-- BEFORE triggers cannot rely on stored generated columns being populated.
-- Validate the staged-row scope from project_id instead.
create or replace function construction_private.validate_staged_mapping_binding()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if not exists (
        select 1
        from ingestion.transformation_runs transformation
        join ingestion.mapping_version_sheets sheet_mapping
          on sheet_mapping.organization_id = transformation.organization_id
         and sheet_mapping.mapping_version_id = transformation.mapping_version_id
        where transformation.organization_id = new.organization_id
          and transformation.project_scope_id = coalesce(
              new.project_id,
              '00000000-0000-0000-0000-000000000000'::uuid
          )
          and transformation.id = new.transformation_run_id
          and sheet_mapping.id = new.mapping_version_sheet_id
          and sheet_mapping.target_entity_type = new.target_entity_type
    ) then
        raise exception 'staged row mapping sheet is not bound to its transformation version and target'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

revoke execute on function construction_private.validate_staged_mapping_binding()
    from public, anon, authenticated, service_role;
