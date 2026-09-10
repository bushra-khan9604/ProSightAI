-- End-to-end approval/publication/lineage and semantic filter checks.
-- Run only on a disposable local Supabase database; all rows are rolled back.

begin;

insert into auth.users (
    instance_id, id, aud, role, email, encrypted_password,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values
    ('00000000-0000-0000-0000-000000000000','61111111-1111-1111-1111-111111111111','authenticated','authenticated','publisher@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','62222222-2222-2222-2222-222222222222','authenticated','authenticated','requester@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','63333333-3333-3333-3333-333333333333','authenticated','authenticated','restricted-member@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','64444444-4444-4444-4444-444444444444','authenticated','authenticated','restricted-outsider@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now());

insert into construction.organizations (id, code, legal_name)
values ('c0000000-0000-0000-0000-000000000001','TEST-PUBLISH','Publication Test');
insert into construction.organization_members
    (id, organization_id, user_id, role, is_active)
values
    ('c1000000-0000-0000-0000-000000000001','c0000000-0000-0000-0000-000000000001','61111111-1111-1111-1111-111111111111','owner',true),
    ('c1000000-0000-0000-0000-000000000002','c0000000-0000-0000-0000-000000000001','62222222-2222-2222-2222-222222222222','manager',true),
    ('c1000000-0000-0000-0000-000000000003','c0000000-0000-0000-0000-000000000001','63333333-3333-3333-3333-333333333333','member',true),
    ('c1000000-0000-0000-0000-000000000004','c0000000-0000-0000-0000-000000000001','64444444-4444-4444-4444-444444444444','viewer',true);
insert into construction.projects
    (id, organization_id, code, name, access_mode)
values
    ('c2000000-0000-0000-0000-000000000001','c0000000-0000-0000-0000-000000000001','P-RESTRICTED','Restricted Project','restricted'),
    ('c2000000-0000-0000-0000-000000000002','c0000000-0000-0000-0000-000000000001','P-OTHER','Other Project','organization');
insert into construction.project_members
    (id, organization_id, project_id, user_id, role, is_active)
values (
    'c3000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    '63333333-3333-3333-3333-333333333333','member',true
);

do $batch_initial_status_guard$
declare rejected boolean := false;
begin
    begin
        insert into ingestion.import_batches (
            organization_id, project_id, source_kind, idempotency_key,
            status, requester_user_id, published_at
        ) values (
            'c0000000-0000-0000-0000-000000000001',
            'c2000000-0000-0000-0000-000000000001','xlsx',
            'illegal-initial-state','published',
            '62222222-2222-2222-2222-222222222222',now()
        );
    exception when check_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'import batch bypassed the mandatory uploaded initial state';
    end if;
end
$batch_initial_status_guard$;

insert into ingestion.mapping_profiles (
    id, organization_id, name, source_kind, created_by
) values (
    'd1000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Daily reports v1','xlsx',
    '62222222-2222-2222-2222-222222222222'
);
insert into ingestion.mapping_profile_versions (
    id, organization_id, mapping_profile_id, version_no,
    mapping_specification, mapping_checksum, transformation_version, created_by
) values (
    'd2000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'd1000000-0000-0000-0000-000000000001',1,
    '{"workbook":"daily-and-reject-case"}'::jsonb,repeat('1',64),
    'deterministic-v1','62222222-2222-2222-2222-222222222222'
);

insert into ingestion.mapping_profiles (
    id, organization_id, name, source_kind, created_by
) values (
    'd1000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000001',
    'Reusable risk profile','xlsx',
    '62222222-2222-2222-2222-222222222222'
);
insert into ingestion.mapping_profile_versions (
    id, organization_id, mapping_profile_id, version_no,
    mapping_specification, mapping_checksum, transformation_version, created_by
) values (
    'd2000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000001',
    'd1000000-0000-0000-0000-000000000002',1,
    '{"workbook":"reusable-risk"}'::jsonb,repeat('a',64),
    'deterministic-v1','62222222-2222-2222-2222-222222222222'
);

do $mapping_identity_contract$
begin
    if (
        select count(distinct mapping_profile_id)
        from ingestion.mapping_profile_versions
        where organization_id = 'c0000000-0000-0000-0000-000000000001'
          and version_no = 1
    ) <> 2 or (
        select count(distinct id)
        from ingestion.mapping_profile_versions
        where organization_id = 'c0000000-0000-0000-0000-000000000001'
          and version_no = 1
    ) <> 2 then
        raise exception 'profile identity and version identity were conflated';
    end if;
end
$mapping_identity_contract$;
insert into ingestion.mapping_version_sheets (
    id, organization_id, mapping_version_id, sheet_classification,
    sheet_ordinal, source_sheet_matcher, target_entity_type,
    mapping_specification, business_key_columns
) values
    (
        'd2100000-0000-0000-0000-000000000001',
        'c0000000-0000-0000-0000-000000000001',
        'd2000000-0000-0000-0000-000000000001','daily_reports',0,
        '{"sheet_name":"Daily"}'::jsonb,'daily_reports',
        '{"report_date":"Report Date"}'::jsonb,
        array['project_id','report_date','shift_code']
    ),
    (
        'd2100000-0000-0000-0000-000000000002',
        'c0000000-0000-0000-0000-000000000001',
        'd2000000-0000-0000-0000-000000000001','unsupported_test_sheet',1,
        '{"sheet_name":"Rows"}'::jsonb,'not_a_publishable_target',
        '{"value":"Value"}'::jsonb,array['value']
    );

do $multi_sheet_mapping$
begin
    if (select count(*) from ingestion.mapping_version_sheets
        where mapping_version_id = 'd2000000-0000-0000-0000-000000000001') <> 2 then
        raise exception 'one mapping version did not retain both governed sheet mappings';
    end if;
    if (select count(distinct target_entity_type) from ingestion.mapping_version_sheets
        where mapping_version_id = 'd2000000-0000-0000-0000-000000000001') <> 2 then
        raise exception 'one mapping version did not retain distinct entity mappings';
    end if;
end
$multi_sheet_mapping$;

insert into ingestion.import_batches (
    id, organization_id, project_id, source_kind, idempotency_key,
    mapping_version_id, input_profile_checksum, normalized_preview_checksum,
    validation_checksum, requester_user_id
) values (
    'd3000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001','xlsx','publish-test-1',
    'd2000000-0000-0000-0000-000000000001',repeat('2',64),repeat('3',64),repeat('4',64),
    '62222222-2222-2222-2222-222222222222'
);

do $batch_transition_bypass_guard$
declare rejected boolean := false;
begin
    begin
        update ingestion.import_batches
        set status = 'awaiting_approval'
        where id = 'd3000000-0000-0000-0000-000000000001';
    exception when check_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'import batch bypassed the guarded legal transition sequence';
    end if;
end
$batch_transition_bypass_guard$;

insert into ingestion.source_files (
    id, organization_id, project_id, import_batch_id, source_kind,
    original_filename, mime_type, byte_size, checksum_sha256, uploaded_by
) values (
    'd4000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd3000000-0000-0000-0000-000000000001','xlsx','daily.xlsx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',128,repeat('5',64),
    '62222222-2222-2222-2222-222222222222'
);
insert into ingestion.source_sheets (
    id, organization_id, project_id, source_file_id, sheet_name,
    sheet_ordinal, row_count, column_count
) values (
    'd5000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd4000000-0000-0000-0000-000000000001','Daily',0,1,1
);
insert into ingestion.source_columns (
    id, organization_id, project_id, source_sheet_id, column_ordinal,
    column_letter, raw_header, normalized_header, inferred_type
) values (
    'd6000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd5000000-0000-0000-0000-000000000001',0,'A','Report Date','report_date','date'
);
insert into ingestion.transformation_runs (
    id, organization_id, project_id, import_batch_id, mapping_version_id,
    run_number, status, input_profile_checksum, normalized_preview_checksum,
    validation_checksum, transformation_version, row_count, started_at,
    completed_at, created_by
) values (
    'd7000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd3000000-0000-0000-0000-000000000001',
    'd2000000-0000-0000-0000-000000000001',1,'succeeded',repeat('2',64),repeat('3',64),repeat('4',64),
    'deterministic-v1',1,now(),now(),'62222222-2222-2222-2222-222222222222'
);
insert into ingestion.staged_rows (
    id, organization_id, project_id, import_batch_id, source_file_id,
    source_sheet_id, transformation_run_id, mapping_version_sheet_id,
    row_number, target_entity_type,
    raw_record, normalized_record, business_key, business_key_checksum,
    raw_row_checksum, normalized_row_checksum, status
) values (
    'd8000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd3000000-0000-0000-0000-000000000001',
    'd4000000-0000-0000-0000-000000000001',
    'd5000000-0000-0000-0000-000000000001',
    'd7000000-0000-0000-0000-000000000001',
    'd2100000-0000-0000-0000-000000000001',2,'daily_reports',
    '{"Report Date":"2026-09-01","Shift":"day"}'::jsonb,
    jsonb_build_object(
        'organization_id','c0000000-0000-0000-0000-000000000001',
        'project_id','c2000000-0000-0000-0000-000000000001',
        'report_date','2026-09-01','shift_code','day','work_completed','Foundation works'
    ),
    jsonb_build_object(
        'project_id','c2000000-0000-0000-0000-000000000001',
        'report_date','2026-09-01','shift_code','day'
    ),repeat('6',64),repeat('7',64),repeat('8',64),'valid'
);
insert into ingestion.staged_cells (
    id, organization_id, project_id, staged_row_id, source_column_id,
    cell_reference, target_field, raw_value, normalized_value
) values (
    'd9000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd8000000-0000-0000-0000-000000000001',
    'd6000000-0000-0000-0000-000000000001','Daily!A2','report_date',
    to_jsonb('2026-09-01'::text),to_jsonb('2026-09-01'::text)
);

update ingestion.import_batches set status = 'profiling' where id = 'd3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'mapping' where id = 'd3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'validating' where id = 'd3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'review_ready' where id = 'd3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'awaiting_approval' where id = 'd3000000-0000-0000-0000-000000000001';

set local role authenticated;
select set_config('request.jwt.claim.sub','61111111-1111-1111-1111-111111111111',true);

do $approval_binding$
declare rejected boolean := false;
begin
    begin
        insert into ingestion.approval_records (
            organization_id, project_id, import_batch_id, mapping_version_id,
            transformation_run_id, requester_user_id, approver_user_id,
            decision, validation_checksum, normalized_preview_checksum
        ) values (
            'c0000000-0000-0000-0000-000000000001',
            'c2000000-0000-0000-0000-000000000001',
            'd3000000-0000-0000-0000-000000000001',
            'd2000000-0000-0000-0000-000000000001',
            'd7000000-0000-0000-0000-000000000001',
            '62222222-2222-2222-2222-222222222222',
            '61111111-1111-1111-1111-111111111111','approved',repeat('9',64),repeat('3',64)
        );
    exception when check_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'approval with a mismatched validation checksum was accepted';
    end if;
end
$approval_binding$;

insert into ingestion.approval_records (
    id, organization_id, project_id, import_batch_id, mapping_version_id,
    transformation_run_id, requester_user_id, approver_user_id,
    decision, validation_checksum, normalized_preview_checksum
) values (
    'da000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'd3000000-0000-0000-0000-000000000001',
    'd2000000-0000-0000-0000-000000000001',
    'd7000000-0000-0000-0000-000000000001',
    '62222222-2222-2222-2222-222222222222',
    '61111111-1111-1111-1111-111111111111','approved',repeat('4',64),repeat('3',64)
);

do $publication$
declare publication_status text;
begin
    select result.status into strict publication_status
    from ingestion.publish_import_batch(
        'd3000000-0000-0000-0000-000000000001',
        'da000000-0000-0000-0000-000000000001',
        'publish-call-1'
    ) result;
    if publication_status <> 'published' then
        raise exception 'publication failed: %', publication_status;
    end if;
    if (select count(*) from construction.daily_reports where project_id = 'c2000000-0000-0000-0000-000000000001') <> 1 then
        raise exception 'publication did not create exactly one operational fact';
    end if;
    if (select count(*) from ingestion.record_lineage where import_batch_id = 'd3000000-0000-0000-0000-000000000001') <> 1 then
        raise exception 'publication did not create exactly one lineage record';
    end if;
    if not exists (
        select 1
        from ingestion.record_lineage lineage
        join ingestion.staged_cells cell on cell.staged_row_id = lineage.staged_row_id
        where lineage.import_batch_id = 'd3000000-0000-0000-0000-000000000001'
          and cell.cell_reference = 'Daily!A2'
    ) then
        raise exception 'published lineage cannot be traced to its source cell';
    end if;

    select result.status into strict publication_status
    from ingestion.publish_import_batch(
        'd3000000-0000-0000-0000-000000000001',
        'da000000-0000-0000-0000-000000000001',
        'publish-call-1'
    ) result;
    if publication_status <> 'already_published' then
        raise exception 'idempotent retry did not return already_published';
    end if;
    if (select count(*) from ingestion.record_lineage where import_batch_id = 'd3000000-0000-0000-0000-000000000001') <> 1 then
        raise exception 'idempotent retry duplicated lineage';
    end if;
end
$publication$;

reset role;

-- A second approved batch deliberately fails after its first staged row. The
-- publisher's inner subtransaction must roll back both the fact and lineage.
insert into ingestion.import_batches (
    id, organization_id, project_id, source_kind, idempotency_key,
    mapping_version_id, input_profile_checksum, normalized_preview_checksum,
    validation_checksum, requester_user_id
) values (
    'f3000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001','xlsx','publish-failure-test',
    'd2000000-0000-0000-0000-000000000001',repeat('2',64),repeat('3',64),repeat('4',64),
    '62222222-2222-2222-2222-222222222222'
);
insert into ingestion.source_files (
    id, organization_id, project_id, import_batch_id, source_kind,
    original_filename, byte_size, checksum_sha256, uploaded_by
) values (
    'f4000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'f3000000-0000-0000-0000-000000000001','xlsx','atomic-failure.xlsx',128,repeat('f',64),
    '62222222-2222-2222-2222-222222222222'
);
insert into ingestion.source_sheets (
    id, organization_id, project_id, source_file_id, sheet_name,
    sheet_ordinal, row_count, column_count
) values (
    'f5000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'f4000000-0000-0000-0000-000000000001','Rows',0,2,1
);
insert into ingestion.transformation_runs (
    id, organization_id, project_id, import_batch_id, mapping_version_id,
    run_number, status, input_profile_checksum, normalized_preview_checksum,
    validation_checksum, transformation_version, row_count, started_at,
    completed_at, created_by
) values (
    'f7000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'f3000000-0000-0000-0000-000000000001',
    'd2000000-0000-0000-0000-000000000001',1,'succeeded',repeat('2',64),repeat('3',64),repeat('4',64),
    'deterministic-v1',2,now(),now(),'62222222-2222-2222-2222-222222222222'
);
insert into ingestion.staged_rows (
    id, organization_id, project_id, import_batch_id, source_file_id,
    source_sheet_id, transformation_run_id, mapping_version_sheet_id,
    row_number, target_entity_type,
    raw_record, normalized_record, business_key, business_key_checksum,
    raw_row_checksum, normalized_row_checksum, status
) values
    (
        'f8000000-0000-0000-0000-000000000001',
        'c0000000-0000-0000-0000-000000000001',
        'c2000000-0000-0000-0000-000000000001',
        'f3000000-0000-0000-0000-000000000001',
        'f4000000-0000-0000-0000-000000000001',
        'f5000000-0000-0000-0000-000000000001',
        'f7000000-0000-0000-0000-000000000001',
        'd2100000-0000-0000-0000-000000000001',2,'daily_reports',
        '{}'::jsonb,
        jsonb_build_object(
            'organization_id','c0000000-0000-0000-0000-000000000001',
            'project_id','c2000000-0000-0000-0000-000000000001',
            'report_date','2026-09-02','shift_code','day','work_completed','Must roll back'
        ),
        jsonb_build_object(
            'project_id','c2000000-0000-0000-0000-000000000001',
            'report_date','2026-09-02','shift_code','day'
        ),repeat('a',64),repeat('b',64),repeat('c',64),'valid'
    ),
    (
        'f8000000-0000-0000-0000-000000000002',
        'c0000000-0000-0000-0000-000000000001',
        'c2000000-0000-0000-0000-000000000001',
        'f3000000-0000-0000-0000-000000000001',
        'f4000000-0000-0000-0000-000000000001',
        'f5000000-0000-0000-0000-000000000001',
        'f7000000-0000-0000-0000-000000000001',
        'd2100000-0000-0000-0000-000000000002',3,'not_a_publishable_target',
        '{}'::jsonb,'{"value":"invalid target"}'::jsonb,
        '{"value":"invalid target"}'::jsonb,repeat('d',64),repeat('e',64),repeat('f',64),'valid'
    );

update ingestion.import_batches set status = 'profiling' where id = 'f3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'mapping' where id = 'f3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'validating' where id = 'f3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'review_ready' where id = 'f3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'awaiting_approval' where id = 'f3000000-0000-0000-0000-000000000001';

set local role authenticated;
select set_config('request.jwt.claim.sub','61111111-1111-1111-1111-111111111111',true);
insert into ingestion.approval_records (
    id, organization_id, project_id, import_batch_id, mapping_version_id,
    transformation_run_id, requester_user_id, approver_user_id,
    decision, validation_checksum, normalized_preview_checksum
) values (
    'fa000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'f3000000-0000-0000-0000-000000000001',
    'd2000000-0000-0000-0000-000000000001',
    'f7000000-0000-0000-0000-000000000001',
    '62222222-2222-2222-2222-222222222222',
    '61111111-1111-1111-1111-111111111111','approved',repeat('4',64),repeat('3',64)
);
do $lineage_atomicity$
declare publication_status text;
begin
    select result.status into strict publication_status
    from ingestion.publish_import_batch(
        'f3000000-0000-0000-0000-000000000001',
        'fa000000-0000-0000-0000-000000000001',
        'publish-failure-call'
    ) result;
    if publication_status <> 'publish_failed' then
        raise exception 'deliberately invalid publication did not fail safely';
    end if;
    if exists (
        select 1 from construction.daily_reports
        where project_id = 'c2000000-0000-0000-0000-000000000001'
          and report_date = date '2026-09-02'
    ) or exists (
        select 1 from ingestion.record_lineage
        where import_batch_id = 'f3000000-0000-0000-0000-000000000001'
    ) then
        raise exception 'failed publication left a partial fact or lineage row';
    end if;
end
$lineage_atomicity$;
reset role;

-- Approved document projection used for vector/filter/revocation checks.
insert into construction.documents (
    id, organization_id, project_id, document_number, title, document_type
) values (
    'e1000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001','DOC-1','Approved source','report'
);
insert into construction.document_revisions (
    id, organization_id, project_id, document_id, revision_code, revision_date,
    status, storage_bucket, storage_object_path, checksum_sha256, mime_type,
    file_size_bytes, uploaded_at, verified_at, approved_by, approved_at
) values (
    'e2000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'e1000000-0000-0000-0000-000000000001','A',date '2026-09-01','approved',
    'prosight-pdfs','test-only/doc-1.pdf',repeat('a',64),'application/pdf',128,
    now(),now(),'61111111-1111-1111-1111-111111111111',now()
);
update construction.documents
set current_revision_id = 'e2000000-0000-0000-0000-000000000001'
where id = 'e1000000-0000-0000-0000-000000000001';

insert into semantic.semantic_projection_versions (
    id, organization_id, source_entity_type, version_no, renderer_name,
    renderer_version, projection_specification, specification_checksum, created_by
) values (
    'e3000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001','document_section',1,
    'document-section','1','{"fields":["title","body"]}'::jsonb,repeat('b',64),
    '61111111-1111-1111-1111-111111111111'
);
insert into semantic.semantic_documents (
    id, organization_id, project_id, source_entity_type, source_entity_id,
    construction_document_id, document_revision_id, title, body,
    projection_version_id, projection_version, content_checksum,
    approval_status, index_status, approved_at
) values (
    'e4000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001','document_section',
    'e2000000-0000-0000-0000-000000000001',
    'e1000000-0000-0000-0000-000000000001',
    'e2000000-0000-0000-0000-000000000001','Concrete method statement',
    'Approved foundation concrete sequence and controls.',
    'e3000000-0000-0000-0000-000000000001',1,repeat('c',64),
    'approved','ready',now()
);
insert into semantic.semantic_chunks (
    id, organization_id, project_id, semantic_document_id,
    construction_document_id, document_revision_id, source_entity_type,
    source_entity_id, source_file_id, import_batch_id, storage_bucket,
    storage_object_path, page_start, page_end, heading_path, chunk_ordinal,
    body, content_checksum, token_count, projection_version,
    chunking_version, approval_status, index_status, embedding
) values (
    'e5000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'c2000000-0000-0000-0000-000000000001',
    'e4000000-0000-0000-0000-000000000001',
    'e1000000-0000-0000-0000-000000000001',
    'e2000000-0000-0000-0000-000000000001','document_section',
    'e2000000-0000-0000-0000-000000000001',
    null, null, 'prosight-pdfs','test-only/doc-1.pdf',
    1,1,array['Foundation'],0,'Approved foundation concrete sequence and controls.',
    repeat('d',64),7,1,'chunk-v1','approved','ready',
    array_fill(0.001::real,array[1536])::extensions.vector
);

do $vector_contract$
declare rejected boolean := false;
begin
    if abs((select embedding OPERATOR(extensions.<=>) embedding
            from semantic.semantic_chunks
            where id = 'e5000000-0000-0000-0000-000000000001')) > 0.0000001 then
        raise exception 'cosine distance parity failed for identical vectors';
    end if;
    if (select metadata ->> 'embedding_dimensions'
        from semantic.semantic_chunks
        where id = 'e5000000-0000-0000-0000-000000000001') <> '1536' then
        raise exception 'chunk metadata does not mirror typed embedding dimensions';
    end if;
    if (select metadata ->> 'document_id'
        from semantic.semantic_chunks
        where id = 'e5000000-0000-0000-0000-000000000001')
       <> 'e1000000-0000-0000-0000-000000000001' then
        raise exception 'legacy chunk metadata does not retain document_id';
    end if;
    begin
        insert into semantic.semantic_chunks (
            organization_id, project_id, semantic_document_id,
            construction_document_id, document_revision_id, source_entity_type,
            source_entity_id, source_file_id, import_batch_id, page_start,
            chunk_ordinal, body, content_checksum, token_count,
            projection_version, chunking_version, approval_status, index_status
        ) values (
            'c0000000-0000-0000-0000-000000000001',
            'c2000000-0000-0000-0000-000000000001',
            'e4000000-0000-0000-0000-000000000001',
            'e1000000-0000-0000-0000-000000000001',
            'e2000000-0000-0000-0000-000000000001','document_section',
            'e2000000-0000-0000-0000-000000000001',
            'd4000000-0000-0000-0000-000000000001',null,2,2,
            'one-sided ingestion provenance must fail',repeat('f',64),5,
            1,'chunk-v1','approved','pending'
        );
    exception when check_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'one-null/one-nonnull ingestion provenance was accepted';
    end if;
    rejected := false;
    begin
        insert into semantic.semantic_chunks (
            organization_id, project_id, semantic_document_id,
            construction_document_id, document_revision_id, source_entity_type,
            source_entity_id, page_start, chunk_ordinal, body, content_checksum,
            token_count, projection_version, chunking_version, approval_status,
            index_status, embedding
        ) values (
            'c0000000-0000-0000-0000-000000000001',
            'c2000000-0000-0000-0000-000000000001',
            'e4000000-0000-0000-0000-000000000001',
            'e1000000-0000-0000-0000-000000000001',
            'e2000000-0000-0000-0000-000000000001','document_section',
            'e2000000-0000-0000-0000-000000000001',2,1,'zero vector must fail',
            repeat('e',64),4,1,'chunk-v1','approved','ready',
            array_fill(0::real,array[1536])::extensions.vector
        );
    exception when check_violation then
        rejected := true;
    end;
    if not rejected then
        raise exception 'zero embedding vector was accepted';
    end if;
end
$vector_contract$;

set local role authenticated;

select set_config('request.jwt.claim.sub','61111111-1111-1111-1111-111111111111',true);
do $owner_search$
begin
    if (select count(*) from semantic.hybrid_search(
        'c0000000-0000-0000-0000-000000000001',
        array['c2000000-0000-0000-0000-000000000001']::uuid[],
        'foundation concrete',array_fill(0.001::real,array[1536])::extensions.vector,
        1,'chunk-v1','text-embedding-3-small',10
    )) <> 1 then
        raise exception 'authorized filtered hybrid search did not return the ready chunk';
    end if;
    if exists (select 1 from semantic.hybrid_search(
        'c0000000-0000-0000-0000-000000000001',
        array['c2000000-0000-0000-0000-000000000002']::uuid[],
        'foundation concrete',array_fill(0.001::real,array[1536])::extensions.vector,
        1,'chunk-v1','text-embedding-3-small',10
    )) then
        raise exception 'hybrid search ignored its typed project filter';
    end if;
end
$owner_search$;

select set_config('request.jwt.claim.sub','64444444-4444-4444-4444-444444444444',true);
do $restricted_outsider_search$
begin
    if exists (select 1 from semantic.hybrid_search(
        'c0000000-0000-0000-0000-000000000001',null,
        'foundation concrete',array_fill(0.001::real,array[1536])::extensions.vector,
        1,'chunk-v1','text-embedding-3-small',10
    )) then
        raise exception 'restricted-project outsider retrieved a semantic chunk';
    end if;
end
$restricted_outsider_search$;

select set_config('request.jwt.claim.sub','63333333-3333-3333-3333-333333333333',true);
do $restricted_member_search$
begin
    if (select count(*) from semantic.hybrid_search(
        'c0000000-0000-0000-0000-000000000001',null,
        'foundation concrete',array_fill(0.001::real,array[1536])::extensions.vector,
        1,'chunk-v1','text-embedding-3-small',10
    )) <> 1 then
        raise exception 'active restricted-project member could not retrieve authorized semantic chunk';
    end if;
end
$restricted_member_search$;

reset role;

update construction.document_revisions
set status = 'withdrawn'
where id = 'e2000000-0000-0000-0000-000000000001';

do $approval_revocation$
begin
    if exists (
        select 1 from construction.documents
        where id = 'e1000000-0000-0000-0000-000000000001'
          and current_revision_id is not null
    ) then
        raise exception 'revoked revision remained the current approved revision';
    end if;
    if exists (
        select 1 from semantic.semantic_chunks
        where id = 'e5000000-0000-0000-0000-000000000001'
          and (approval_status = 'approved' or index_status = 'ready')
    ) then
        raise exception 'revoked revision remained retrieval-ready';
    end if;
end
$approval_revocation$;

rollback;
