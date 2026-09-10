-- Governed, traceable, idempotent import lifecycle.
-- No workbook formula or uploaded value is ever executed by this schema.

begin;

create schema ingestion;
revoke all on schema ingestion from public, anon, service_role;

create table ingestion.mapping_profiles (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    name text not null,
    source_kind text not null,
    description text,
    is_active boolean not null default true,
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    unique (organization_id, name),
    unique (organization_id, id)
);

create table ingestion.mapping_profile_versions (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    mapping_profile_id uuid not null,
    version_no integer not null check (version_no > 0),
    mapping_specification jsonb not null check (jsonb_typeof(mapping_specification) = 'object'),
    mapping_checksum text not null check (mapping_checksum ~ '^[0-9a-f]{64}$'),
    transformation_version text not null,
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    foreign key (organization_id, mapping_profile_id)
        references ingestion.mapping_profiles(organization_id, id) on delete cascade,
    unique (mapping_profile_id, version_no),
    unique (organization_id, id)
);

create table ingestion.mapping_version_sheets (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    mapping_version_id uuid not null,
    sheet_classification text not null check (length(btrim(sheet_classification)) > 0),
    sheet_ordinal integer not null check (sheet_ordinal >= 0),
    source_sheet_matcher jsonb not null default '{}'::jsonb
        check (jsonb_typeof(source_sheet_matcher) = 'object'),
    target_entity_type text not null check (length(btrim(target_entity_type)) > 0),
    mapping_specification jsonb not null check (jsonb_typeof(mapping_specification) = 'object'),
    business_key_columns text[] not null check (cardinality(business_key_columns) > 0),
    formula_policy text not null default 'reject'
        check (formula_policy in ('reject','retain_as_text')),
    created_at timestamptz not null default now(),
    foreign key (organization_id, mapping_version_id)
        references ingestion.mapping_profile_versions(organization_id, id) on delete cascade,
    unique (mapping_version_id, sheet_classification),
    unique (mapping_version_id, sheet_ordinal),
    unique (organization_id, id),
    unique (organization_id, mapping_version_id, id)
);

create table ingestion.import_batches (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    source_kind text not null,
    idempotency_key text not null check (length(btrim(idempotency_key)) > 0),
    status text not null default 'uploaded' check (status in (
        'uploaded','profiling','mapping','validating','review_ready',
        'awaiting_approval','approved','publishing','published','rejected',
        'validation_failed','publish_failed','cancelled'
    )),
    mapping_version_id uuid,
    input_profile_checksum text check (input_profile_checksum is null or input_profile_checksum ~ '^[0-9a-f]{64}$'),
    normalized_preview_checksum text check (normalized_preview_checksum is null or normalized_preview_checksum ~ '^[0-9a-f]{64}$'),
    validation_checksum text check (validation_checksum is null or validation_checksum ~ '^[0-9a-f]{64}$'),
    requester_user_id uuid not null references auth.users(id) on delete restrict,
    requested_at timestamptz not null default now(),
    status_changed_at timestamptz not null default now(),
    published_at timestamptz,
    cancelled_at timestamptz,
    failure_detail jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete restrict,
    foreign key (organization_id, mapping_version_id)
        references ingestion.mapping_profile_versions(organization_id, id) on delete restrict,
    unique (organization_id, idempotency_key),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check ((status = 'published') = (published_at is not null)),
    check ((status = 'cancelled') = (cancelled_at is not null))
);

create table ingestion.source_files (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    import_batch_id uuid not null,
    source_kind text not null,
    original_filename text not null,
    mime_type text,
    byte_size bigint not null check (byte_size > 0),
    checksum_sha256 text not null check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    storage_bucket text,
    storage_object_path text,
    uploaded_by uuid not null references auth.users(id) on delete restrict,
    uploaded_at timestamptz not null default now(),
    verified_at timestamptz,
    foreign key (organization_id, project_id)
        references construction.projects(organization_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    unique (organization_id, source_kind, checksum_sha256),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    unique (organization_id, project_scope_id, import_batch_id, id),
    check ((storage_bucket is null) = (storage_object_path is null))
);

create table ingestion.source_sheets (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    source_file_id uuid not null,
    sheet_name text not null,
    sheet_ordinal integer not null check (sheet_ordinal >= 0),
    row_count bigint not null default 0 check (row_count >= 0),
    column_count integer not null default 0 check (column_count >= 0),
    is_hidden boolean not null default false,
    profile jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, source_file_id)
        references ingestion.source_files(organization_id, project_scope_id, id) on delete cascade,
    unique (source_file_id, sheet_ordinal),
    unique (source_file_id, sheet_name),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table ingestion.source_columns (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    source_sheet_id uuid not null,
    column_ordinal integer not null check (column_ordinal >= 0),
    column_letter text,
    raw_header text,
    normalized_header text,
    inferred_type text,
    null_count bigint not null default 0 check (null_count >= 0),
    formula_count bigint not null default 0 check (formula_count >= 0),
    profile jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, source_sheet_id)
        references ingestion.source_sheets(organization_id, project_scope_id, id) on delete cascade,
    unique (source_sheet_id, column_ordinal),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table ingestion.transformation_runs (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    import_batch_id uuid not null,
    mapping_version_id uuid not null,
    run_number integer not null check (run_number > 0),
    status text not null default 'queued'
        check (status in ('queued','running','succeeded','failed','cancelled')),
    input_profile_checksum text not null check (input_profile_checksum ~ '^[0-9a-f]{64}$'),
    normalized_preview_checksum text check (normalized_preview_checksum is null or normalized_preview_checksum ~ '^[0-9a-f]{64}$'),
    validation_checksum text check (validation_checksum is null or validation_checksum ~ '^[0-9a-f]{64}$'),
    transformation_version text not null,
    row_count bigint not null default 0 check (row_count >= 0),
    started_at timestamptz,
    completed_at timestamptz,
    error_detail jsonb,
    created_by uuid not null references auth.users(id) on delete restrict,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, mapping_version_id)
        references ingestion.mapping_profile_versions(organization_id, id) on delete restrict,
    unique (import_batch_id, run_number),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check (completed_at is null or started_at is null or completed_at >= started_at)
);

