"""Authenticated attachment workflow transport; role parameters never grant access."""
from pathlib import Path
import tempfile
from fastapi import APIRouter, File, Form, UploadFile, Request, HTTPException
from pydantic import BaseModel

class Decision(BaseModel):
    preview_token: str
    decision: str


def attachment_router(agent, invalidate):
    router=APIRouter(prefix='/api/attachments')
    def user(request):
        identity=getattr(request.state,'user',None)
        if not identity: raise HTTPException(401,'Authentication required')
        return identity
    def run(function,*args,**kwargs):
        try: return function(*args,**kwargs)
        except PermissionError as error: raise HTTPException(403,str(error)) from error
        except KeyError as error: raise HTTPException(404,'Attachment operation not found') from error
        except (ValueError, OSError) as error:
            detail=str(error) if isinstance(error,ValueError) else 'Attachment storage is unavailable'
            raise HTTPException(409,detail) from error
        except Exception as error:
            raise HTTPException(422,'Could not process this attachment. Check its format and schema, then retry.') from error
    @router.get('')
    def operations(request: Request):
        return {'items':run(agent.list,user(request))}
    @router.get('/schemas')
    def schemas(request: Request):
        identity=user(request)
        run(agent._identity,identity)
        from .ingestion.workforce import workforce_schema_manifest
        from .workforce_models import workforce_schema_catalog
        return {'datasets':workforce_schema_manifest(),'schemas':workforce_schema_catalog()}
    @router.post('',status_code=202)
    def upload(request: Request,file: UploadFile=File(...),instruction: str=Form(...),
               kind: str=Form(...),project_code: str=Form(''),external_processing: bool=Form(False),
               replacement_id: str=Form('')):
        identity=user(request)
        with tempfile.NamedTemporaryFile(delete=False,suffix=Path(file.filename or '').suffix) as temporary:
            path=Path(temporary.name)
            try:
                total=0
                while chunk:=file.file.read(1024*1024):
                    total+=len(chunk)
                    if total>20*1024*1024: raise HTTPException(413,'Attachments cannot exceed 20 MB')
                    temporary.write(chunk)
                temporary.close()
                return run(agent.prepare,path,file.filename or '',instruction,project_code,kind,identity,
                           external_processing,replacement_id or None)
            finally:
                temporary.close();path.unlink(missing_ok=True)
    @router.get('/{operation_id}')
    def operation(operation_id: str,request: Request):
        return run(agent.get,operation_id,user(request))
    @router.post('/{operation_id}/decision')
    def decide(operation_id: str,body: Decision,request: Request):
        result=run(agent.decide,operation_id,user(request),body.preview_token,body.decision)
        invalidate()
        return result
    return router
