-- Prevent employees from bypassing contact masking through the Data API.
create or replace function public.mask_project_payload(project_payload jsonb)
returns jsonb language sql stable security definer set search_path = public
as $$
  select case
    when public.current_app_role() <> 'employee' then project_payload
    else jsonb_set(
      project_payload,
      '{contacts}',
      coalesce((
        select jsonb_agg(
          contact || jsonb_build_object('email', 'restricted', 'mobile', 'restricted')
        )
        from jsonb_array_elements(coalesce(project_payload->'contacts', '[]'::jsonb)) contact
      ), '[]'::jsonb),
      true
    )
  end
$$;

create or replace function public.list_authorized_projects(project_status text default null)
returns table(payload jsonb)
language sql stable security definer set search_path = public
as $$
  select public.mask_project_payload(p.payload)
  from public.projects p
  where public.has_project_access(p.code)
    and (project_status is null or p.status = lower(project_status))
  order by p.planned_start
$$;

create or replace function public.find_authorized_project(search_term text)
returns table(payload jsonb)
language sql stable security definer set search_path = public
as $$
  select public.mask_project_payload(p.payload)
  from public.projects p
  where public.has_project_access(p.code)
    and (p.code ilike '%' || search_term || '%' or p.name ilike '%' || search_term || '%')
  order by (lower(p.code) = lower(search_term)) desc,
           (lower(p.name) = lower(search_term)) desc,
           p.code
  limit 1
$$;

revoke all on function public.mask_project_payload(jsonb) from public, anon, authenticated;
revoke all on function public.list_authorized_projects(text) from public, anon;
revoke all on function public.find_authorized_project(text) from public, anon;
grant execute on function public.list_authorized_projects(text) to authenticated, service_role;
grant execute on function public.find_authorized_project(text) to authenticated, service_role;

-- Authenticated callers use only the masked RPCs for reads. Authors may still
-- update through RLS; trusted approved changes and migration use service_role.
revoke select on table public.projects from authenticated;
grant select(code) on table public.projects to authenticated;