create table ingestion.staged_rows (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    import_batch_id uuid not null,
    source_file_id uuid not null,
    source_sheet_id uuid not null,
    transformation_run_id uuid not null,
    mapping_version_sheet_id uuid not null,
    row_number bigint not null check (row_number > 0),
    target_entity_type text not null,
    raw_record jsonb not null check (jsonb_typeof(raw_record) = 'object'),
    normalized_record jsonb not null check (jsonb_typeof(normalized_record) = 'object'),
    business_key jsonb not null check (jsonb_typeof(business_key) = 'object'),
    business_key_checksum text not null check (business_key_checksum ~ '^[0-9a-f]{64}$'),
    raw_row_checksum text not null check (raw_row_checksum ~ '^[0-9a-f]{64}$'),
    normalized_row_checksum text not null check (normalized_row_checksum ~ '^[0-9a-f]{64}$'),
    status text not null default 'staged'
        check (status in ('staged','valid','invalid','published','superseded')),
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, source_file_id)
        references ingestion.source_files(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, source_sheet_id)
        references ingestion.source_sheets(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, transformation_run_id)
        references ingestion.transformation_runs(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, mapping_version_sheet_id)
        references ingestion.mapping_version_sheets(organization_id, id) on delete restrict,
    unique (transformation_run_id, source_sheet_id, row_number, target_entity_type),
    unique (import_batch_id, target_entity_type, business_key_checksum),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table ingestion.staged_cells (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    staged_row_id uuid not null,
    source_column_id uuid not null,
    cell_reference text not null,
    target_field text,
    raw_value jsonb,
    normalized_value jsonb,
    formula_text text,
    formula_present boolean generated always as (formula_text is not null) stored,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, staged_row_id)
        references ingestion.staged_rows(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, source_column_id)
        references ingestion.source_columns(organization_id, project_scope_id, id) on delete restrict,
    unique (staged_row_id, source_column_id),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table ingestion.validation_issues (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    import_batch_id uuid not null,
    transformation_run_id uuid not null,
    staged_row_id uuid,
    staged_cell_id uuid,
    severity text not null check (severity in ('error','warning','info')),
    issue_code text not null,
    message text not null,
    issue_fingerprint text not null check (issue_fingerprint ~ '^[0-9a-f]{64}$'),
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, transformation_run_id)
        references ingestion.transformation_runs(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, staged_row_id)
        references ingestion.staged_rows(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, staged_cell_id)
        references ingestion.staged_cells(organization_id, project_scope_id, id) on delete cascade,
    unique (import_batch_id, issue_fingerprint),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

create table ingestion.approval_records (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    import_batch_id uuid not null,
    mapping_version_id uuid not null,
    transformation_run_id uuid not null,
    requester_user_id uuid not null references auth.users(id) on delete restrict,
    approver_user_id uuid not null references auth.users(id) on delete restrict,
    decision text not null check (decision in ('approved','rejected')),
    validation_checksum text not null check (validation_checksum ~ '^[0-9a-f]{64}$'),
    normalized_preview_checksum text not null check (normalized_preview_checksum ~ '^[0-9a-f]{64}$'),
    decision_reason text,
    decided_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, mapping_version_id)
        references ingestion.mapping_profile_versions(organization_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, transformation_run_id)
        references ingestion.transformation_runs(organization_id, project_scope_id, id) on delete restrict,
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check (requester_user_id <> approver_user_id)
);

create unique index approval_records_one_approval_idx
    on ingestion.approval_records (import_batch_id)
    where decision = 'approved';

