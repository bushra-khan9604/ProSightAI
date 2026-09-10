-- Rebuildable semantic projections. Canonical structured facts remain in
-- construction; the legacy prosight schema and its vectors are not modified.

begin;

create schema semantic;
revoke all on schema semantic from public, anon, service_role;

create table semantic.semantic_projection_versions (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    source_entity_type text not null,
    version_no integer not null check (version_no > 0),
    renderer_name text not null,
    renderer_version text not null,
    projection_specification jsonb not null check (jsonb_typeof(projection_specification) = 'object'),
    specification_checksum text not null check (specification_checksum ~ '^[0-9a-f]{64}$'),
    status text not null default 'active' check (status in ('active','superseded','retired')),
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    unique (organization_id, source_entity_type, version_no),
    unique (organization_id, id)
);

create table semantic.semantic_documents (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    source_entity_type text not null check (source_entity_type in (
        'project_summary','risk','claim','contract_notice','rfi',
        'nonconformance_report','daily_report','meeting','action_item',
        'safety_incident','document_section','handover_observation'
    )),
    source_entity_id uuid not null,
    construction_document_id uuid,
    document_revision_id uuid,
    title text not null check (length(btrim(title)) > 0),
    body text not null check (length(btrim(body)) > 0),
    language_code text not null default 'en' check (language_code ~ '^[a-z]{2}(-[A-Z]{2})?$'),
    projection_version_id uuid not null,
    projection_version integer not null check (projection_version > 0),
    content_checksum text not null check (content_checksum ~ '^[0-9a-f]{64}$'),
    approval_status text not null check (approval_status in ('approved','withdrawn','superseded','rejected')),
    index_status text not null default 'pending' check (index_status in ('pending','ready','failed','disabled')),
    approved_at timestamptz,
    superseded_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    search_vector tsvector generated always as (
        to_tsvector('english'::regconfig, coalesce(title, '') || ' ' || coalesce(body, ''))
    ) stored,
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, projection_version_id)
        references semantic.semantic_projection_versions(organization_id, id) on delete restrict,
    foreign key (organization_id, construction_document_id)
        references construction.documents(organization_id, id) on delete cascade,
    foreign key (organization_id, document_revision_id)
        references construction.document_revisions(organization_id, id) on delete cascade,
    foreign key (organization_id, project_id, construction_document_id)
        references construction.documents(organization_id, project_id, id),
    foreign key (organization_id, project_id, document_revision_id)
        references construction.document_revisions(organization_id, project_id, id),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check ((construction_document_id is null) = (document_revision_id is null)),
    check (approval_status <> 'approved' or approved_at is not null)
);

create unique index semantic_documents_projection_identity_idx
    on semantic.semantic_documents (
        organization_id, source_entity_type, source_entity_id,
        projection_version, content_checksum
    );

create table semantic.semantic_chunks (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    semantic_document_id uuid not null,
    construction_document_id uuid,
    document_revision_id uuid,
    source_entity_type text not null,
    source_entity_id uuid not null,
    source_file_id uuid,
    import_batch_id uuid,
    storage_bucket text,
    storage_object_path text,
    page_start integer check (page_start is null or page_start > 0),
    page_end integer check (page_end is null or page_end > 0),
    sheet_name text,
    row_start bigint check (row_start is null or row_start > 0),
    row_end bigint check (row_end is null or row_end > 0),
    heading_path text[] not null default array[]::text[],
    chunk_ordinal integer not null check (chunk_ordinal >= 0),
    body text not null check (length(btrim(body)) > 0),
    content_checksum text not null check (content_checksum ~ '^[0-9a-f]{64}$'),
    token_count integer not null check (token_count > 0),
    embedding_model text not null default 'text-embedding-3-small'
        check (embedding_model = 'text-embedding-3-small'),
    embedding_dimensions integer not null default 1536 check (embedding_dimensions = 1536),
    projection_version integer not null check (projection_version > 0),
    chunking_version text not null,
    approval_status text not null check (approval_status in ('approved','withdrawn','superseded','rejected')),
    index_status text not null default 'pending' check (index_status in ('pending','ready','failed','disabled')),
    metadata jsonb not null default '{}'::jsonb,
    embedding extensions.vector(1536),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    search_vector tsvector generated always as (
        to_tsvector('english'::regconfig, coalesce(body, ''))
    ) stored,
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, semantic_document_id)
        references semantic.semantic_documents(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, construction_document_id)
        references construction.documents(organization_id, id) on delete cascade,
    foreign key (organization_id, document_revision_id)
        references construction.document_revisions(organization_id, id) on delete cascade,
    foreign key (organization_id, project_id, construction_document_id)
        references construction.documents(organization_id, project_id, id),
    foreign key (organization_id, project_id, document_revision_id)
        references construction.document_revisions(organization_id, project_id, id),
    foreign key (organization_id, project_scope_id, source_file_id)
        references ingestion.source_files(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, import_batch_id, source_file_id)
        references ingestion.source_files(organization_id, project_scope_id, import_batch_id, id) on delete restrict,
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    unique (organization_id, project_scope_id, semantic_document_id, id),
    check ((construction_document_id is null) = (document_revision_id is null)),
    check ((storage_bucket is null) = (storage_object_path is null)),
    check ((source_file_id is null) = (import_batch_id is null)),
    check (
        storage_bucket is null
        or (
            construction_document_id is not null
            and document_revision_id is not null
        )
    ),
    check (page_end is null or page_start is null or page_end >= page_start),
    check (row_end is null or row_start is null or row_end >= row_start),
    check (
        embedding is null
        or (
            extensions.vector_dims(embedding) = embedding_dimensions
            and extensions.vector_norm(embedding) > 0::double precision
            and extensions.vector_norm(embedding) <= '1.7976931348623157e308'::double precision
        )
    ),
    check (index_status <> 'ready' or embedding is not null)
);

