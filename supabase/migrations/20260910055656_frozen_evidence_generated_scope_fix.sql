-- Stored generated columns are recomputed after BEFORE triggers. Ignore the
-- generated project_scope_id while proving the publisher changed only status.
create or replace function construction_private.prevent_frozen_import_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    owning_batch_id uuid;
    owning_batch_status text;
begin
    if tg_table_name in ('source_files','transformation_runs','staged_rows','validation_issues') then
        owning_batch_id := case when tg_op = 'DELETE' then old.import_batch_id else new.import_batch_id end;
    elsif tg_table_name = 'source_sheets' then
        select source_file.import_batch_id into strict owning_batch_id
        from ingestion.source_files source_file
        where source_file.id = case when tg_op = 'DELETE' then old.source_file_id else new.source_file_id end;
    elsif tg_table_name = 'source_columns' then
        select source_file.import_batch_id into strict owning_batch_id
        from ingestion.source_sheets source_sheet
        join ingestion.source_files source_file on source_file.id = source_sheet.source_file_id
        where source_sheet.id = case when tg_op = 'DELETE' then old.source_sheet_id else new.source_sheet_id end;
    elsif tg_table_name = 'staged_cells' then
        select staged_row.import_batch_id into strict owning_batch_id
        from ingestion.staged_rows staged_row
        where staged_row.id = case when tg_op = 'DELETE' then old.staged_row_id else new.staged_row_id end;
    else
        raise exception 'unsupported frozen-import table %', tg_table_name using errcode = '55000';
    end if;

    select batch.status into strict owning_batch_status
    from ingestion.import_batches batch
    where batch.id = owning_batch_id;

    if owning_batch_status in (
        'awaiting_approval','approved','publishing','published','publish_failed','rejected','cancelled'
    ) then
        if tg_table_name = 'staged_rows'
           and tg_op = 'UPDATE'
           and old.status = 'valid'
           and new.status = 'published'
           and (to_jsonb(new) - array['status','project_scope_id'])
               = (to_jsonb(old) - array['status','project_scope_id'])
           and exists (
               select 1
               from ingestion.publish_batches publication
               where publication.import_batch_id = owning_batch_id
                 and publication.status = 'publishing'
           ) then
            return new;
        end if;
        raise exception 'approved or terminal import evidence is immutable'
            using errcode = '55000';
    end if;
    return case when tg_op = 'DELETE' then old else new end;
end;
$$;

revoke execute on function construction_private.prevent_frozen_import_mutation()
    from public, anon, authenticated, service_role;