create table ingestion.publish_batches (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    import_batch_id uuid not null,
    approval_record_id uuid not null,
    idempotency_key text not null check (length(btrim(idempotency_key)) > 0),
    status text not null check (status in ('publishing','published','failed')),
    attempt_count integer not null default 1 check (attempt_count > 0),
    inserted_count integer not null default 0 check (inserted_count >= 0),
    updated_count integer not null default 0 check (updated_count >= 0),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    error_detail jsonb,
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, approval_record_id)
        references ingestion.approval_records(organization_id, project_scope_id, id) on delete restrict,
    unique (organization_id, import_batch_id),
    unique (organization_id, idempotency_key),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id),
    check (completed_at is null or completed_at >= started_at)
);

create table ingestion.record_lineage (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    project_scope_id uuid generated always as (
        coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) stored,
    publish_batch_id uuid not null,
    import_batch_id uuid not null,
    staged_row_id uuid not null,
    source_file_id uuid not null,
    source_sheet_id uuid not null,
    source_row_number bigint not null check (source_row_number > 0),
    target_schema text not null default 'construction' check (target_schema = 'construction'),
    target_table text not null,
    target_record_id uuid not null,
    operation text not null check (operation in ('insert','update')),
    mapping_version_id uuid not null,
    transformation_run_id uuid not null,
    normalized_row_checksum text not null check (normalized_row_checksum ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_scope_id, publish_batch_id)
        references ingestion.publish_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, import_batch_id)
        references ingestion.import_batches(organization_id, project_scope_id, id) on delete cascade,
    foreign key (organization_id, project_scope_id, staged_row_id)
        references ingestion.staged_rows(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, source_file_id)
        references ingestion.source_files(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, source_sheet_id)
        references ingestion.source_sheets(organization_id, project_scope_id, id) on delete restrict,
    foreign key (organization_id, mapping_version_id)
        references ingestion.mapping_profile_versions(organization_id, id) on delete restrict,
    foreign key (organization_id, project_scope_id, transformation_run_id)
        references ingestion.transformation_runs(organization_id, project_scope_id, id) on delete restrict,
    unique (publish_batch_id, staged_row_id, target_schema, target_table, target_record_id),
    unique (organization_id, id),
    unique (organization_id, project_scope_id, id)
);

-- Only these construction targets and exact business keys are publishable.
-- The registry is private and receives no application DML grants.
create table construction_private.ingestion_publication_targets (
    entity_type text primary key,
    target_table text not null unique,
    business_key_columns text[] not null check (cardinality(business_key_columns) > 0),
    requires_project_id boolean not null,
    check (target_table ~ '^[a-z][a-z0-9_]*$')
);

insert into construction_private.ingestion_publication_targets
    (entity_type, target_table, business_key_columns, requires_project_id)
values
    ('projects','projects',array['organization_id','code'],false),
    ('employees','employees',array['organization_id','employee_number'],false),
    ('activities','activities',array['project_id','activity_code'],true),
    ('invoices','invoices',array['project_id','direction','invoice_number'],true),
    ('risks','risks',array['project_id','risk_number'],true),
    ('rfis','rfis',array['project_id','rfi_number'],true),
    ('nonconformance_reports','nonconformance_reports',array['project_id','ncr_number'],true),
    ('safety_incidents','safety_incidents',array['project_id','incident_number'],true),
    ('daily_reports','daily_reports',array['project_id','report_date','shift_code'],true);

revoke all on construction_private.ingestion_publication_targets
    from public, anon, authenticated, service_role;