create unique index semantic_chunks_stable_identity_idx
    on semantic.semantic_chunks (
        organization_id, semantic_document_id, projection_version,
        chunking_version, page_start, page_end, sheet_name, row_start, row_end,
        heading_path, chunk_ordinal, content_checksum
    ) nulls not distinct;

create table semantic.semantic_entity_links (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    semantic_document_id uuid not null,
    source_entity_type text not null,
    source_entity_id uuid not null,
    target_entity_type text not null,
    target_entity_id uuid not null,
    relationship_type text not null,
    confidence numeric(7,6) check (confidence is null or confidence between 0 and 1),
    projection_version integer not null check (projection_version > 0),
    status text not null default 'active' check (status in ('active','superseded','rejected')),
    provenance jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, semantic_document_id)
        references semantic.semantic_documents(organization_id, project_scope_id, id) on delete cascade,
    unique (
        organization_id, semantic_document_id, target_entity_type,
        target_entity_id, relationship_type, projection_version
    ),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table semantic.embedding_jobs (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    semantic_document_id uuid not null,
    semantic_chunk_id uuid,
    idempotency_key text not null check (length(btrim(idempotency_key)) > 0),
    status text not null default 'queued'
        check (status in ('queued','running','succeeded','failed','cancelled')),
    priority integer not null default 100,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 5 check (max_attempts between 1 and 20),
    embedding_model text not null default 'text-embedding-3-small'
        check (embedding_model = 'text-embedding-3-small'),
    embedding_dimensions integer not null default 1536 check (embedding_dimensions = 1536),
    projection_version integer not null check (projection_version > 0),
    chunking_version text not null,
    chunk_count integer not null check (chunk_count > 0),
    payload_checksum text not null check (payload_checksum ~ '^[0-9a-f]{64}$'),
    claimed_by text,
    claimed_at timestamptz,
    lease_expires_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    error_code text,
    error_detail jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, semantic_document_id)
        references semantic.semantic_documents(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, semantic_chunk_id)
        references semantic.semantic_chunks(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, semantic_document_id, semantic_chunk_id)
        references semantic.semantic_chunks(organization_id, project_scope_id, semantic_document_id, id) on delete cascade,
    unique (organization_id, idempotency_key),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check (attempt_count <= max_attempts),
    check (lease_expires_at is null or claimed_at is null or lease_expires_at >= claimed_at),
    check (completed_at is null or started_at is null or completed_at >= started_at)
);

create or replace function construction_private.reject_projection_version_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'projection versions are immutable' using errcode = '55000';
    end if;
    if (to_jsonb(new) - 'status') <> (to_jsonb(old) - 'status') then
        raise exception 'projection version content is immutable' using errcode = '55000';
    end if;
    if old.status = 'active' and new.status not in ('active','superseded','retired') then
        raise exception 'invalid projection version status transition' using errcode = '23514';
    elsif old.status in ('superseded','retired') and new.status <> old.status then
        raise exception 'terminal projection version status is immutable' using errcode = '23514';
    end if;
    return new;
end;
$$;

create trigger semantic_projection_versions_immutable
before update or delete on semantic.semantic_projection_versions
for each row execute function construction_private.reject_projection_version_mutation();

create or replace function construction_private.validate_semantic_document_source()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    version_row semantic.semantic_projection_versions%rowtype;
begin
    select * into strict version_row
    from semantic.semantic_projection_versions version
    where version.organization_id = new.organization_id
      and version.id = new.projection_version_id;

    if version_row.source_entity_type <> new.source_entity_type
       or version_row.version_no <> new.projection_version then
        raise exception 'semantic document does not match its projection version'
            using errcode = '23514';
    end if;

    if (new.approval_status = 'approved' or new.index_status = 'ready')
       and version_row.status <> 'active' then
        raise exception 'only an active projection version can be approved or indexed'
            using errcode = '23514';
    end if;

    if (new.approval_status = 'approved' or new.index_status = 'ready')
       and new.document_revision_id is not null and not exists (
        select 1
        from construction.document_revisions revision
        where revision.organization_id = new.organization_id
          and revision.id = new.document_revision_id
          and revision.document_id = new.construction_document_id
          and revision.project_id is not distinct from new.project_id
          and revision.status = 'approved'
    ) then
        raise exception 'only an approved document revision in the same scope may be projected'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

