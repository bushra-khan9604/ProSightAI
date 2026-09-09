"""Authenticated natural-language project draft API."""
from fastapi import APIRouter,Request,HTTPException,UploadFile,File,Form
from pathlib import Path
import tempfile
from pydantic import BaseModel,Field
from .agents.project_creation import DraftFields

class StartDraft(BaseModel):
    id: str
class EditDraft(BaseModel):
    revision: str
    fields: DraftFields | None = None
    message: str | None = Field(default=None,min_length=1,max_length=4000)
    allow_ai: bool = False
class DecideDraft(BaseModel):
    revision: str
    decision: str


def project_draft_router(agent,invalidate):
    router=APIRouter(prefix='/api/project-drafts')
    def identity(request):
        user=getattr(request.state,'user',None)
        if not user:raise HTTPException(401,'Authentication required')
        return user
    def run(function,*args,**kwargs):
        try:return function(*args,**kwargs)
        except PermissionError as error:raise HTTPException(403,str(error)) from error
        except KeyError as error:raise HTTPException(404,'Project draft not found') from error
        except ValueError as error:raise HTTPException(409,str(error)) from error
        except Exception as error:raise HTTPException(503,'The project draft could not be saved. Please retry.') from error
    @router.get('')
    def drafts(request:Request):return {'items':run(agent.list,identity(request))}
    @router.post('',status_code=201)
    def start(body:StartDraft,request:Request):return run(agent.start,body.id,identity(request))
    @router.get('/mapping-profile')
    def mapping_profile(request:Request):
        run(agent.identity,identity(request))
        from .ingestion.project_mapping import load_mapping,ProjectMapping
        from .project_models import ProjectDraft
        return {'profile':run(load_mapping).model_dump(),'profile_schema':ProjectMapping.model_json_schema(),
                'project_schema':ProjectDraft.model_json_schema()}
    @router.post('/workbook',status_code=201)
    def workbook(request:Request,file:UploadFile=File(...),batch_id:str=Form(...)):
        user=identity(request)
        run(agent.identity,user)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'register.xlsx'
            with path.open('wb') as destination:
                size=0
                while chunk:=file.file.read(1024*1024):
                    size+=len(chunk)
                    if size>20*1024*1024:raise HTTPException(413,'Attachments cannot exceed 20 MB')
                    destination.write(chunk)
            return run(agent.import_workbook,path,file.filename or '',batch_id,user)
    @router.get('/{identifier}')
    def get(identifier:str,request:Request):return run(agent.get,identifier,identity(request))
    @router.patch('/{identifier}')
    def edit(identifier:str,body:EditDraft,request:Request):
        return run(agent.edit,identifier,identity(request),body.revision,
            body.fields.model_dump(exclude_unset=True) if body.fields is not None else None,body.message,body.allow_ai)
    @router.post('/{identifier}/decision')
    def decide(identifier:str,body:DecideDraft,request:Request):
        result=run(agent.decide,identifier,identity(request),body.revision,body.decision);invalidate();return result
    return router