create or replace function construction_private.enforce_import_batch_transition()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    allowed_statuses text[];
begin
    if tg_op = 'INSERT' then
        if new.status <> 'uploaded' then
            raise exception 'new import batches must start in uploaded status'
                using errcode = '23514';
        end if;
        new.status_changed_at := coalesce(new.status_changed_at, now());
        return new;
    end if;

    if new.status = old.status then
        return new;
    end if;

    allowed_statuses := case old.status
        when 'uploaded' then array['profiling','cancelled']
        when 'profiling' then array['mapping','validation_failed','cancelled']
        when 'mapping' then array['validating','validation_failed','cancelled']
        when 'validating' then array['review_ready','validation_failed','cancelled']
        when 'review_ready' then array['awaiting_approval','validating','cancelled']
        when 'awaiting_approval' then array['approved','rejected','validating','cancelled']
        when 'approved' then array['publishing','cancelled']
        when 'publishing' then array['published','publish_failed']
        when 'publish_failed' then array['approved','publishing','cancelled']
        when 'validation_failed' then array['profiling','mapping','validating','cancelled']
        else array[]::text[]
    end;

    if not new.status = any (allowed_statuses) then
        raise exception 'invalid import batch transition: % -> %', old.status, new.status
            using errcode = '23514';
    end if;
    if new.status = 'approved' and not exists (
        select 1 from ingestion.approval_records approval
        where approval.organization_id = new.organization_id
          and approval.import_batch_id = new.id
          and approval.decision = 'approved'
    ) then
        raise exception 'approved status requires a bound approval record' using errcode = '23514';
    end if;
    if new.status = 'rejected' and not exists (
        select 1 from ingestion.approval_records approval
        where approval.organization_id = new.organization_id
          and approval.import_batch_id = new.id
          and approval.decision = 'rejected'
    ) then
        raise exception 'rejected status requires a bound rejection record' using errcode = '23514';
    end if;
    if new.status = 'publishing' and not exists (
        select 1 from ingestion.publish_batches publication
        where publication.organization_id = new.organization_id
          and publication.import_batch_id = new.id
          and publication.status = 'publishing'
    ) then
        raise exception 'publishing status requires the controlled publisher' using errcode = '23514';
    end if;
    if new.status = 'published' and not exists (
        select 1 from ingestion.publish_batches publication
        where publication.organization_id = new.organization_id
          and publication.import_batch_id = new.id
          and publication.status = 'published'
    ) then
        raise exception 'published status requires an atomic publication record' using errcode = '23514';
    end if;
    if new.status = 'publish_failed' and not exists (
        select 1 from ingestion.publish_batches publication
        where publication.organization_id = new.organization_id
          and publication.import_batch_id = new.id
          and publication.status = 'failed'
    ) then
        raise exception 'publish_failed status requires a failed publication record' using errcode = '23514';
    end if;
    if new.status = 'cancelled' then
        new.cancelled_at := coalesce(new.cancelled_at, now());
    end if;
    new.status_changed_at := now();
    return new;
end;
$$;

create trigger import_batches_enforce_initial_status
before insert on ingestion.import_batches
for each row execute function construction_private.enforce_import_batch_transition();

create trigger import_batches_enforce_transition
before update of status on ingestion.import_batches
for each row execute function construction_private.enforce_import_batch_transition();

create or replace function construction_private.protect_import_batch_binding()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if new.organization_id <> old.organization_id
       or new.project_id is distinct from old.project_id
       or new.requester_user_id <> old.requester_user_id
       or new.source_kind <> old.source_kind
       or new.idempotency_key <> old.idempotency_key then
        raise exception 'import identity and scope are immutable' using errcode = '55000';
    end if;
    if old.status in (
        'awaiting_approval','approved','publishing','published','publish_failed','rejected','cancelled'
    ) and (
        new.mapping_version_id is distinct from old.mapping_version_id
        or new.input_profile_checksum is distinct from old.input_profile_checksum
        or new.normalized_preview_checksum is distinct from old.normalized_preview_checksum
        or new.validation_checksum is distinct from old.validation_checksum
    ) then
        raise exception 'approved import binding is immutable' using errcode = '55000';
    end if;
    return new;
end;
$$;

create trigger import_batches_protect_binding
before update on ingestion.import_batches
for each row execute function construction_private.protect_import_batch_binding();

create or replace function construction_private.reject_mapping_version_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    raise exception 'mapping version definitions are immutable' using errcode = '55000';
end;
$$;

create trigger mapping_versions_immutable
before update or delete on ingestion.mapping_profile_versions
for each row execute function construction_private.reject_mapping_version_mutation();

create trigger mapping_version_sheets_immutable
before update or delete on ingestion.mapping_version_sheets
for each row execute function construction_private.reject_mapping_version_mutation();

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
          -- Stored generated columns are populated after BEFORE triggers, so
          -- derive the scope from the writable project_id column here.
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

create trigger staged_rows_validate_mapping_binding
before insert or update of organization_id, project_id, transformation_run_id,
    mapping_version_sheet_id, target_entity_type
on ingestion.staged_rows
for each row execute function construction_private.validate_staged_mapping_binding();

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

do $freeze_triggers$
declare
    evidence_table text;
begin
    foreach evidence_table in array array[
        'source_files','source_sheets','source_columns','transformation_runs',
        'staged_rows','staged_cells','validation_issues'
    ] loop
        execute format(
            'create trigger prevent_frozen_import_mutation before update or delete on ingestion.%I for each row execute function construction_private.prevent_frozen_import_mutation()',
            evidence_table
        );
    end loop;
end
$freeze_triggers$;

create or replace function construction_private.reject_approval_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    raise exception 'approval records are append-only' using errcode = '55000';
end;
$$;

create trigger approval_records_append_only
before update or delete on ingestion.approval_records
for each row execute function construction_private.reject_approval_mutation();

create or replace function construction_private.validate_import_approval()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    batch ingestion.import_batches%rowtype;
    run ingestion.transformation_runs%rowtype;
