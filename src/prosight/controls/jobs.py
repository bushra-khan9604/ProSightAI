"""Bounded durable specialist workers; user JWTs are never stored or replayed."""
from __future__ import annotations
import asyncio
from contextlib import suppress

from ..auth import AuthContext, current_auth
from ..supabase_gateway import SupabaseGateway


class WorkerGateway:
    """A deliberately narrow service client rechecking the requesting user's membership."""
    def __init__(self,service,job):self.service=service;self.job=job

    def identity(self):
        profiles=self.service.select('profiles',id=f"eq.{self.job['requested_by']}",limit='1')
        if not profiles:raise PermissionError('Requesting user no longer exists')
        profile=profiles[0]
        memberships=self.service.select_all('project_memberships',user_id=f"eq.{profile['id']}")
        return profile,{r['project_code'] for r in memberships}

    def authorize(self,code):
        profile,codes=self.identity()
        if profile['role']!='admin' and code not in codes:raise PermissionError('Project access was revoked')

    def select(self,table,**filters):return self.select_all(table,**filters)

    def select_all(self,table,**filters):
        reader=self.service.select if 'limit' in filters else self.service.select_all
        if table=='controls_jobs':
            filters['id']=f"eq.{self.job['id']}"
            self.authorize(self.job['project_code'])
            return reader(table,**filters)
        if table not in {'controls_versions','document_chunks','documents'}:
            raise PermissionError('Worker read is not allowlisted')
        code=filters.get('project_code','')
        if not code.startswith('eq.'):raise PermissionError('Worker reads require one explicit project')
        self.authorize(code[3:])
        rows=reader(table,**filters)
        if table=='controls_versions':
            for row in rows:
                for reference in row['content'].get('Demand',[])+row['content'].get('Historical Sources',[]):
                    self.authorize(reference['project_code'])
        return rows

    def update(self,table,payload,**filters):
        if table!='controls_jobs' or filters.get('id')!=f"eq.{self.job['id']}":raise PermissionError('Worker mutation is not allowlisted')
        self.authorize(self.job['project_code'])
        return self.service.rpc('finish_controls_job',{'p_id':self.job['id'],'p_lease':self.job['lease_id'],'p_result':payload.get('result'),
                                'p_status':payload.get('status','failed'),'p_error':payload.get('error')})

    def rpc(self,function,payload):
        if function!='stage_controls_version':raise PermissionError('Worker action is not allowlisted')
        self.authorize(payload['p_code'])
        return self.service.rpc('worker_stage_controls_version',{'p_job':self.job['id'],'p_lease':self.job['lease_id'],'p_args':payload})


class WorkerRepository:
    def __init__(self,service,job):self.user=WorkerGateway(service,job);self.service=service
    def list_projects(self,user_role='employee'):
        profile,codes=self.user.identity()
        rows=self.service.select_all('projects') if profile['role']=='admin' else self.service.select_all('projects',code='in.('+','.join(sorted(codes))+')') if codes else []
        return [{**r.get('payload',{}),**{k:v for k,v in r.items() if k!='payload'}} for r in rows]
    def find_project(self,term,user_role='employee'):
        return next((p for p in self.list_projects(user_role) if term in (p['code'],p['name'])),None)
    def list_documents(self,code):return self.user.select_all('documents',project_code=f'eq.{code}')


class ControlsWorker:
    def __init__(self,service,concurrency=2):self.service=service;self.concurrency=concurrency;self.tasks=[]
    def start(self):self.tasks=[asyncio.create_task(self.loop()) for _ in range(self.concurrency)]
    async def close(self):
        for task in self.tasks:task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError):await task
    async def loop(self):
        from .specialists import SpecialistService
        while True:
            try:
                claimed=await asyncio.to_thread(self.service.rpc,'claim_controls_job',{})
                if not claimed:
                    await asyncio.sleep(1);continue
                repository=WorkerRepository(self.service,claimed)
                profile,codes=await asyncio.to_thread(repository.user.identity)
                token=current_auth.set(AuthContext(profile['id'],profile.get('email',''),profile.get('display_name',''),profile['role'],tuple(codes),''))
                try:
                    if claimed['kind']=='export':
                        await self.export(repository,claimed)
                    else:
                        await SpecialistService(repository).run(claimed['input']['query'],claimed['project_code'],profile['role'],claimed['kind']=='planner',existing_run=claimed)
                finally:current_auth.reset(token)
            except asyncio.CancelledError:raise
            except Exception:
                # Failed leases expire and are claimed again; repeated attempts become terminal.
                await asyncio.sleep(2)

    async def export(self,repository,job):
        from .store import ControlsStore
        from .exports import render, analysis_rows
        import hashlib
        version=ControlsStore(repository).version(job['project_code'],job['version_id'])
        if job['input'].get('run_id'):
            rows=self.service.select('controls_jobs',id=f"eq.{job['input']['run_id']}",project_code=f"eq.{job['project_code']}",requested_by=f"eq.{job['requested_by']}",limit='1')
            if not rows or rows[0]['status']!='completed':raise PermissionError('Analysis run is unavailable')
            result=rows[0]['result']['structured_results']
            for source in result.get('historical_sources',[]):repository.user.authorize(source['project_code'])
            version={**version,'content':{**version['content'],'Analysis Findings':analysis_rows(result)}}
        content,mime=await asyncio.to_thread(render,version,job['input']['format'])
        repository.user.authorize(job['project_code'])
        state=self.service.select('controls_jobs',id=f"eq.{job['id']}",limit='1')[0]
        if state['status']!='running' or state['lease_id']!=job['lease_id']:return
        artifact_id=job['input']['artifact_id']
        key=f"{job['project_code']}/controls/{artifact_id}.{job['input']['format']}"
        await asyncio.to_thread(self.service.upload,'project-documents',key,content,mime,upsert=True)
        repository.user.authorize(job['project_code'])
        self.service.update('controls_artifacts',{'status':'ready','storage_key':key,'checksum':hashlib.sha256(content).hexdigest()},id=f'eq.{artifact_id}',project_code=f"eq.{job['project_code']}",version_id=f"eq.{job['version_id']}")
        repository.user.update('controls_jobs',{'status':'completed','result':{'artifact_id':artifact_id}},id=f"eq.{job['id']}")
