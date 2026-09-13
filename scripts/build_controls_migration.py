"""Generate the checked-in typed schema from the versioned workbook contract."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
schema = json.loads((ROOT / "src/prosight/controls/workbook_schema.json").read_text())
sql = '''-- Versioned project controls. No synthetic project data is installed.
create table public.controls_versions (
 id uuid primary key default gen_random_uuid(),
 project_code text not null references public.projects(code),
 parent_id uuid references public.controls_versions(id),
 status text not null default 'draft' check(status in ('draft','pending_approval','approved','active','rejected','superseded')),
 reporting_date date not null, construction_cutoff date, financial_cutoff date,
 author_id uuid not null references public.profiles(id), synthetic boolean not null default false,
 source_files jsonb not null default '[]', content jsonb not null,
 validation jsonb not null, checksum text not null, created_at timestamptz not null default now(),
 unique(project_code,id), unique(project_code,checksum)
);
create unique index controls_one_active on public.controls_versions(project_code) where status='active';
alter table public.controls_versions enable row level security;
create policy controls_versions_read on public.controls_versions for select to authenticated
 using(public.has_project_access(project_code) and not exists (
 select 1 from jsonb_array_elements(coalesce(content->'Demand','[]')) d where not public.has_project_access(d->>'project_code'))
 and not exists(select 1 from jsonb_array_elements(coalesce(content->'Historical Sources','[]')) h where not public.has_project_access(h->>'project_code')));
revoke all on public.controls_versions from anon, authenticated;
grant select on public.controls_versions to authenticated;
'''
inserts = []
for table in schema["tables"]:
    name = 'controls_' + table['sheet'].lower().replace(' ', '_')
    fields = []
    for field in table['fields']:
        if field['name'] == 'project_code':
            continue
        kind = {'number': 'numeric', 'date': 'date', 'boolean': 'boolean', 'string': 'text'}[field['type']]
        fields.append(f' "{field["name"]}" {kind}')
    sql += f'''\ncreate table public.{name} (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
{','.join(fields)},
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.{name} enable row level security;
create policy {name}_read on public.{name} for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.{name} from anon, authenticated;
grant select on public.{name} to authenticated;
'''
    fieldnames = [f['name'] for f in table['fields'] if f['name'] != 'project_code']
    keynames = [k for k in table['primary_key'] if k != 'project_code']
    if keynames:
        sql += f'create unique index {name}_identity on public.{name}(controls_version_id,' + ','.join('"'+k+'"' for k in keynames) + ');\n'
    columns = ','.join('"'+f+'"' for f in fieldnames)
    values = ','.join('r."'+f+'"' for f in fieldnames)
    inserts.append(f'''insert into public.{name}(controls_version_id,project_code,record_number,{columns})
 select v_id,p_code,row_number() over()::integer,{values}
 from jsonb_populate_recordset(null::public.{name},coalesce(p_content->'{table['sheet']}', '[]')) r;''')

sql += '''
create or replace function public.stage_controls_version(p_code text,p_parent uuid,p_content jsonb,p_metadata jsonb,p_validation jsonb,p_checksum text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_id uuid; item jsonb;
begin
 if not public.has_project_access(p_code) or public.current_app_role() not in ('admin','planning_engineer','project_manager') then
  raise exception 'Project editor access required';
 end if;
 if jsonb_typeof(p_content) <> 'object' or octet_length(p_content::text)>25000000 then raise exception 'Invalid controls payload'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p_code,0));
 if p_parent is not null and not exists(select 1 from controls_versions where id=p_parent and project_code=p_code) then raise exception 'Invalid parent'; end if;
 for item in select value from jsonb_array_elements(coalesce(p_content->'Demand','[]')) loop
  if not public.has_project_access(item->>'project_code') then raise exception 'Unauthorized shared demand'; end if;
 end loop;
 for item in select value from jsonb_array_elements(coalesce(p_content->'Historical Sources','[]')) loop
  if not public.has_project_access(item->>'project_code') then raise exception 'Unauthorized historical source'; end if;
  if not exists(select 1 from controls_versions where id=(item->>'version_id')::uuid and project_code=item->>'project_code') then raise exception 'Historical source version mismatch'; end if;
 end loop;
 if exists(select 1 from jsonb_array_elements(coalesce(p_content->'Relationships','[]')) r where r->>'type'<>'FS') then raise exception 'Only FS relationships are supported'; end if;
 if jsonb_array_length(coalesce(p_content->'Schedule','[]'))>1000 then raise exception 'Version supports at most 1000 activities'; end if;
 if jsonb_array_length(coalesce(p_content->'Schedule','[]'))>0 and exists(
  select 1 from jsonb_array_elements(coalesce(p_content->'Relationships','[]')) r
  where not exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')||coalesce(p_content->'Milestones','[]')) a where a->>'activity_id'=r->>'predecessor_id')
  or not exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')||coalesce(p_content->'Milestones','[]')) a where a->>'activity_id'=r->>'successor_id')
 ) then raise exception 'Broken schedule relationship'; end if;
 if exists(with recursive edges as (select r->>'predecessor_id' p,r->>'successor_id' s from jsonb_array_elements(coalesce(p_content->'Relationships','[]')) r),
 reach(p,s) as (select p,s from edges union select r.p,e.s from reach r join edges e on r.s=e.p) select 1 from reach where p=s) then raise exception 'Schedule contains a cycle'; end if;
 if exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')) a where (a->>'duration_wd')::numeric<0 or (a->>'duration_wd')::numeric<>trunc((a->>'duration_wd')::numeric)) then raise exception 'Invalid activity duration'; end if;
 if exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')) a where (a->>'actual_start')::date>(p_metadata->>'reporting_date')::date or (a->>'actual_finish')::date>(p_metadata->>'reporting_date')::date) then raise exception 'Actuals exceed reporting cutoff'; end if;
 if (select status from projects where code=p_code)='future' and (jsonb_array_length(coalesce(p_content->'Actual Costs','[]'))>0 or jsonb_array_length(coalesce(p_content->'Measurements','[]'))>0) then raise exception 'Future execution actuals are prohibited'; end if;
 if (select status from projects where code=p_code)='future' and exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')) a where nullif(a->>'actual_start','') is not null or nullif(a->>'actual_finish','') is not null) then raise exception 'Future schedule cannot contain actual dates'; end if;
 if (select status from projects where code=p_code)='completed' and jsonb_array_length(coalesce(p_content->'Current Manpower','[]'))>0 then raise exception 'Historical manpower cannot become current manpower'; end if;
 select id into v_id from controls_versions where project_code=p_code and checksum=p_checksum;
 if v_id is not null then return (select to_jsonb(v) from controls_versions v where id=v_id); end if;
 insert into controls_versions(project_code,parent_id,reporting_date,construction_cutoff,financial_cutoff,author_id,synthetic,source_files,content,validation,checksum)
 values(p_code,p_parent,(p_metadata->>'reporting_date')::date,(p_metadata->>'construction_cutoff')::date,(p_metadata->>'financial_cutoff')::date,
 auth.uid(),coalesce((p_metadata->>'synthetic')::boolean,false),coalesce(p_metadata->'source_files','[]'),p_content,p_validation,p_checksum) returning id into v_id;
'''
sql += '\n'.join(inserts)
sql += '''
 return (select to_jsonb(v) from controls_versions v where id=v_id);
end $$;
revoke all on function public.stage_controls_version(text,uuid,jsonb,jsonb,jsonb,text) from public;
grant execute on function public.stage_controls_version(text,uuid,jsonb,jsonb,jsonb,text) to authenticated;

create or replace function public.submit_controls_version(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public as $$
declare v controls_versions; c change_requests;
begin
 select * into v from controls_versions where id=p_id for update;
 if v.id is null or not public.has_project_access(v.project_code) or public.current_app_role() not in ('admin','planning_engineer','project_manager') then raise exception 'Project editor access required'; end if;
 if v.status='pending_approval' then return (select to_jsonb(x) from change_requests x where payload->>'version_id'=p_id::text and status='pending' limit 1); end if;
 if v.status<>'draft' then raise exception 'Only drafts can be submitted'; end if;
 insert into change_requests(action,project_code,payload,preview,requested_by,requested_role)
 values('controls_activation',v.project_code,jsonb_build_object('version_id',v.id),jsonb_build_object('before',v.parent_id,'after',v.validation,'reporting_date',v.reporting_date),auth.uid(),public.current_app_role()) returning * into c;
 update controls_versions set status='pending_approval' where id=p_id;
 insert into notifications(recipient_user_id,event_type,project_code,change_request_id,title,message)
 select id,'approval_required',v.project_code,c.id,'Project controls approval required','Review validated counts and activate the proposed controls version.' from profiles where role='admin';
 return to_jsonb(c);
end $$;
revoke all on function public.submit_controls_version(uuid) from public;
grant execute on function public.submit_controls_version(uuid) to authenticated;

create or replace function public.decide_controls_version(p_change uuid,p_approve boolean) returns jsonb
language plpgsql security definer set search_path=public as $$
declare c change_requests; v controls_versions; active_id uuid; base_id uuid;
begin
 if not public.is_admin() then raise exception 'Admin approval required'; end if;
 select * into c from change_requests where id=p_change for update;
 if c.id is null or c.action<>'controls_activation' then raise exception 'Controls approval not found'; end if;
 if c.status<>'pending' then return to_jsonb(c); end if;
 perform pg_advisory_xact_lock(hashtextextended(c.project_code,0));
 select * into v from controls_versions where id=(c.payload->>'version_id')::uuid and project_code=c.project_code for update;
 if v.id is null or v.status<>'pending_approval' then raise exception 'Version is not pending approval'; end if;
 if p_approve then
  select id into active_id from controls_versions where project_code=v.project_code and status='active';
  base_id := v.parent_id;
  while base_id is not null and base_id is distinct from active_id loop
   if exists(select 1 from controls_versions where id=base_id and status in ('active','superseded')) then exit; end if;
   select parent_id into base_id from controls_versions where id=base_id;
  end loop;
  if base_id is distinct from active_id then raise exception 'Active version changed; rebase and review the draft'; end if;
  update controls_versions set status='superseded' where id=active_id;
  update controls_versions set status='active' where id=v.id;
 else
  update controls_versions set status='rejected' where id=v.id;
 end if;
 update change_requests set status=case when p_approve then 'approved' else 'rejected' end,
 decided_by=auth.uid(),decided_role='admin',decided_at=now() where id=p_change returning * into c;
 insert into audit_events(actor_user_id,actor_role,action,target_type,target_id,before_json,after_json)
 values(auth.uid(),'admin','controls_activation','controls_version',v.id::text,to_jsonb(active_id),to_jsonb(c));
 return to_jsonb(c);
end $$;
revoke all on function public.decide_controls_version(uuid,boolean) from public;
grant execute on function public.decide_controls_version(uuid,boolean) to authenticated;

create table public.controls_jobs (
 id uuid primary key default gen_random_uuid(), project_code text not null references projects(code),
 requested_by uuid not null references profiles(id), kind text not null check(kind in ('import','analyst','planner','export')),
 status text not null default 'queued' check(status in ('queued','running','completed','failed','cancelled')),
 version_id uuid references controls_versions(id), input jsonb not null default '{}', result jsonb, error text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.controls_jobs enable row level security;
create policy controls_jobs_read on public.controls_jobs for select to authenticated using(has_project_access(project_code) and (requested_by=auth.uid() or is_admin()));
create policy controls_jobs_insert on public.controls_jobs for insert to authenticated with check(has_project_access(project_code) and requested_by=auth.uid());
create policy controls_jobs_update on public.controls_jobs for update to authenticated using(has_project_access(project_code) and requested_by=auth.uid()) with check(has_project_access(project_code) and requested_by=auth.uid());
grant select,insert,update on public.controls_jobs to authenticated;
create table public.controls_artifacts (
 id uuid primary key default gen_random_uuid(), project_code text not null references projects(code),
 version_id uuid not null references controls_versions(id), filename text not null, format text not null check(format in ('xlsx','pdf')),
 created_at timestamptz not null default now()
);
alter table public.controls_artifacts enable row level security;
create policy controls_artifacts_read on public.controls_artifacts for select to authenticated using(has_project_access(project_code));
create policy controls_artifacts_insert on public.controls_artifacts for insert to authenticated with check(has_project_access(project_code) and exists(select 1 from controls_versions v where v.id=version_id and v.project_code=controls_artifacts.project_code));
grant select,insert on public.controls_artifacts to authenticated;
'''
(ROOT / 'supabase/migrations/202609130001_project_controls.sql').write_text(sql, encoding='utf-8')