begin
    if (select auth.uid()) is null or new.approver_user_id <> (select auth.uid()) then
        raise exception 'approval actor must be the authenticated user' using errcode = '42501';
    end if;

    select * into strict batch
    from ingestion.import_batches
    where organization_id = new.organization_id
      and project_scope_id = coalesce(new.project_id, '00000000-0000-0000-0000-000000000000'::uuid)
      and id = new.import_batch_id
    for update;

    select * into strict run
    from ingestion.transformation_runs
    where organization_id = new.organization_id
      and project_scope_id = coalesce(new.project_id, '00000000-0000-0000-0000-000000000000'::uuid)
      and id = new.transformation_run_id;

    if batch.status <> 'awaiting_approval'
       or batch.requester_user_id <> new.requester_user_id
       or batch.mapping_version_id is distinct from new.mapping_version_id
       or run.import_batch_id <> batch.id
       or run.mapping_version_id is distinct from new.mapping_version_id
       or run.status <> 'succeeded'
       or run.validation_checksum is distinct from new.validation_checksum
       or run.normalized_preview_checksum is distinct from new.normalized_preview_checksum
       or batch.validation_checksum is distinct from new.validation_checksum
       or batch.normalized_preview_checksum is distinct from new.normalized_preview_checksum then
        raise exception 'approval does not bind the current validated batch, mapping, run, and checksums'
            using errcode = '23514';
    end if;

    if new.decision = 'approved' and exists (
        select 1
        from ingestion.validation_issues issue
        where issue.organization_id = new.organization_id
          and issue.import_batch_id = new.import_batch_id
          and issue.transformation_run_id = new.transformation_run_id
          and issue.severity = 'error'
    ) then
        raise exception 'a batch with validation errors cannot be approved' using errcode = '23514';
    end if;

    return new;
end;
$$;

create trigger approval_records_validate
before insert on ingestion.approval_records
for each row execute function construction_private.validate_import_approval();

create or replace function construction_private.apply_import_approval()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    update ingestion.import_batches
    set status = case new.decision when 'approved' then 'approved' else 'rejected' end,
        updated_at = now()
    where organization_id = new.organization_id
      and id = new.import_batch_id;
    return new;
end;
$$;

create trigger approval_records_apply
after insert on ingestion.approval_records
for each row execute function construction_private.apply_import_approval();

