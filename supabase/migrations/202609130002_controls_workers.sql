-- Durable jobs have bounded attempts and lease ownership. Only backend workers may claim them.
alter table public.controls_jobs add column lease_id uuid;
alter table public.controls_jobs add column lease_until timestamptz;
alter table public.controls_jobs add column attempts integer not null default 0;
create or replace function public.claim_controls_job() returns jsonb language plpgsql security definer set search_path=public as $$
declare j controls_jobs;
begin
 update controls_jobs set status='failed',error='Worker retry limit exceeded',updated_at=now()
 where kind in ('analyst','planner') and attempts>=3 and status='running' and lease_until<now();
 select * into j from controls_jobs where kind in ('analyst','planner') and attempts<3
 and (status='queued' or (status='running' and lease_until<now())) order by created_at for update skip locked limit 1;
 if j.id is null then return null; end if;
 if not exists(select 1 from profiles p where p.id=j.requested_by and (p.role='admin' or exists(select 1 from project_memberships m where m.user_id=p.id and m.project_code=j.project_code))) then
  update controls_jobs set status='failed',error='Project access was revoked',updated_at=now() where id=j.id;
  return null;
 end if;
 update controls_jobs set status='running',lease_id=gen_random_uuid(),lease_until=now()+interval '10 minutes',attempts=attempts+1,updated_at=now() where id=j.id returning * into j;
 return to_jsonb(j);
end $$;
revoke all on function public.claim_controls_job() from public,authenticated;
grant execute on function public.claim_controls_job() to service_role;

create or replace function public.finish_controls_job(p_id uuid,p_lease uuid,p_result jsonb,p_status text,p_error text) returns jsonb
language plpgsql security definer set search_path=public as $$
declare j controls_jobs;
begin
 if p_status not in ('completed','failed','cancelled') then raise exception 'Invalid terminal state'; end if;
 select * into j from controls_jobs where id=p_id and lease_id=p_lease and status='running' for update;
 if j.id is null then return null; end if;
 if not exists(select 1 from profiles p where p.id=j.requested_by and (p.role='admin' or exists(select 1 from project_memberships m where m.user_id=p.id and m.project_code=j.project_code))) then
  update controls_jobs set status='failed',result=null,error='Project access was revoked' where id=j.id;return null;
 end if;
 update controls_jobs set status=p_status,result=p_result,error=p_error,lease_until=null,updated_at=now() where id=j.id returning * into j;
 return to_jsonb(j);
end $$;
revoke all on function public.finish_controls_job(uuid,uuid,jsonb,text,text) from public,authenticated;
grant execute on function public.finish_controls_job(uuid,uuid,jsonb,text,text) to service_role;

create or replace function public.worker_stage_controls_version(p_job uuid,p_lease uuid,p_args jsonb) returns jsonb
language plpgsql security definer set search_path=public as $$
declare j controls_jobs;
begin
 select * into j from controls_jobs where id=p_job and lease_id=p_lease and status='running' for update;
 if j.id is null or j.project_code<>p_args->>'p_code' then raise exception 'Job was cancelled or lease expired'; end if;
 perform set_config('request.jwt.claim.sub',j.requested_by::text,true);
 perform set_config('request.jwt.claims',jsonb_build_object('sub',j.requested_by,'role','authenticated')::text,true);
 return stage_controls_version(p_args->>'p_code',(p_args->>'p_parent')::uuid,p_args->'p_content',p_args->'p_metadata',p_args->'p_validation',p_args->>'p_checksum');
end $$;
revoke all on function public.worker_stage_controls_version(uuid,uuid,jsonb) from public,authenticated;
grant execute on function public.worker_stage_controls_version(uuid,uuid,jsonb) to service_role;

drop policy controls_jobs_read on public.controls_jobs;
create policy controls_jobs_read on public.controls_jobs for select to authenticated using (
 has_project_access(project_code) and (requested_by=auth.uid() or is_admin())
 and (version_id is null or exists(select 1 from controls_versions v where v.id=version_id))
 and not exists(select 1 from jsonb_array_elements(coalesce(result->'structured_results'->'historical_sources','[]')) h where not has_project_access(h->>'project_code'))
);