create trigger semantic_documents_validate_source
before insert or update on semantic.semantic_documents
for each row execute function construction_private.validate_semantic_document_source();

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

create trigger semantic_chunks_validate_and_sync
before insert or update on semantic.semantic_chunks
for each row execute function construction_private.validate_and_sync_semantic_chunk();

create or replace function construction_private.disable_revoked_semantic_projection()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if old.status = 'approved' and new.status <> 'approved' then
        update semantic.semantic_documents
        set approval_status = case
                when new.status = 'superseded' then 'superseded'
                when new.status = 'rejected' then 'rejected'
                else 'withdrawn'
            end,
            index_status = 'disabled',
            updated_at = now()
        where organization_id = new.organization_id
          and document_revision_id = new.id;

        update semantic.semantic_chunks
        set approval_status = case
                when new.status = 'superseded' then 'superseded'
                when new.status = 'rejected' then 'rejected'
                else 'withdrawn'
            end,
            index_status = 'disabled',
            updated_at = now()
        where organization_id = new.organization_id
          and document_revision_id = new.id;
    end if;
    return new;
end;
$$;

create trigger document_revisions_disable_semantic
after update of status on construction.document_revisions
for each row execute function construction_private.disable_revoked_semantic_projection();

revoke execute on function construction_private.reject_projection_version_mutation() from public, anon, authenticated, service_role;
revoke execute on function construction_private.validate_semantic_document_source() from public, anon, authenticated, service_role;
revoke execute on function construction_private.validate_and_sync_semantic_chunk() from public, anon, authenticated, service_role;
revoke execute on function construction_private.disable_revoked_semantic_projection() from public, anon, authenticated, service_role;

create index semantic_documents_search_gin_idx
    on semantic.semantic_documents using gin (search_vector);
create index semantic_chunks_search_gin_idx
    on semantic.semantic_chunks using gin (search_vector);
create index semantic_chunks_embedding_hnsw_idx
    on semantic.semantic_chunks using hnsw (embedding extensions.vector_cosine_ops)
    with (m = 16, ef_construction = 64);
create index semantic_documents_scope_filter_idx
    on semantic.semantic_documents (
        organization_id, project_id, approval_status, index_status,
        source_entity_type, projection_version
    );
create index semantic_documents_active_idx
    on semantic.semantic_documents (organization_id, project_id, source_entity_type, updated_at desc)
    where approval_status = 'approved' and index_status = 'ready';
create index semantic_chunks_scope_filter_idx
    on semantic.semantic_chunks (
        organization_id, project_id, approval_status, index_status,
        embedding_model, source_entity_type, projection_version
    );
create index semantic_chunks_active_idx
    on semantic.semantic_chunks (organization_id, project_id, semantic_document_id, chunk_ordinal)
    where approval_status = 'approved' and index_status = 'ready';
create index semantic_chunks_source_file_idx
    on semantic.semantic_chunks (organization_id, source_file_id)
    where source_file_id is not null;
create index semantic_chunks_import_batch_idx
    on semantic.semantic_chunks (organization_id, import_batch_id)
    where import_batch_id is not null;
create index semantic_entity_links_target_idx
    on semantic.semantic_entity_links (organization_id, project_id, target_entity_type, target_entity_id)
    where status = 'active';
create index embedding_jobs_claim_idx
    on semantic.embedding_jobs (organization_id, priority, created_at, id)
    where status = 'queued';
create index embedding_jobs_expired_lease_idx
    on semantic.embedding_jobs (organization_id, lease_expires_at)
    where status = 'running';

create or replace function semantic.claim_embedding_job(
    worker_id text,
    lease_duration interval default interval '5 minutes'
)
returns setof semantic.embedding_jobs
language sql
security invoker
set search_path = ''
as $$
    update semantic.embedding_jobs job
    set status = 'running',
        claimed_by = worker_id,
        claimed_at = now(),
        lease_expires_at = now() + lease_duration,
        started_at = coalesce(job.started_at, now()),
        attempt_count = job.attempt_count + 1,
        updated_at = now()
    where job.id = (
        select candidate.id
        from semantic.embedding_jobs candidate
        where candidate.status = 'queued'
          and candidate.attempt_count < candidate.max_attempts
        order by candidate.priority, candidate.created_at, candidate.id
        for update skip locked
        limit 1
    )
    returning job.*;
$$;