create or replace function construction_private.publish_import_batch_internal(
    requested_batch_id uuid,
    requested_approval_id uuid,
    requested_idempotency_key text
)
returns table (
    status text,
    publish_batch_id uuid,
    inserted_count integer,
    updated_count integer
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    actor_id uuid := (select auth.uid());
    batch ingestion.import_batches%rowtype;
    approval ingestion.approval_records%rowtype;
    publication ingestion.publish_batches%rowtype;
    publication_exists boolean := false;
    staged ingestion.staged_rows%rowtype;
    sheet_mapping ingestion.mapping_version_sheets%rowtype;
    target construction_private.ingestion_publication_targets%rowtype;
    payload jsonb;
    insert_columns text;
    insert_values text;
    conflict_columns text;
    update_assignments text;
    statement_text text;
    target_id uuid;
    inserted boolean;
    inserted_total integer := 0;
    updated_total integer := 0;
    staged_total integer := 0;
    key_column text;
    failure_message text;
begin
    if actor_id is null then
        raise exception 'authentication is required' using errcode = '42501';
    end if;
    if requested_idempotency_key is null or btrim(requested_idempotency_key) = '' then
        raise exception 'idempotency key is required' using errcode = '22023';
    end if;

    select * into strict batch
    from ingestion.import_batches
    where id = requested_batch_id
    for update;

    if not exists (
        select 1
        from construction.organization_members membership
        where membership.organization_id = batch.organization_id
          and membership.user_id = actor_id
          and membership.is_active
          and membership.role in ('owner','admin')
    ) then
        raise exception 'an active organization owner or admin must publish imports'
            using errcode = '42501';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            batch.organization_id::text || ':' || requested_idempotency_key,
            0
        )
    );

    if exists (
        select 1
        from ingestion.publish_batches existing
        where existing.organization_id = batch.organization_id
          and existing.idempotency_key = requested_idempotency_key
          and existing.import_batch_id <> batch.id
    ) then
        raise exception 'idempotency key is already bound to another import batch'
            using errcode = '23505';
    end if;

    select * into publication
    from ingestion.publish_batches existing
    where existing.organization_id = batch.organization_id
      and (existing.import_batch_id = batch.id
           or existing.idempotency_key = requested_idempotency_key)
    for update;

    publication_exists := found;

    if publication_exists and publication.idempotency_key <> requested_idempotency_key then
        raise exception 'import batch is already bound to a different publication idempotency key'
            using errcode = '23505';
    end if;

    if publication_exists and publication.status = 'published' then
        return query select 'already_published'::text, publication.id,
            publication.inserted_count, publication.updated_count;
        return;
    end if;

    select * into strict approval
    from ingestion.approval_records approval_row
    where approval_row.organization_id = batch.organization_id
      and approval_row.project_scope_id = batch.project_scope_id
      and approval_row.id = requested_approval_id;

    if approval.import_batch_id <> batch.id
       or approval.decision <> 'approved'
       or approval.mapping_version_id is distinct from batch.mapping_version_id
       or approval.requester_user_id <> batch.requester_user_id
       or approval.validation_checksum is distinct from batch.validation_checksum
       or approval.normalized_preview_checksum is distinct from batch.normalized_preview_checksum
       or batch.status not in ('approved','publish_failed')
       or exists (
           select 1
           from ingestion.validation_issues issue
           where issue.organization_id = batch.organization_id
             and issue.import_batch_id = batch.id
             and issue.transformation_run_id = approval.transformation_run_id
             and issue.severity = 'error'
       ) then
        raise exception 'publication approval binding or validation state is invalid'
            using errcode = '23514';
    end if;

    if publication_exists then
        update ingestion.publish_batches
        set approval_record_id = approval.id,
            idempotency_key = requested_idempotency_key,
            status = 'publishing',
            attempt_count = attempt_count + 1,
            inserted_count = 0,
            updated_count = 0,
            started_at = now(),
            completed_at = null,
            error_detail = null
        where id = publication.id
        returning * into publication;
    else
        insert into ingestion.publish_batches (
            organization_id, project_id, import_batch_id, approval_record_id,
            idempotency_key, status
        ) values (
            batch.organization_id, batch.project_id, batch.id, approval.id,
            requested_idempotency_key, 'publishing'
        ) returning * into publication;
    end if;

    update ingestion.import_batches
    set status = 'publishing', updated_at = now(), failure_detail = null
    where id = batch.id;

    begin
        for staged in
            select staged_row.*
            from ingestion.staged_rows staged_row
            where staged_row.organization_id = batch.organization_id
              and staged_row.project_scope_id = batch.project_scope_id
              and staged_row.import_batch_id = batch.id
              and staged_row.transformation_run_id = approval.transformation_run_id
              and staged_row.status = 'valid'
            order by staged_row.id
            for update
        loop
            staged_total := staged_total + 1;
            select * into strict sheet_mapping
            from ingestion.mapping_version_sheets mapping_row
            where mapping_row.organization_id = batch.organization_id
              and mapping_row.mapping_version_id = approval.mapping_version_id
              and mapping_row.id = staged.mapping_version_sheet_id
              and mapping_row.target_entity_type = staged.target_entity_type;

            select * into strict target
            from construction_private.ingestion_publication_targets target_row
            where target_row.entity_type = staged.target_entity_type;

            if sheet_mapping.business_key_columns <> target.business_key_columns then
                raise exception 'mapping sheet business key does not match the governed publication target for %',
                    target.entity_type using errcode = '23514';
            end if;

            if target.requires_project_id and batch.project_id is null then
                raise exception 'publication target % requires a project-scoped batch', target.entity_type
                    using errcode = '23514';
            end if;

            if not exists (
                select 1
                from pg_catalog.pg_index index_row
                where index_row.indrelid = format('construction.%I', target.target_table)::regclass
                  and index_row.indisunique
                  and index_row.indisvalid
                  and index_row.indpred is null
                  and (
                      select array_agg(attribute_row.attname::text order by key_row.ordinality)
                      from unnest(index_row.indkey) with ordinality key_row(attnum, ordinality)
                      join pg_catalog.pg_attribute attribute_row
                        on attribute_row.attrelid = index_row.indrelid
                       and attribute_row.attnum = key_row.attnum
                      where key_row.ordinality <= index_row.indnkeyatts
                  ) = target.business_key_columns
            ) then
                raise exception 'publication conflict key has no matching usable unique constraint for %', target.entity_type
                    using errcode = '55000';
            end if;

            payload := staged.normalized_record
                || jsonb_build_object('organization_id', batch.organization_id)
                || case
                    when batch.project_id is null then '{}'::jsonb
                    else jsonb_build_object('project_id', batch.project_id)
                   end;
            if not payload ? 'id' or nullif(payload ->> 'id', '') is null then
                payload := payload || jsonb_build_object('id', extensions.gen_random_uuid());
            end if;

            foreach key_column in array target.business_key_columns
            loop
                if not payload ? key_column
                   or not staged.business_key ? key_column
                   or payload -> key_column is distinct from staged.business_key -> key_column then
                    raise exception 'staged business key does not match normalized payload for %.%',
                        staged.target_entity_type, key_column using errcode = '23514';
                end if;
            end loop;

            select
                string_agg(format('%I', attribute.attname), ', ' order by attribute.attnum),
                string_agg(
                    format('(jsonb_populate_record(null::construction.%I, $1)).%I',
                        target.target_table, attribute.attname),
                    ', ' order by attribute.attnum
                ),
                string_agg(format('%I', key_name), ', ' order by key_ordinality)
                    filter (where key_name is not null),
                string_agg(format('%I = excluded.%I', attribute.attname, attribute.attname),
                    ', ' order by attribute.attnum)
                    filter (
                        where not attribute.attname = any(target.business_key_columns)
                          and attribute.attname not in ('id','organization_id','project_id','created_at')
                    )
            into insert_columns, insert_values, conflict_columns, update_assignments
            from pg_attribute attribute
            left join unnest(target.business_key_columns) with ordinality
                as keys(key_name, key_ordinality)
              on keys.key_name = attribute.attname
            where attribute.attrelid = format('construction.%I', target.target_table)::regclass
              and attribute.attnum > 0
              and not attribute.attisdropped
              and attribute.attgenerated = ''
              and payload ? attribute.attname;

            if insert_columns is null or conflict_columns is null then
                raise exception 'publication target definition is invalid for %', target.entity_type
                    using errcode = '55000';
            end if;
            if update_assignments is null then
                update_assignments := 'updated_at = now()';
            end if;

            statement_text := format(
                'insert into construction.%I (%s) select %s '
                || 'on conflict (%s) do update set %s '
                || 'returning id, (xmax = 0)',
                target.target_table,
                insert_columns,
                insert_values,
                conflict_columns,
                update_assignments
            );

            execute statement_text into strict target_id, inserted using payload;
            if inserted then
                inserted_total := inserted_total + 1;
            else
                updated_total := updated_total + 1;
            end if;

            insert into ingestion.record_lineage (
                organization_id, project_id, publish_batch_id, import_batch_id,
                staged_row_id, source_file_id, source_sheet_id, source_row_number,
                target_table, target_record_id, operation, mapping_version_id,
                transformation_run_id, normalized_row_checksum
            ) values (
                batch.organization_id, batch.project_id, publication.id,
                batch.id, staged.id, staged.source_file_id, staged.source_sheet_id,
                staged.row_number, target.target_table, target_id,
                case when inserted then 'insert' else 'update' end,
                approval.mapping_version_id, approval.transformation_run_id,
                staged.normalized_row_checksum
            );

            update ingestion.staged_rows set status = 'published' where id = staged.id;
        end loop;

        if staged_total = 0 then
            raise exception 'approved batch has no valid staged rows' using errcode = '23514';
        end if;

        update ingestion.publish_batches
        set status = 'published', inserted_count = inserted_total,
            updated_count = updated_total, completed_at = now()
        where id = publication.id;
        update ingestion.import_batches
        set status = 'published', published_at = now(), updated_at = now()
        where id = batch.id;

        return query select 'published'::text, publication.id, inserted_total, updated_total;
        return;
    exception when others then
        get stacked diagnostics failure_message = message_text;
        update ingestion.publish_batches
        set status = 'failed', completed_at = now(),
            error_detail = jsonb_build_object('message', failure_message)
        where id = publication.id;
        update ingestion.import_batches
        set status = 'publish_failed', updated_at = now(),
            failure_detail = jsonb_build_object('message', failure_message)
        where id = batch.id;
        return query select 'publish_failed'::text, publication.id, 0, 0;
        return;
    end;
