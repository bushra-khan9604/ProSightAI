create or replace function public.append_controls_batch_file(p_id uuid,p_file jsonb,p_document boolean) returns jsonb
language plpgsql security definer set search_path=public as $$
declare j controls_jobs; field text;
begin
 select * into j from controls_jobs where id=p_id for update;
 if j.id is null or j.kind<>'import' or j.requested_by<>auth.uid() or not has_project_access(j.project_code) or current_app_role() not in ('admin','planning_engineer','project_manager') then raise exception 'Batch editor access required'; end if;
 if j.status<>'queued' or j.version_id is not null then raise exception 'Batch is frozen for validation'; end if;
 field:=case when p_document then 'documents' else 'files' end;
 if exists(select 1 from jsonb_array_elements(coalesce(j.input->field,'[]')) f where f->>'checksum'=p_file->>'checksum') then return to_jsonb(j); end if;
 if jsonb_array_length(coalesce(j.input->'files','[]'))+jsonb_array_length(coalesce(j.input->'documents','[]'))>=30 then raise exception 'Batch file limit exceeded'; end if;
 update controls_jobs set input=jsonb_set(input,array[field],coalesce(input->field,'[]')||jsonb_build_array(p_file)),updated_at=now() where id=p_id returning * into j;
 return to_jsonb(j);
end $$;
revoke all on function public.append_controls_batch_file(uuid,jsonb,boolean) from public;
grant execute on function public.append_controls_batch_file(uuid,jsonb,boolean) to authenticated;