create or replace function construction_private.publish_chunk_embeddings_internal(
    requested_organization_id uuid,
    requested_embedding_job_id uuid,
    requested_chunks jsonb,
    requested_idempotency_key text
)
returns table (
    status text,
    published_embedding_job_id uuid,
    chunk_count integer
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    actor_id uuid := (select auth.uid());
    document_row semantic.semantic_documents%rowtype;
    projection_row semantic.semantic_projection_versions%rowtype;
    job_row semantic.embedding_jobs%rowtype;
    existing_chunk semantic.semantic_chunks%rowtype;
    item jsonb;
    chunk_data jsonb;
    batch_document_id uuid;
    batch_project_id uuid;
    batch_projection_version integer;
    batch_chunking_version text;
    batch_embedding_model text;
    batch_embedding_dimensions integer;
    supplied_chunk_count integer;
    canonical_payload_checksum text;
    chunk_id uuid;
    chunk_body text;
    chunk_embedding extensions.vector(1536);
    job_match_count integer;
begin
    if actor_id is null then
        raise exception 'authentication is required' using errcode = '42501';
    end if;
    if requested_organization_id is null or requested_embedding_job_id is null then
        raise exception 'organization and embedding job identifiers are required'
            using errcode = '22023';
    end if;
    if requested_idempotency_key is null or btrim(requested_idempotency_key) = '' then
        raise exception 'idempotency key is required' using errcode = '22023';
    end if;
    if not construction_private.can_manage_org(requested_organization_id) then
        raise exception 'an active organization owner, admin, or manager must publish embeddings'
            using errcode = '42501';
    end if;
    if pg_catalog.jsonb_typeof(requested_chunks) <> 'array'
       or pg_catalog.jsonb_array_length(requested_chunks) = 0 then
        raise exception 'a non-empty JSON array of chunk embeddings is required'
            using errcode = '22023';
    end if;

    supplied_chunk_count := pg_catalog.jsonb_array_length(requested_chunks);
    if supplied_chunk_count > 1000 then
        raise exception 'an embedding publication is limited to 1000 chunks'
            using errcode = '54000';
    end if;

    if exists (
        select 1
        from pg_catalog.jsonb_array_elements(requested_chunks) payload(item)
        where pg_catalog.jsonb_typeof(payload.item) <> 'object'
           or pg_catalog.jsonb_typeof(payload.item -> 'chunk') <> 'object'
           or pg_catalog.jsonb_typeof(payload.item -> 'embedding') <> 'array'
    ) then
        raise exception 'every payload item must contain chunk object and embedding array'
            using errcode = '22023';
    end if;

    if exists (
        select 1
        from pg_catalog.jsonb_array_elements(requested_chunks) payload(item)
        group by ((payload.item -> 'chunk' ->> 'id')::uuid)
        having count(*) > 1
    ) then
        raise exception 'an embedding publication cannot contain duplicate chunk identifiers'
            using errcode = '23505';
    end if;

    select
        (payload.item -> 'chunk' ->> 'semantic_document_id')::uuid,
        nullif(payload.item -> 'chunk' ->> 'project_id', '')::uuid,
        (payload.item -> 'chunk' ->> 'projection_version')::integer,
        payload.item -> 'chunk' ->> 'chunking_version',
        payload.item -> 'chunk' ->> 'embedding_model',
        (payload.item -> 'chunk' ->> 'embedding_dimensions')::integer
    into strict
        batch_document_id,
        batch_project_id,
        batch_projection_version,
        batch_chunking_version,
        batch_embedding_model,
        batch_embedding_dimensions
    from pg_catalog.jsonb_array_elements(requested_chunks) payload(item)
    limit 1;

    if batch_document_id is null
       or batch_projection_version is null or batch_projection_version <= 0
       or nullif(btrim(batch_chunking_version), '') is null
       or batch_embedding_model <> 'text-embedding-3-small'
       or batch_embedding_dimensions <> 1536 then
        raise exception 'embedding batch version, chunking, model, or dimension contract is invalid'
            using errcode = '23514';
    end if;

    if exists (
        select 1
        from pg_catalog.jsonb_array_elements(requested_chunks) payload(item)
        where (payload.item -> 'chunk' ->> 'organization_id')::uuid <> requested_organization_id
           or (payload.item -> 'chunk' ->> 'semantic_document_id')::uuid <> batch_document_id
           or nullif(payload.item -> 'chunk' ->> 'project_id', '')::uuid is distinct from batch_project_id
           or (payload.item -> 'chunk' ->> 'projection_version')::integer <> batch_projection_version
           or payload.item -> 'chunk' ->> 'chunking_version' <> batch_chunking_version
           or payload.item -> 'chunk' ->> 'embedding_model' <> batch_embedding_model
           or (payload.item -> 'chunk' ->> 'embedding_dimensions')::integer <> batch_embedding_dimensions
           or payload.item -> 'chunk' ->> 'approval_status' <> 'approved'
           or payload.item -> 'chunk' ->> 'index_status' <> 'pending'
           or pg_catalog.jsonb_array_length(payload.item -> 'embedding') <> 1536
    ) then
        raise exception 'all chunks must be one approved pending document/project/version/model batch'
            using errcode = '23514';
    end if;

    select pg_catalog.encode(
        extensions.digest(
            pg_catalog.convert_to(
                pg_catalog.jsonb_agg(payload.item order by payload.item -> 'chunk' ->> 'id')::text,
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    )
    into strict canonical_payload_checksum
    from pg_catalog.jsonb_array_elements(requested_chunks) payload(item);

    select * into strict document_row
    from semantic.semantic_documents document
    where document.organization_id = requested_organization_id
      and document.id = batch_document_id
    for update;

    if document_row.project_id is distinct from batch_project_id
       or document_row.projection_version <> batch_projection_version
       or document_row.approval_status <> 'approved'
       or document_row.index_status not in ('pending','ready') then
        raise exception 'semantic document scope, version, approval, or index state is invalid'
            using errcode = '23514';
    end if;

    select * into strict projection_row
    from semantic.semantic_projection_versions projection
    where projection.organization_id = requested_organization_id
      and projection.id = document_row.projection_version_id
    for share;

    if projection_row.status <> 'active'
       or projection_row.source_entity_type <> document_row.source_entity_type
       or projection_row.version_no <> document_row.projection_version
       or projection_row.version_no <> batch_projection_version then
        raise exception 'embedding publication requires the active bound projection version'
            using errcode = '23514';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            requested_organization_id::text || ':' || requested_idempotency_key,
            0
        )
    );

    select count(distinct existing.id)
    into strict job_match_count
    from semantic.embedding_jobs existing
    where existing.id = requested_embedding_job_id
       or (
           existing.organization_id = requested_organization_id
           and existing.idempotency_key = requested_idempotency_key
       );
    if job_match_count > 1 then
        raise exception 'embedding job id and idempotency key identify different jobs'
            using errcode = '23505';
    end if;

    select * into job_row
    from semantic.embedding_jobs existing
    where existing.id = requested_embedding_job_id
       or (
           existing.organization_id = requested_organization_id
           and existing.idempotency_key = requested_idempotency_key
       )
    for update;

    if found then
        if job_row.id <> requested_embedding_job_id
           or job_row.organization_id <> requested_organization_id
           or job_row.idempotency_key <> requested_idempotency_key
           or job_row.semantic_document_id <> batch_document_id
           or job_row.project_id is distinct from batch_project_id
           or job_row.projection_version <> batch_projection_version
           or job_row.chunking_version <> batch_chunking_version
           or job_row.embedding_model <> batch_embedding_model
           or job_row.embedding_dimensions <> batch_embedding_dimensions
           or job_row.chunk_count <> supplied_chunk_count
           or job_row.payload_checksum <> canonical_payload_checksum then
            raise exception 'embedding job is already bound to a different immutable batch'
                using errcode = '23505';
        end if;

        if job_row.status = 'succeeded' then
            if (
                select count(*)
                from pg_catalog.jsonb_array_elements(requested_chunks) payload(item)
                join semantic.semantic_chunks chunk
                  on chunk.organization_id = requested_organization_id
                 and chunk.id = (payload.item -> 'chunk' ->> 'id')::uuid
                 and chunk.semantic_document_id = batch_document_id
                 and chunk.index_status = 'ready'
                 and chunk.content_checksum = payload.item -> 'chunk' ->> 'content_checksum'
            ) <> supplied_chunk_count then
                raise exception 'succeeded embedding job does not match ready chunk state'
                    using errcode = '55000';
            end if;
            return query select 'already_succeeded'::text, job_row.id, supplied_chunk_count;
            return;
        end if;
        if job_row.status = 'cancelled' or job_row.attempt_count >= job_row.max_attempts then
            raise exception 'embedding job cannot be retried in its current state'
                using errcode = '55000';
        end if;

        update semantic.embedding_jobs
        set status = 'running',
            attempt_count = attempt_count + 1,
            claimed_by = actor_id::text,
            claimed_at = now(),
            lease_expires_at = null,
            started_at = coalesce(started_at, now()),
            completed_at = null,
            error_code = null,
            error_detail = null,
            updated_at = now()
        where id = job_row.id
        returning * into job_row;
    else
        insert into semantic.embedding_jobs (
            id, organization_id, project_id, semantic_document_id,
            idempotency_key, status, attempt_count, embedding_model,
            embedding_dimensions, projection_version, chunking_version,
            chunk_count, payload_checksum, claimed_by, claimed_at, started_at
        ) values (
            requested_embedding_job_id, requested_organization_id, batch_project_id,
            batch_document_id, requested_idempotency_key, 'running', 1,
            batch_embedding_model, batch_embedding_dimensions,
            batch_projection_version, batch_chunking_version,
            supplied_chunk_count, canonical_payload_checksum,
            actor_id::text, now(), now()
        )
        returning * into job_row;
    end if;

    for item in
        select payload.item
        from pg_catalog.jsonb_array_elements(requested_chunks) payload(item)
        order by payload.item -> 'chunk' ->> 'id'
    loop
        chunk_data := item -> 'chunk';
        chunk_id := (chunk_data ->> 'id')::uuid;
        chunk_body := coalesce(chunk_data ->> 'body', chunk_data ->> 'text');
        if nullif(btrim(chunk_body), '') is null
           or chunk_data ->> 'content_checksum' <> pg_catalog.encode(
                extensions.digest(pg_catalog.convert_to(chunk_body, 'UTF8'), 'sha256'), 'hex'
              ) then
            raise exception 'chunk % body checksum is invalid', chunk_id
                using errcode = '23514';
        end if;

        chunk_embedding := (item -> 'embedding')::text::extensions.vector(1536);
        if extensions.vector_dims(chunk_embedding) <> 1536
           or extensions.vector_norm(chunk_embedding) <= 0::double precision
           or extensions.vector_norm(chunk_embedding) > '1.7976931348623157e308'::double precision then
            raise exception 'chunk % embedding must contain 1536 finite non-zero values', chunk_id
                using errcode = '23514';
        end if;

        if exists (
            select 1 from semantic.semantic_chunks cross_tenant
            where cross_tenant.id = chunk_id
              and cross_tenant.organization_id <> requested_organization_id
        ) then
            raise exception 'chunk % is already owned by another organization', chunk_id
                using errcode = '23503';
        end if;

        select * into existing_chunk
        from semantic.semantic_chunks chunk
        where chunk.organization_id = requested_organization_id
          and chunk.id = chunk_id
        for update;

        if found then
            if existing_chunk.semantic_document_id <> batch_document_id
               or existing_chunk.project_id is distinct from batch_project_id
               or existing_chunk.source_entity_type <> chunk_data ->> 'source_entity_type'
               or existing_chunk.source_entity_id <> (chunk_data ->> 'source_entity_id')::uuid
               or existing_chunk.construction_document_id is distinct from nullif(chunk_data ->> 'construction_document_id', '')::uuid
               or existing_chunk.document_revision_id is distinct from nullif(chunk_data ->> 'document_revision_id', '')::uuid
               or existing_chunk.source_file_id is distinct from nullif(chunk_data ->> 'source_file_id', '')::uuid
               or existing_chunk.import_batch_id is distinct from nullif(chunk_data ->> 'import_batch_id', '')::uuid
               or existing_chunk.storage_bucket is distinct from chunk_data ->> 'storage_bucket'
               or existing_chunk.storage_object_path is distinct from chunk_data ->> 'storage_object_path'
               or existing_chunk.chunk_ordinal <> (chunk_data ->> 'chunk_ordinal')::integer
               or existing_chunk.content_checksum <> chunk_data ->> 'content_checksum'
               or existing_chunk.projection_version <> batch_projection_version
               or existing_chunk.chunking_version <> batch_chunking_version
               or existing_chunk.embedding_model <> batch_embedding_model
               or existing_chunk.embedding_dimensions <> batch_embedding_dimensions
               or existing_chunk.approval_status <> 'approved'
               or existing_chunk.index_status <> 'pending'
               or existing_chunk.embedding is not null then
                raise exception 'chunk % is already bound to different or non-pending content', chunk_id
                    using errcode = '23505';
            end if;
        else
            insert into semantic.semantic_chunks (
                id, organization_id, project_id, semantic_document_id,
                construction_document_id, document_revision_id,
                source_entity_type, source_entity_id, source_file_id, import_batch_id,
                storage_bucket, storage_object_path, page_start, page_end,
                sheet_name, row_start, row_end, heading_path, chunk_ordinal,
                body, content_checksum, token_count, embedding_model,
                embedding_dimensions, projection_version, chunking_version,
                approval_status, index_status, embedding
            ) values (
                chunk_id, requested_organization_id, batch_project_id, batch_document_id,
                nullif(chunk_data ->> 'construction_document_id', '')::uuid,
                nullif(chunk_data ->> 'document_revision_id', '')::uuid,
                chunk_data ->> 'source_entity_type',
                (chunk_data ->> 'source_entity_id')::uuid,
                nullif(chunk_data ->> 'source_file_id', '')::uuid,
                nullif(chunk_data ->> 'import_batch_id', '')::uuid,
                chunk_data ->> 'storage_bucket', chunk_data ->> 'storage_object_path',
                nullif(chunk_data ->> 'page_start', '')::integer,
                nullif(chunk_data ->> 'page_end', '')::integer,
                chunk_data ->> 'sheet_name',
                nullif(chunk_data ->> 'row_start', '')::bigint,
                nullif(chunk_data ->> 'row_end', '')::bigint,
                coalesce(
                    array(select pg_catalog.jsonb_array_elements_text(chunk_data -> 'heading_path')),
                    array[]::text[]
                ),
                (chunk_data ->> 'chunk_ordinal')::integer,
                chunk_body, chunk_data ->> 'content_checksum',
                (chunk_data ->> 'token_count')::integer,
                batch_embedding_model, batch_embedding_dimensions,
                batch_projection_version, batch_chunking_version,
                'approved', 'pending', null
            );
        end if;

        update semantic.semantic_chunks
        set embedding = chunk_embedding,
            index_status = 'ready',
            updated_at = now()
        where organization_id = requested_organization_id
          and id = chunk_id;
    end loop;

    update semantic.semantic_documents
    set index_status = 'ready', updated_at = now()
    where organization_id = requested_organization_id
      and id = batch_document_id;

    update semantic.embedding_jobs
    set status = 'succeeded', completed_at = now(), updated_at = now()
    where organization_id = requested_organization_id
      and id = job_row.id;

    return query select 'succeeded'::text, job_row.id, supplied_chunk_count;
end;
$$;

create or replace function semantic.publish_chunk_embeddings(
    requested_organization_id uuid,
    requested_embedding_job_id uuid,
    requested_chunks jsonb,
    requested_idempotency_key text
)
returns table (
    status text,
    embedding_job_id uuid,
    chunk_count integer
)
language sql
security invoker
set search_path = ''
as $$
    select *
    from construction_private.publish_chunk_embeddings_internal(
        $1, $2, $3, $4
    );
$$;

create or replace function semantic.hybrid_search(
    requested_organization_id uuid,
    requested_project_ids uuid[],
    requested_query_text text,
    requested_query_embedding extensions.vector(1536),
    requested_projection_version integer,
    requested_chunking_version text,
    requested_embedding_model text default 'text-embedding-3-small',
    requested_match_count integer default 20
)
returns table (
    chunk_id uuid,
    semantic_document_id uuid,
    project_id uuid,
    body text,
    metadata jsonb,
    lexical_score double precision,
    semantic_score double precision,
    combined_score double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
    with lexical as (
        select chunk.id,
               ts_rank_cd(chunk.search_vector,
                   websearch_to_tsquery('english'::regconfig, coalesce(requested_query_text, ''))
               )::double precision as score
        from semantic.semantic_chunks chunk
        join semantic.semantic_documents document
          on document.organization_id = chunk.organization_id
         and document.project_scope_id = chunk.project_scope_id
         and document.id = chunk.semantic_document_id
        join semantic.semantic_projection_versions projection
          on projection.organization_id = document.organization_id
         and projection.id = document.projection_version_id
        where chunk.organization_id = requested_organization_id
          and (chunk.project_id is null or requested_project_ids is null or chunk.project_id = any(requested_project_ids))
          and document.organization_id = requested_organization_id
          and (document.project_id is null or requested_project_ids is null or document.project_id = any(requested_project_ids))
          and chunk.approval_status = 'approved'
          and chunk.index_status = 'ready'
          and chunk.embedding_model = requested_embedding_model
          and chunk.embedding_dimensions = 1536
          and chunk.projection_version = requested_projection_version
          and chunk.chunking_version = requested_chunking_version
          and document.approval_status = 'approved'
          and document.index_status = 'ready'
          and document.projection_version = requested_projection_version
          and projection.version_no = requested_projection_version
          and projection.status = 'active'
          and chunk.search_vector @@ websearch_to_tsquery(
              'english'::regconfig, coalesce(requested_query_text, '')
          )
        order by score desc, chunk.id
        limit greatest(requested_match_count * 4, requested_match_count)
    ),
    semantic_candidates as (
        select chunk.id,
               (1 - (chunk.embedding OPERATOR(extensions.<=>) requested_query_embedding))::double precision as score
        from semantic.semantic_chunks chunk
        join semantic.semantic_documents document
          on document.organization_id = chunk.organization_id
         and document.project_scope_id = chunk.project_scope_id
         and document.id = chunk.semantic_document_id
        join semantic.semantic_projection_versions projection
          on projection.organization_id = document.organization_id
         and projection.id = document.projection_version_id
        where chunk.organization_id = requested_organization_id
          and (chunk.project_id is null or requested_project_ids is null or chunk.project_id = any(requested_project_ids))
          and document.organization_id = requested_organization_id
          and (document.project_id is null or requested_project_ids is null or document.project_id = any(requested_project_ids))
          and chunk.approval_status = 'approved'
          and chunk.index_status = 'ready'
          and chunk.embedding_model = requested_embedding_model
          and chunk.embedding_dimensions = 1536
          and chunk.projection_version = requested_projection_version
          and chunk.chunking_version = requested_chunking_version
          and document.approval_status = 'approved'
          and document.index_status = 'ready'
          and document.projection_version = requested_projection_version
          and projection.version_no = requested_projection_version
          and projection.status = 'active'
          and extensions.vector_dims(requested_query_embedding) = 1536
        order by chunk.embedding OPERATOR(extensions.<=>) requested_query_embedding, chunk.id
        limit greatest(requested_match_count * 4, requested_match_count)
    ),
    candidates as (
        select candidate.id,
               max(candidate.lexical_score) as lexical_score,
               max(candidate.semantic_score) as semantic_score
        from (
            select lexical.id, lexical.score as lexical_score, 0::double precision as semantic_score
            from lexical
            union all
            select semantic_candidates.id, 0::double precision, semantic_candidates.score
            from semantic_candidates
        ) candidate
        group by candidate.id
    )
    select chunk.id,
           chunk.semantic_document_id,
           chunk.project_id,
           chunk.body,
           chunk.metadata,
           candidates.lexical_score,
           candidates.semantic_score,
           (0.35 * candidates.lexical_score + 0.65 * candidates.semantic_score) as combined_score
    from candidates
    join semantic.semantic_chunks chunk on chunk.id = candidates.id
    join semantic.semantic_documents document
      on document.organization_id = chunk.organization_id
     and document.project_scope_id = chunk.project_scope_id
     and document.id = chunk.semantic_document_id
    join semantic.semantic_projection_versions projection
      on projection.organization_id = document.organization_id
     and projection.id = document.projection_version_id
    where chunk.organization_id = requested_organization_id
      and (chunk.project_id is null or requested_project_ids is null or chunk.project_id = any(requested_project_ids))
      and document.organization_id = requested_organization_id
      and (document.project_id is null or requested_project_ids is null or document.project_id = any(requested_project_ids))
      and chunk.approval_status = 'approved'
      and chunk.index_status = 'ready'
      and chunk.embedding_model = requested_embedding_model
      and chunk.embedding_dimensions = 1536
      and chunk.projection_version = requested_projection_version
      and chunk.chunking_version = requested_chunking_version
      and document.approval_status = 'approved'
      and document.index_status = 'ready'
      and document.projection_version = requested_projection_version
      and projection.version_no = requested_projection_version
      and projection.status = 'active'
    order by combined_score desc, chunk.id
    limit requested_match_count;
$$;

do $policies$
declare
    target_table text;
begin
    foreach target_table in array array[
        'semantic_documents','semantic_entity_links','embedding_jobs'
    ] loop
        execute format('alter table semantic.%I enable row level security', target_table);
        execute format(
            'create policy tenant_read on semantic.%I for select to authenticated using ((select auth.uid()) is not null and (select construction_private.can_read_project(organization_id, project_id)))',
            target_table
        );
        execute format(
            'create policy tenant_insert on semantic.%I for insert to authenticated with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            target_table
        );
        execute format(
            'create policy tenant_update on semantic.%I for update to authenticated using ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id))) with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            target_table
        );
        execute format(
            'create policy tenant_delete on semantic.%I for delete to authenticated using ((select auth.uid()) is not null and (select construction_private.can_admin_org(organization_id)))',
            target_table
        );
    end loop;
end
$policies$;

alter table semantic.semantic_chunks enable row level security;
create policy tenant_read on semantic.semantic_chunks
for select to authenticated
using (
    (select auth.uid()) is not null
    and (select construction_private.can_read_project(organization_id, project_id))
);

alter table semantic.semantic_projection_versions enable row level security;
create policy tenant_read on semantic.semantic_projection_versions
for select to authenticated
using ((select auth.uid()) is not null and (select construction_private.is_org_member(organization_id)));
create policy tenant_insert on semantic.semantic_projection_versions
for insert to authenticated
with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)));
create policy tenant_update on semantic.semantic_projection_versions
for update to authenticated
using ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))
with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)));