end;
$$;

create or replace function ingestion.publish_import_batch(
    batch_id uuid,
    approval_id uuid,
    idempotency_key text
)
returns table (
    status text,
    publish_batch_id uuid,
    inserted_count integer,
    updated_count integer
)
language sql
security invoker
set search_path = ''
as $$
    select *
    from construction_private.publish_import_batch_internal(batch_id, approval_id, idempotency_key);
$$;

revoke execute on function construction_private.enforce_import_batch_transition() from public, anon, authenticated, service_role;
revoke execute on function construction_private.protect_import_batch_binding() from public, anon, authenticated, service_role;
revoke execute on function construction_private.reject_mapping_version_mutation() from public, anon, authenticated, service_role;
revoke execute on function construction_private.validate_staged_mapping_binding() from public, anon, authenticated, service_role;
revoke execute on function construction_private.prevent_frozen_import_mutation() from public, anon, authenticated, service_role;
revoke execute on function construction_private.reject_approval_mutation() from public, anon, authenticated, service_role;
revoke execute on function construction_private.validate_import_approval() from public, anon, authenticated, service_role;
revoke execute on function construction_private.apply_import_approval() from public, anon, authenticated, service_role;
revoke execute on function construction_private.publish_import_batch_internal(uuid, uuid, text) from public, anon, authenticated, service_role;
grant execute on function construction_private.publish_import_batch_internal(uuid, uuid, text) to authenticated;
revoke execute on function ingestion.publish_import_batch(uuid, uuid, text) from public, anon, service_role;
grant execute on function ingestion.publish_import_batch(uuid, uuid, text) to authenticated;

-- Tenant/project policies. Publication and lineage tables are intentionally
-- read-only to authenticated clients; only the controlled publisher writes them.
do $policies$
declare
    target_table text;
