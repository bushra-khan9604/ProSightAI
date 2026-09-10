-- Stored generated project_scope_id is not populated in a BEFORE trigger.
create or replace function construction_private.validate_and_sync_semantic_chunk()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    document_row semantic.semantic_documents%rowtype;
begin
    select * into strict document_row
    from semantic.semantic_documents document
    where document.organization_id = new.organization_id
      and document.project_scope_id = coalesce(
          new.project_id,
          '00000000-0000-0000-0000-000000000000'::uuid
      )
      and document.id = new.semantic_document_id;

    if new.source_entity_type <> document_row.source_entity_type
       or new.source_entity_id <> document_row.source_entity_id
       or new.construction_document_id is distinct from document_row.construction_document_id
       or new.document_revision_id is distinct from document_row.document_revision_id
       or new.projection_version <> document_row.projection_version
       or new.approval_status <> document_row.approval_status then
        raise exception 'semantic chunk scope, provenance, version, and approval must match its document'
            using errcode = '23514';
    end if;

    new.metadata := jsonb_build_object(
        'organization_id', new.organization_id,
        'project_id', new.project_id,
        'semantic_document_id', new.semantic_document_id,
        'document_id', new.construction_document_id,
        'document_revision_id', new.document_revision_id,
        'source_entity_type', new.source_entity_type,
        'source_entity_id', new.source_entity_id,
        'source_file_id', new.source_file_id,
        'import_batch_id', new.import_batch_id,
        'storage_bucket', new.storage_bucket,
        'storage_object_path', new.storage_object_path,
        'page_start', new.page_start,
        'page_end', new.page_end,
        'sheet_name', new.sheet_name,
        'row_start', new.row_start,
        'row_end', new.row_end,
        'heading_path', to_jsonb(new.heading_path),
        'content_checksum', new.content_checksum,
        'token_count', new.token_count,
        'embedding_model', new.embedding_model,
        'embedding_dimensions', new.embedding_dimensions,
        'projection_version', new.projection_version,
        'chunking_version', new.chunking_version,
        'approval_status', new.approval_status,
        'index_status', new.index_status
    );
    return new;
end;
$$;

revoke execute on function construction_private.validate_and_sync_semantic_chunk()
    from public, anon, authenticated, service_role;