create or replace function public.freeze_controls_batch(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public as $$
declare j controls_jobs;
begin
 select * into j from controls_jobs where id=p_id for update;
 if j.id is null or j.kind<>'import' or j.requested_by<>auth.uid() or not has_project_access(j.project_code) then raise exception 'Batch access required'; end if;
 if j.version_id is not null then return to_jsonb(j); end if;
 if j.status<>'queued' and not(j.status='running' and j.updated_at<now()-interval '5 minutes') then raise exception 'Batch is already validating or closed'; end if;
 update controls_jobs set status='running',updated_at=now() where id=p_id returning * into j;
 return to_jsonb(j);
end $$;
revoke all on function public.freeze_controls_batch(uuid) from public;
grant execute on function public.freeze_controls_batch(uuid) to authenticated;

alter table public.controls_artifacts add column status text not null default 'queued' check(status in ('queued','ready','failed'));
alter table public.controls_artifacts add column storage_key text;
alter table public.controls_artifacts add column checksum text;
alter table public.controls_artifacts add column run_id uuid references controls_jobs(id);

create or replace function public.create_controls_export(p_version uuid,p_format text,p_run uuid default null) returns jsonb
language plpgsql security definer set search_path=public as $$
declare v controls_versions; a controls_artifacts; j controls_jobs;
begin
 select * into v from controls_versions where id=p_version;
 if v.id is null or not has_project_access(v.project_code) or p_format not in ('xlsx','pdf') then raise exception 'Invalid or unauthorized export'; end if;
 if p_run is not null then
  select * into j from controls_jobs where id=p_run and project_code=v.project_code and requested_by=auth.uid();
  if j.id is null or j.status<>'completed' then raise exception 'Analysis run is unavailable'; end if;
 end if;
 insert into controls_artifacts(project_code,version_id,filename,format,run_id) values(v.project_code,v.id,v.project_code||'-controls.'||p_format,p_format,p_run) returning * into a;
 insert into controls_jobs(project_code,requested_by,kind,version_id,input) values(v.project_code,auth.uid(),'export',v.id,jsonb_build_object('artifact_id',a.id,'format',p_format,'run_id',p_run));
 return to_jsonb(a);
end $$;
revoke all on function public.create_controls_export(uuid,text,uuid) from public;
grant execute on function public.create_controls_export(uuid,text,uuid) to authenticated;

-- Include export jobs in the same bounded worker lease queue.
create or replace function public.claim_controls_job() returns jsonb language plpgsql security definer set search_path=public as $$
declare j controls_jobs;
begin
 update controls_jobs set status='failed',error='Worker retry limit exceeded',updated_at=now()
 where kind in ('analyst','planner','export') and attempts>=3 and status='running' and lease_until<now();
 select * into j from controls_jobs where kind in ('analyst','planner','export') and attempts<3
 and (status='queued' or (status='running' and lease_until<now())) order by created_at for update skip locked limit 1;
 if j.id is null then return null; end if;
 if not exists(select 1 from profiles p where p.id=j.requested_by and (p.role='admin' or exists(select 1 from project_memberships m where m.user_id=p.id and m.project_code=j.project_code))) then
  update controls_jobs set status='failed',error='Project access was revoked',updated_at=now() where id=j.id;return null;
 end if;
 update controls_jobs set status='running',lease_id=gen_random_uuid(),lease_until=now()+interval '10 minutes',attempts=attempts+1,updated_at=now() where id=j.id returning * into j;
 return to_jsonb(j);
end $$;

drop policy controls_artifacts_read on public.controls_artifacts;
create policy controls_artifacts_read on public.controls_artifacts for select to authenticated using (
 has_project_access(project_code) and exists(select 1 from controls_versions v where v.id=version_id)
 and (run_id is null or exists(select 1 from controls_jobs j where j.id=run_id))
);

create index controls_jobs_claim_idx on public.controls_jobs(kind,status,created_at) where status in ('queued','running');
create index controls_jobs_user_idx on public.controls_jobs(requested_by,project_code);
create index controls_artifacts_version_idx on public.controls_artifacts(version_id);
create index controls_versions_parent_idx on public.controls_versions(parent_id);

-- Export objects must satisfy all source-project permissions even via Storage URLs.
create policy controls_export_storage_read on storage.objects as restrictive for select to authenticated
 using (bucket_id<>'project-documents' or (storage.foldername(name))[2]<>'controls'
 or exists(select 1 from public.controls_artifacts a where a.storage_key=name and a.status='ready'));
create policy controls_export_storage_insert on storage.objects as restrictive for insert to authenticated
 with check (bucket_id<>'project-documents' or coalesce((storage.foldername(name))[2],'')<>'controls');

-- Direct Data API job updates cannot change identity, evidence scope or worker leases.
create function public.guard_controls_job_update() returns trigger language plpgsql set search_path=public as $$
begin
 if current_user='authenticated' then
  if new.project_code is distinct from old.project_code or new.requested_by is distinct from old.requested_by
   or new.kind is distinct from old.kind or new.lease_id is distinct from old.lease_id
   or new.lease_until is distinct from old.lease_until or new.attempts is distinct from old.attempts then
   raise exception 'Job identity and lease are immutable';
  end if;
  if old.kind<>'import' and (new.input is distinct from old.input or new.version_id is distinct from old.version_id
   or new.result is distinct from old.result or new.status<>'cancelled' or old.status not in ('queued','running')) then
   raise exception 'Only cancellation is allowed for specialist jobs';
  end if;
 end if;
 return new;
end $$;
create trigger guard_controls_jobs before update on public.controls_jobs for each row execute function public.guard_controls_job_update();

drop policy controls_jobs_insert on public.controls_jobs;
create policy controls_jobs_insert on public.controls_jobs for insert to authenticated with check (
 has_project_access(project_code) and requested_by=(select auth.uid()) and status='queued' and result is null and lease_id is null and attempts=0
 and kind in ('import','analyst','planner') and (kind='analyst' or current_app_role() in ('admin','planning_engineer','project_manager'))
 and (version_id is null or exists(select 1 from controls_versions v where v.id=version_id and v.project_code=controls_jobs.project_code))
);
revoke insert on public.controls_artifacts from authenticated;
grant select,insert,update,delete on public.controls_jobs,public.controls_artifacts to service_role;
grant select on public.controls_versions to service_role;