-- Foreign-key leading indexes not already covered by scope/filter indexes.
do $indexes$
declare
    foreign_key record;
begin
    for foreign_key in
        select
            constraint_row.conrelid::regclass as relation_name,
            constraint_row.conname,
            string_agg(quote_ident(attribute_row.attname), ', ' order by key_row.ordinality) as column_list
        from pg_constraint constraint_row
        join pg_namespace namespace_row on namespace_row.oid = constraint_row.connamespace
        cross join lateral unnest(constraint_row.conkey) with ordinality as key_row(attnum, ordinality)
        join pg_attribute attribute_row
          on attribute_row.attrelid = constraint_row.conrelid
         and attribute_row.attnum = key_row.attnum
        where constraint_row.contype = 'f'
          and namespace_row.nspname = 'semantic'
        group by constraint_row.conrelid, constraint_row.conname
    loop
        execute format(
            'create index if not exists %I on %s (%s)',
            left(foreign_key.conname || '_idx', 63),
            foreign_key.relation_name,
            foreign_key.column_list
        );
    end loop;
end
$indexes$;

grant usage on schema semantic to authenticated;
revoke all on all tables in schema semantic from public, anon, authenticated, service_role;
grant select, insert, update, delete on semantic.semantic_documents,
    semantic.semantic_entity_links, semantic.embedding_jobs to authenticated;