begin
    foreach target_table in array array[
        'import_batches','source_files','source_sheets','source_columns',
        'transformation_runs','staged_rows','staged_cells','validation_issues'
    ] loop
        execute format('alter table ingestion.%I enable row level security', target_table);
        execute format(
            'create policy tenant_read on ingestion.%I for select to authenticated using ((select auth.uid()) is not null and (select construction_private.can_read_project(organization_id, project_id)))',
            target_table
        );
        execute format(
            'create policy tenant_insert on ingestion.%I for insert to authenticated with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            target_table
        );
        execute format(
            'create policy tenant_update on ingestion.%I for update to authenticated using ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id))) with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            target_table
        );
    end loop;

    foreach target_table in array array[
        'mapping_profiles','mapping_profile_versions','mapping_version_sheets'
    ] loop
        execute format('alter table ingestion.%I enable row level security', target_table);
        execute format(
            'create policy tenant_read on ingestion.%I for select to authenticated using ((select auth.uid()) is not null and (select construction_private.is_org_member(organization_id)))',
            target_table
        );
        execute format(
            'create policy tenant_insert on ingestion.%I for insert to authenticated with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            target_table
        );
    end loop;

    foreach target_table in array array['publish_batches','record_lineage'] loop
        execute format('alter table ingestion.%I enable row level security', target_table);
        execute format(
            'create policy tenant_read on ingestion.%I for select to authenticated using ((select auth.uid()) is not null and (select construction_private.can_read_project(organization_id, project_id)))',
            target_table
        );
    end loop;
end
$policies$;

drop policy tenant_insert on ingestion.import_batches;
create policy tenant_insert on ingestion.import_batches
for insert to authenticated
with check (
    (select auth.uid()) is not null
    and requester_user_id = (select auth.uid())
    and status = 'uploaded'
    and published_at is null
    and cancelled_at is null
    and (select construction_private.can_manage_org(organization_id))
);

create policy tenant_update on ingestion.mapping_profiles
for update to authenticated
using ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))
with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)));

alter table ingestion.approval_records enable row level security;
create policy tenant_read on ingestion.approval_records
for select to authenticated
using ((select auth.uid()) is not null and (select construction_private.can_read_project(organization_id, project_id)));
create policy tenant_approve on ingestion.approval_records
for insert to authenticated
with check (
    (select auth.uid()) is not null
    and approver_user_id = (select auth.uid())
    and (select construction_private.can_admin_org(organization_id))
);

-- All foreign-key column sets receive leading-order indexes.
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
          and namespace_row.nspname = 'ingestion'
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

create index import_batches_scope_status_idx
    on ingestion.import_batches (organization_id, project_id, status, status_changed_at desc);
create index import_batches_actionable_idx
    on ingestion.import_batches (organization_id, status_changed_at)
    where status in ('review_ready','awaiting_approval','approved','publish_failed');
create index staged_rows_publishable_idx
    on ingestion.staged_rows (organization_id, import_batch_id, transformation_run_id, id)
    where status = 'valid';
create index validation_issues_errors_idx
    on ingestion.validation_issues (organization_id, import_batch_id, transformation_run_id)
    where severity = 'error';
create index publish_batches_status_idx
    on ingestion.publish_batches (organization_id, status, started_at);
create index record_lineage_target_idx
    on ingestion.record_lineage (organization_id, target_schema, target_table, target_record_id);
create index record_lineage_source_idx
    on ingestion.record_lineage (organization_id, source_file_id, source_sheet_id, source_row_number);

grant usage on schema ingestion to authenticated;
revoke all on all tables in schema ingestion from public, anon, authenticated, service_role;
grant select, insert, update on ingestion.import_batches, ingestion.source_files,
    ingestion.source_sheets, ingestion.source_columns, ingestion.transformation_runs,
    ingestion.staged_rows, ingestion.staged_cells, ingestion.validation_issues
    to authenticated;
grant select, insert on ingestion.mapping_profile_versions,
    ingestion.mapping_version_sheets, ingestion.approval_records to authenticated;
grant select, insert, update on ingestion.mapping_profiles to authenticated;
grant select on ingestion.publish_batches, ingestion.record_lineage to authenticated;
-- These nine tables are import-only publication targets. RLS remains enabled,
-- but authenticated clients cannot bypass approval with direct fact mutations.
revoke insert, update on construction.projects, construction.employees,
    construction.activities, construction.invoices, construction.risks,
    construction.rfis, construction.nonconformance_reports,
    construction.safety_incidents, construction.daily_reports
    from authenticated;
alter default privileges in schema ingestion revoke all on tables from public, anon, authenticated, service_role;
alter default privileges in schema ingestion revoke execute on functions from public, anon, authenticated, service_role;

comment on schema ingestion is
'Governed multi-sheet imports with immutable mapping versions, per-sheet target definitions, source-cell provenance, deterministic validation, bound approval, atomic publication, and record lineage.';
comment on function ingestion.publish_import_batch(uuid, uuid, text) is
'The only client-callable import publication entry point; authorization, approval binding, validation, idempotency, operational upsert, and lineage are rechecked atomically.';

commit;
