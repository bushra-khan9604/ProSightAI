"""Governed import and draft endpoints mounted on the existing application."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pypdf import PdfReader

from ..auth import current_auth
from .store import ControlsStore
from .workbooks import MAX_BYTES, parse, merge_files, validate


class BatchRequest(BaseModel):
    project_code: str = Field(min_length=3,max_length=30)
    dataset: str = "mixed"


class DraftEdit(BaseModel):
    tables: dict[str,list[dict]]


def register_controls_routes(app, runtime, caller_role):
    parsing = asyncio.Semaphore(2)
    def store():
        if not hasattr(runtime.repository,"user"):
            raise HTTPException(503,"Project controls require the Supabase migrations")
        return ControlsStore(runtime.repository)

    def editor(role):
        if role not in {"admin","planning_engineer","project_manager"}:
            raise HTTPException(403,"Project editor access required")

    def job(job_id):
        rows=store().db.select("controls_jobs",id=f"eq.{job_id}",limit="1")
        if not rows:
            raise HTTPException(404,"Batch or run not found or unauthorized")
        return rows[0]

    @app.post("/api/portfolio-import-batches",status_code=201)
    def create_batch(body:BatchRequest,role=Depends(caller_role)):
        editor(role)
        s=store()
        if not runtime.repository.find_project(body.project_code,role):
            raise HTTPException(404,"Project not found or unauthorized")
        auth=current_auth.get()
        if not auth:
            raise HTTPException(401,"Authentication required")
        return s.db.insert("controls_jobs",{"project_code":body.project_code,"requested_by":auth.user_id,"kind":"import",
                           "input":{"dataset":body.dataset,"files":[],"documents":[]}})[0]

    @app.get("/api/portfolio-import-batches/{batch_id}")
    def batch_status(batch_id:str,role=Depends(caller_role)):
        value=job(batch_id)
        result=copy.deepcopy(value)
        for file in result["input"].get("files",[]):
            file.pop("tables",None);file.pop("sources",None)
        for document in result['input'].get('documents',[]):
            old=document.get('job') or {}
            if old.get('id'):
                document['job']=runtime.repository.get_job(old['id']) or old
        return result

    @app.post("/api/portfolio-import-batches/{batch_id}/files")
    async def add_file(batch_id:str,file:UploadFile=File(...),role=Depends(caller_role)):
        editor(role)
        value=job(batch_id)
        if value["kind"]!="import" or value["status"]!="queued" or value.get("version_id"):
            raise HTTPException(409,"Create a new batch to change a validated import")
        state=value["input"]
        if len(state.get("files",[]))+len(state.get("documents",[]))>=30:
            raise HTTPException(400,"A batch supports at most 30 files")
        suffix=Path(file.filename or "").suffix.lower()
        if suffix not in {".xlsx",".pdf"}:
            raise HTTPException(400,"Only XLSX and PDF files are supported; ZIP files are excluded")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/Path(file.filename).name
            size=0
            with path.open("wb") as output:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>MAX_BYTES:
                        raise HTTPException(413,"File exceeds 20 MB")
                    output.write(chunk)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if any(f.get("checksum")==digest for f in state.get("files",[])+state.get("documents",[])):
                return batch_status(batch_id,role)
            try:
                if suffix==".xlsx":
                    def resolve(term):
                        p=runtime.repository.find_project(term,role)
                        return p["code"] if p else None
                    async with parsing:
                        parsed=await asyncio.to_thread(parse,path,value["project_code"],resolve)
                    parsed["filename"]=Path(file.filename).name
                    appended=parsed
                else:
                    reader=PdfReader(path)
                    if reader.is_encrypted or len(reader.pages)>300:
                        raise ValueError("Encrypted PDFs and PDFs over 300 pages are unsupported")
                    text="\n".join(page.extract_text() or "" for page in reader.pages)
                    if not text.strip():
                        raise ValueError("PDF has no searchable text; OCR is not supported")
                    if any(t in text.lower() for t in ("reference kickoff", "evaluation_only", "evaluation-only", "reference answer")):
                        raise ValueError("Evaluation reference answers cannot be ingested")
                    if not runtime.ingestion:
                        raise HTTPException(503,"PDF ingestion is unavailable")
                    result=await asyncio.to_thread(runtime.ingestion.submit,path,Path(file.filename).name,value["project_code"],role)
                    appended={"filename":Path(file.filename).name,"checksum":digest,**result}
                store().db.rpc('append_controls_batch_file',{'p_id':batch_id,'p_file':appended,'p_document':suffix=='.pdf'})
            except (ValueError,PermissionError) as exc:
                raise HTTPException(400,str(exc)) from exc
        return batch_status(batch_id,role)

    @app.post("/api/portfolio-import-batches/{batch_id}/validate")
    def validate_batch(batch_id:str,role=Depends(caller_role)):
        editor(role)
        value=job(batch_id)
        if value.get("version_id"):
            return store().version(value["project_code"],value["version_id"])
        if not value["input"].get("files"):
            return {"validation":{"counts":{},"warnings":["Documents follow individual date confirmation and Admin approval."]},"documents":value["input"].get("documents",[])}
        try:
            value=store().db.rpc('freeze_controls_batch',{'p_id':batch_id})
            version=store().stage(value["project_code"],value["input"]["files"])
            store().db.update("controls_jobs",{"status":"queued","version_id":version["id"],"result":{"validation":version["validation"]}},id=f"eq.{batch_id}",status='eq.running')
            return version
        except (ValueError,KeyError) as exc:
            store().db.update('controls_jobs',{'status':'queued','error':str(exc)},id=f'eq.{batch_id}',status='eq.running')
            raise HTTPException(400,str(exc)) from exc

    @app.post("/api/portfolio-import-batches/{batch_id}/submit")
    def submit_batch(batch_id:str,role=Depends(caller_role)):
        editor(role)
        value=job(batch_id)
        if value["status"]=="completed":
            return value["result"]
        if value["input"].get("files") and not value.get("version_id"):
            raise HTTPException(409,"Validate and review the batch before submitting")
        result=store().submit(value["project_code"],value["version_id"]) if value.get("version_id") else {"status":"documents_pending_individual_approval"}
        store().db.update("controls_jobs",{"status":"completed","result":result},id=f"eq.{batch_id}")
        return result

    @app.post('/api/agent-runs/{run_id}/exports/{format}')
    def export_run(run_id:str,format:Literal['xlsx','pdf'],role=Depends(caller_role)):
        value=job(run_id)
        if value['status']!='completed':raise HTTPException(409,'Run has not completed')
        return store().db.rpc('create_controls_export',{'p_version':value['version_id'],'p_format':format,'p_run':run_id})

    @app.get("/api/projects/{code}/controls-versions")
    def versions(code:str,role=Depends(caller_role)):
        return store().db.select("controls_versions",select="id,parent_id,status,reporting_date,synthetic,validation,created_at",project_code=f"eq.{code}",order="created_at.desc")

    @app.get("/api/projects/{code}/controls-versions/{version_id}")
    def version_detail(code:str,version_id:str,role=Depends(caller_role)):
        try: return store().version(code,version_id)
        except KeyError as exc: raise HTTPException(404,str(exc)) from exc

    @app.patch("/api/projects/{code}/controls-versions/{version_id}")
    def edit_version(code:str,version_id:str,body:DraftEdit,role=Depends(caller_role)):
        editor(role)
        try:
            old=store().version(code,version_id)
            if old["status"] not in {"draft","rejected"}:
                raise ValueError("Only unsubmitted drafts can be edited; create a new revision first")
            from .workbooks import SCHEMA
            if set(body.tables)-set(SCHEMA)-{'Proposed Recovery'}:
                raise ValueError("Unsupported editable sheets")
            project=runtime.repository.find_project(code)
            if project['status']!='future' and set(body.tables)-{'Proposed Recovery'}:
                raise ValueError('Execution draft edits are limited to proposed recovery; original baselines and actuals are immutable')
            tables={**old["content"],**body.tables}
            from .specialists import recalculate_draft
            recalculate_draft(tables,project)
            return store().stage(code,[],parent_id=version_id,tables=tables,reporting_date=old["reporting_date"])
        except (ValueError,KeyError) as exc: raise HTTPException(400,str(exc)) from exc

    @app.post("/api/projects/{code}/controls-versions/{version_id}/submit")
    def submit_version(code:str,version_id:str,role=Depends(caller_role)):
        editor(role)
        return store().submit(code,version_id)

    @app.get("/api/agent-runs/{run_id}")
    def run_status(run_id:str,role=Depends(caller_role)):
        value=job(run_id)
        if (value.get('result') or {}).get('_evidence'):
            from ..contracts import DatabaseEvidence
            from ..agents.writer import WriterAgent
            data=copy.deepcopy(value['result']);evidence=DatabaseEvidence.model_validate(data.pop('_evidence'))
            packet=WriterAgent.prepare_input(value['input']['query'],evidence);packet.specialist_metadata=data
            answer=WriterAgent().fallback(packet).model_dump()
            answer['agent_route']=['analyst','planner','writer'] if value['kind']=='planner' else ['analyst','writer']
            value['answer']=answer
        return value

    @app.post("/api/agent-runs/{run_id}/cancel")
    def cancel_run(run_id:str,role=Depends(caller_role)):
        job(run_id)
        result=store().db.update("controls_jobs",{"status":"cancelled"},id=f"eq.{run_id}",status="in.(queued,running)")
        return result[0] if result else job(run_id)

    @app.post("/api/projects/{code}/controls-versions/{version_id}/exports/{format}")
    def export_version(code:str,version_id:str,format:Literal['xlsx','pdf'],role=Depends(caller_role)):
        store().version(code,version_id)
        return store().db.rpc('create_controls_export',{'p_version':version_id,'p_format':format,'p_run':None})

    @app.get("/api/artifacts/{artifact_id}/download")
    async def download_artifact(artifact_id:str,role=Depends(caller_role)):
        rows=store().db.select("controls_artifacts",id=f"eq.{artifact_id}",limit="1")
        if not rows: raise HTTPException(404,"Artifact not found or unauthorized")
        artifact=rows[0]
        version=store().version(artifact["project_code"],artifact["version_id"])
        for _ in range(120):
            if artifact['status']=='ready':break
            if artifact['status']=='failed':raise HTTPException(409,'Export failed; request another export')
            await asyncio.sleep(.5)
            rows=await asyncio.to_thread(store().db.select,'controls_artifacts',id=f'eq.{artifact_id}',limit='1')
            if not rows:raise HTTPException(404,'Artifact is no longer accessible')
            artifact=rows[0]
        if artifact['status']!='ready':raise HTTPException(409,'Export is still processing; retry this artifact download')
        content=await asyncio.to_thread(runtime.repository.service.download,'project-documents',artifact['storage_key'])
        if not store().db.select('controls_artifacts',id=f'eq.{artifact_id}',limit='1'):
            raise HTTPException(404,'Artifact is no longer accessible')
        mime='application/pdf' if artifact['format']=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return Response(content,media_type=mime,headers={"Content-Disposition":f'attachment; filename="{artifact["filename"]}"'})