grant select on semantic.semantic_chunks to authenticated;
grant select, insert, update on semantic.semantic_projection_versions to authenticated;
revoke execute on function construction_private.publish_chunk_embeddings_internal(uuid, uuid, jsonb, text)
    from public, anon, authenticated, service_role;
grant execute on function construction_private.publish_chunk_embeddings_internal(uuid, uuid, jsonb, text)
    to authenticated;
revoke execute on function semantic.publish_chunk_embeddings(uuid, uuid, jsonb, text)
    from public, anon, service_role;
grant execute on function semantic.publish_chunk_embeddings(uuid, uuid, jsonb, text)
    to authenticated;
revoke execute on function semantic.claim_embedding_job(text, interval) from public, anon, service_role;
revoke execute on function semantic.hybrid_search(uuid, uuid[], text, extensions.vector, integer, text, text, integer)
    from public, anon, service_role;
grant execute on function semantic.claim_embedding_job(text, interval) to authenticated;
grant execute on function semantic.hybrid_search(uuid, uuid[], text, extensions.vector, integer, text, text, integer)
    to authenticated;
alter default privileges in schema semantic revoke all on tables from public, anon, authenticated, service_role;
alter default privileges in schema semantic revoke execute on functions from public, anon, authenticated, service_role;

comment on schema semantic is
'Derived, versioned, approved semantic projections with typed provenance, hybrid full-text/vector search, and rebuildable embedding jobs.';

commit;
