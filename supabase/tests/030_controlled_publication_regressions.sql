-- Regression coverage for controlled employee and semantic publication.
-- Run only against a disposable local database; every change is rolled back.

begin;

insert into auth.users (
    instance_id, id, aud, role, email, encrypted_password,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values
    ('00000000-0000-0000-0000-000000000000','71111111-1111-1111-1111-111111111111','authenticated','authenticated','owner-regression@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now()),
    ('00000000-0000-0000-0000-000000000000','72222222-2222-2222-2222-222222222222','authenticated','authenticated','manager-regression@example.test','', '{}'::jsonb,'{}'::jsonb,now(),now());

insert into construction.organizations (id, code, legal_name)
values ('a0000000-0000-0000-0000-000000000001','CONTROLLED-PUBLISH','Controlled Publication Test');
insert into construction.organization_members
    (id, organization_id, user_id, role, is_active)
values
    ('a1000000-0000-0000-0000-000000000001','a0000000-0000-0000-0000-000000000001','71111111-1111-1111-1111-111111111111','owner',true),
    ('a1000000-0000-0000-0000-000000000002','a0000000-0000-0000-0000-000000000001','72222222-2222-2222-2222-222222222222','manager',true);

set local role authenticated;
select set_config('request.jwt.claim.sub','72222222-2222-2222-2222-222222222222',true);
do $direct_employee_denial$
declare denied boolean := false;
begin
    begin
        insert into construction.employees (
            organization_id, employee_number, first_name
        ) values (
            'a0000000-0000-0000-0000-000000000001','BYPASS-1','Must Fail'
        );
    exception when insufficient_privilege then
        denied := true;
    end;
    if not denied then
        raise exception 'authenticated manager bypassed ingestion approval with direct employee DML';
    end if;
end
$direct_employee_denial$;
reset role;

insert into ingestion.mapping_profiles (
    id, organization_id, name, source_kind, created_by
) values (
    'b1000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'Employee regression v1','xlsx',
    '72222222-2222-2222-2222-222222222222'
);
insert into ingestion.mapping_profile_versions (
    id, organization_id, mapping_profile_id, version_no,
    mapping_specification, mapping_checksum, transformation_version, created_by
) values (
    'b2000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b1000000-0000-0000-0000-000000000001',1,
    '{"workbook":"employee-regression"}'::jsonb,repeat('1',64),
    'deterministic-v1','72222222-2222-2222-2222-222222222222'
);
insert into ingestion.mapping_version_sheets (
    id, organization_id, mapping_version_id, sheet_classification,
    sheet_ordinal, source_sheet_matcher, target_entity_type,
    mapping_specification, business_key_columns
) values (
    'b2100000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b2000000-0000-0000-0000-000000000001','employees',0,
    '{"sheet_name":"Employees"}'::jsonb,'employees',
    '{"employee_number":"Employee No"}'::jsonb,
    array['organization_id','employee_number']
);
insert into ingestion.import_batches (
    id, organization_id, source_kind, idempotency_key, mapping_version_id,
    input_profile_checksum, normalized_preview_checksum, validation_checksum,
    requester_user_id
) values (
    'b3000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001','xlsx','employee-regression-batch',
    'b2000000-0000-0000-0000-000000000001',repeat('2',64),repeat('3',64),repeat('4',64),
    '72222222-2222-2222-2222-222222222222'
);
insert into ingestion.source_files (
    id, organization_id, import_batch_id, source_kind, original_filename,
    byte_size, checksum_sha256, uploaded_by
) values (
    'b4000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b3000000-0000-0000-0000-000000000001','xlsx','employees.xlsx',64,repeat('5',64),
    '72222222-2222-2222-2222-222222222222'
);
insert into ingestion.source_sheets (
    id, organization_id, source_file_id, sheet_name, sheet_ordinal,
    row_count, column_count
) values (
    'b5000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b4000000-0000-0000-0000-000000000001','Employees',0,1,3
);
insert into ingestion.transformation_runs (
    id, organization_id, import_batch_id, mapping_version_id, run_number,
    status, input_profile_checksum, normalized_preview_checksum,
    validation_checksum, transformation_version, row_count,
    started_at, completed_at, created_by
) values (
    'b6000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b3000000-0000-0000-0000-000000000001',
    'b2000000-0000-0000-0000-000000000001',1,'succeeded',
    repeat('2',64),repeat('3',64),repeat('4',64),'deterministic-v1',1,
    now(),now(),'72222222-2222-2222-2222-222222222222'
);
insert into ingestion.staged_rows (
    id, organization_id, import_batch_id, source_file_id, source_sheet_id,
    transformation_run_id, mapping_version_sheet_id, row_number,
    target_entity_type, raw_record,
    normalized_record, business_key, business_key_checksum,
    raw_row_checksum, normalized_row_checksum, status
) values (
    'b7000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b3000000-0000-0000-0000-000000000001',
    'b4000000-0000-0000-0000-000000000001',
    'b5000000-0000-0000-0000-000000000001',
    'b6000000-0000-0000-0000-000000000001',
    'b2100000-0000-0000-0000-000000000001',2,'employees',
    '{"Employee No":"EMP-100","First Name":"Ada"}'::jsonb,
    jsonb_build_object(
        'organization_id','a0000000-0000-0000-0000-000000000001',
        'employee_number','EMP-100','first_name','Ada','last_name','Lovelace'
    ),
    jsonb_build_object(
        'organization_id','a0000000-0000-0000-0000-000000000001',
        'employee_number','EMP-100'
    ),repeat('6',64),repeat('7',64),repeat('8',64),'valid'
);

update ingestion.import_batches set status = 'profiling' where id = 'b3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'mapping' where id = 'b3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'validating' where id = 'b3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'review_ready' where id = 'b3000000-0000-0000-0000-000000000001';
update ingestion.import_batches set status = 'awaiting_approval' where id = 'b3000000-0000-0000-0000-000000000001';

set local role authenticated;
select set_config('request.jwt.claim.sub','71111111-1111-1111-1111-111111111111',true);
insert into ingestion.approval_records (
    id, organization_id, import_batch_id, mapping_version_id,
    transformation_run_id, requester_user_id, approver_user_id,
    decision, validation_checksum, normalized_preview_checksum
) values (
    'b8000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'b3000000-0000-0000-0000-000000000001',
    'b2000000-0000-0000-0000-000000000001',
    'b6000000-0000-0000-0000-000000000001',
    '72222222-2222-2222-2222-222222222222',
    '71111111-1111-1111-1111-111111111111','approved',repeat('4',64),repeat('3',64)
);
do $employee_publication$
declare publication_status text;
begin
    select result.status into strict publication_status
    from ingestion.publish_import_batch(
        'b3000000-0000-0000-0000-000000000001',
        'b8000000-0000-0000-0000-000000000001',
        'employee-publication-call'
    ) result;
    if publication_status <> 'published' then
        raise exception 'controlled employee publication failed: %', publication_status;
    end if;
    if (select count(*) from construction.employees
        where organization_id = 'a0000000-0000-0000-0000-000000000001'
          and employee_number = 'EMP-100') <> 1 then
        raise exception 'controlled publisher did not create exactly one employee';
    end if;
    if (select count(*) from ingestion.record_lineage
        where import_batch_id = 'b3000000-0000-0000-0000-000000000001'
          and target_table = 'employees') <> 1 then
        raise exception 'employee publication did not create exactly one lineage row';
    end if;
end
$employee_publication$;
reset role;

insert into construction.projects (id, organization_id, code, name, access_mode)
values
    ('a2000000-0000-0000-0000-000000000001','a0000000-0000-0000-0000-000000000001','SEM-1','Semantic One','organization'),
    ('a2000000-0000-0000-0000-000000000002','a0000000-0000-0000-0000-000000000001','SEM-2','Semantic Two','organization');
insert into construction.documents (
    id, organization_id, project_id, document_number, title, document_type
) values (
    'c1000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'a2000000-0000-0000-0000-000000000001','LEGACY-1','Legacy approved PDF','report'
);
insert into construction.document_revisions (
    id, organization_id, project_id, document_id, revision_code, revision_date,
    status, storage_bucket, storage_object_path, checksum_sha256, mime_type,
    file_size_bytes, uploaded_at, verified_at, approved_by, approved_at
) values (
    'c2000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'a2000000-0000-0000-0000-000000000001',
    'c1000000-0000-0000-0000-000000000001','A',date '2026-09-10','approved',
    'prosight-pdfs','legacy/regression.pdf',repeat('a',64),'application/pdf',128,
    now(),now(),'71111111-1111-1111-1111-111111111111',now()
);
update construction.documents
set current_revision_id = 'c2000000-0000-0000-0000-000000000001'
where id = 'c1000000-0000-0000-0000-000000000001';

insert into semantic.semantic_projection_versions (
    id, organization_id, source_entity_type, version_no, renderer_name,
    renderer_version, projection_specification, specification_checksum, created_by
) values
    ('c3000000-0000-0000-0000-000000000001','a0000000-0000-0000-0000-000000000001','document_section',1,'document-section','1','{}'::jsonb,repeat('b',64),'71111111-1111-1111-1111-111111111111'),
    ('c3000000-0000-0000-0000-000000000002','a0000000-0000-0000-0000-000000000001','project_summary',1,'project-summary','1','{}'::jsonb,repeat('c',64),'71111111-1111-1111-1111-111111111111'),
    ('c3000000-0000-0000-0000-000000000003','a0000000-0000-0000-0000-000000000001','project_summary',2,'project-summary','2','{}'::jsonb,repeat('d',64),'71111111-1111-1111-1111-111111111111'),
    ('c3000000-0000-0000-0000-000000000004','a0000000-0000-0000-0000-000000000001','project_summary',3,'project-summary','3','{}'::jsonb,repeat('1',64),'71111111-1111-1111-1111-111111111111'),
    ('c3000000-0000-0000-0000-000000000005','a0000000-0000-0000-0000-000000000001','project_summary',4,'project-summary','4','{}'::jsonb,repeat('2',64),'71111111-1111-1111-1111-111111111111');
insert into semantic.semantic_documents (
    id, organization_id, project_id, source_entity_type, source_entity_id,
    construction_document_id, document_revision_id, title, body, language_code,
    projection_version_id, projection_version, content_checksum,
    approval_status, index_status, approved_at
) values
    ('c4000000-0000-0000-0000-000000000001','a0000000-0000-0000-0000-000000000001','a2000000-0000-0000-0000-000000000001','document_section','c2000000-0000-0000-0000-000000000001','c1000000-0000-0000-0000-000000000001','c2000000-0000-0000-0000-000000000001','Project foundation','Foundation controls current project','en','c3000000-0000-0000-0000-000000000001',1,repeat('e',64),'approved','pending',now()),
    ('c4000000-0000-0000-0000-000000000002','a0000000-0000-0000-0000-000000000001',null,'project_summary','c9000000-0000-0000-0000-000000000001',null,null,'Organization foundation','Foundation controls organization wide','en','c3000000-0000-0000-0000-000000000002',1,repeat('f',64),'approved','pending',now()),
    ('c4000000-0000-0000-0000-000000000003','a0000000-0000-0000-0000-000000000001','a2000000-0000-0000-0000-000000000001','project_summary','c9000000-0000-0000-0000-000000000002',null,null,'Stale foundation','Foundation controls stale projection','en','c3000000-0000-0000-0000-000000000003',2,repeat('0',64),'approved','pending',now()),
    ('c4000000-0000-0000-0000-000000000004','a0000000-0000-0000-0000-000000000001','a2000000-0000-0000-0000-000000000001','project_summary','c9000000-0000-0000-0000-000000000003',null,null,'Superseded projection','Must not be indexed after projection supersession','en','c3000000-0000-0000-0000-000000000004',3,repeat('2',64),'approved','pending',now()),
    ('c4000000-0000-0000-0000-000000000005','a0000000-0000-0000-0000-000000000001','a2000000-0000-0000-0000-000000000001','project_summary','c9000000-0000-0000-0000-000000000004',null,null,'Retired projection','Must not be indexed after projection retirement','en','c3000000-0000-0000-0000-000000000005',4,repeat('3',64),'approved','pending',now());

set local role authenticated;
select set_config('request.jwt.claim.sub','71111111-1111-1111-1111-111111111111',true);

do $semantic_project_publication$
declare
    body_text text := 'Foundation controls current project';
    checksum_text text;
    payload jsonb;
    publication_status text;
    rejected boolean;
begin
    checksum_text := pg_catalog.encode(
        extensions.digest(pg_catalog.convert_to(body_text,'UTF8'),'sha256'),'hex'
    );
    payload := pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
        'chunk', pg_catalog.jsonb_build_object(
            'id','c5000000-0000-0000-0000-000000000001',
            'organization_id','a0000000-0000-0000-0000-000000000001',
            'project_id','a2000000-0000-0000-0000-000000000001',
            'semantic_document_id','c4000000-0000-0000-0000-000000000001',
            'construction_document_id','c1000000-0000-0000-0000-000000000001',
            'document_revision_id','c2000000-0000-0000-0000-000000000001',
            'source_entity_type','document_section','source_entity_id','c2000000-0000-0000-0000-000000000001',
            'source_file_id',null,'import_batch_id',null,
            'storage_bucket','prosight-pdfs','storage_object_path','legacy/regression.pdf',
            'page_start',1,'page_end',1,'heading_path',jsonb_build_array('Foundation'),
            'chunk_ordinal',0,'body',body_text,'content_checksum',checksum_text,
            'token_count',4,'embedding_model','text-embedding-3-small',
            'embedding_dimensions',1536,'projection_version',1,'chunking_version','chunk-v1',
            'approval_status','approved','index_status','pending',
            'metadata',jsonb_build_object('document_id','c1000000-0000-0000-0000-000000000001')
        ),
        'embedding',to_jsonb(array_fill(0.001::double precision,array[1536]))
    ));

    select result.status into strict publication_status
    from semantic.publish_chunk_embeddings(
        'a0000000-0000-0000-0000-000000000001',
        'c6000000-0000-0000-0000-000000000001',payload,'semantic-project-v1'
    ) result;
    if publication_status <> 'succeeded' then
        raise exception 'first semantic publication failed: %', publication_status;
    end if;

    select result.status into strict publication_status
    from semantic.publish_chunk_embeddings(
        'a0000000-0000-0000-0000-000000000001',
        'c6000000-0000-0000-0000-000000000001',payload,'semantic-project-v1'
    ) result;
    if publication_status <> 'already_succeeded' then
        raise exception 'semantic retry was not idempotent: %', publication_status;
    end if;
    if (select count(*) from semantic.semantic_chunks
        where id = 'c5000000-0000-0000-0000-000000000001') <> 1
       or (select count(*) from semantic.embedding_jobs
           where id = 'c6000000-0000-0000-0000-000000000001') <> 1 then
        raise exception 'semantic retry duplicated a vector or embedding job';
    end if;
    if (select metadata ->> 'document_id' from semantic.semantic_chunks
        where id = 'c5000000-0000-0000-0000-000000000001')
       <> 'c1000000-0000-0000-0000-000000000001' then
        raise exception 'controlled publication did not retain JSON document_id metadata';
    end if;

    rejected := false;
    begin
        perform * from semantic.publish_chunk_embeddings(
            'a0000000-0000-0000-0000-000000000001',
            'c6000000-0000-0000-0000-000000000009',payload,'semantic-project-v1'
        );
    exception when unique_violation then rejected := true;
    end;
    if not rejected then raise exception 'wrong embedding job binding was accepted'; end if;

    rejected := false;
    begin
        perform * from semantic.publish_chunk_embeddings(
            'a0000000-0000-0000-0000-000000000009',
            'c6000000-0000-0000-0000-000000000008',payload,'wrong-org'
        );
    exception when insufficient_privilege then rejected := true;
    end;
    if not rejected then raise exception 'wrong organization embedding batch was accepted'; end if;

    rejected := false;
    begin
        perform * from semantic.publish_chunk_embeddings(
            'a0000000-0000-0000-0000-000000000001',
            'c6000000-0000-0000-0000-000000000007',
            jsonb_set(payload,'{0,chunk,project_id}',to_jsonb('a2000000-0000-0000-0000-000000000002'::text)),
            'wrong-project'
        );
    exception when check_violation then rejected := true;
    end;
    if not rejected then raise exception 'wrong project embedding batch was accepted'; end if;

    rejected := false;
    begin
        perform * from semantic.publish_chunk_embeddings(
            'a0000000-0000-0000-0000-000000000001',
            'c6000000-0000-0000-0000-000000000006',
            jsonb_set(
                jsonb_set(payload,'{0,chunk,id}',to_jsonb('c5000000-0000-0000-0000-000000000009'::text)),
                '{0,chunk,source_file_id}',to_jsonb('b4000000-0000-0000-0000-000000000001'::text)
            ),
            'wrong-source'
        );
    exception when check_violation or foreign_key_violation then rejected := true;
    end;
    if not rejected then raise exception 'one-sided or mismatched source binding was accepted'; end if;
end
$semantic_project_publication$;

do $semantic_other_publications$
declare
    payload jsonb;
    body_text text;
    checksum_text text;
    publication_status text;
    rejected boolean := false;
begin
    body_text := 'Foundation controls organization wide';
    checksum_text := pg_catalog.encode(extensions.digest(pg_catalog.convert_to(body_text,'UTF8'),'sha256'),'hex');
    payload := jsonb_build_array(jsonb_build_object(
        'chunk',jsonb_build_object(
            'id','c5000000-0000-0000-0000-000000000002','organization_id','a0000000-0000-0000-0000-000000000001',
            'project_id',null,'semantic_document_id','c4000000-0000-0000-0000-000000000002',
            'construction_document_id',null,'document_revision_id',null,
            'source_entity_type','project_summary','source_entity_id','c9000000-0000-0000-0000-000000000001',
            'source_file_id',null,'import_batch_id',null,'storage_bucket',null,'storage_object_path',null,
            'heading_path',jsonb_build_array(),'chunk_ordinal',0,'body',body_text,
            'content_checksum',checksum_text,'token_count',4,'embedding_model','text-embedding-3-small',
            'embedding_dimensions',1536,'projection_version',1,'chunking_version','chunk-v1',
            'approval_status','approved','index_status','pending'
        ),'embedding',to_jsonb(array_fill(0.001::double precision,array[1536]))
    ));
    select result.status into strict publication_status
    from semantic.publish_chunk_embeddings(
        'a0000000-0000-0000-0000-000000000001','c6000000-0000-0000-0000-000000000002',payload,'semantic-org-v1'
    ) result;
    if publication_status <> 'succeeded' then raise exception 'org-wide semantic publication failed'; end if;

    body_text := 'Foundation controls stale projection';
    checksum_text := pg_catalog.encode(extensions.digest(pg_catalog.convert_to(body_text,'UTF8'),'sha256'),'hex');
    payload := jsonb_build_array(jsonb_build_object(
        'chunk',jsonb_build_object(
            'id','c5000000-0000-0000-0000-000000000003','organization_id','a0000000-0000-0000-0000-000000000001',
            'project_id','a2000000-0000-0000-0000-000000000001','semantic_document_id','c4000000-0000-0000-0000-000000000003',
            'construction_document_id',null,'document_revision_id',null,
            'source_entity_type','project_summary','source_entity_id','c9000000-0000-0000-0000-000000000002',
            'source_file_id',null,'import_batch_id',null,'storage_bucket',null,'storage_object_path',null,
            'heading_path',jsonb_build_array(),'chunk_ordinal',0,'body',body_text,
            'content_checksum',checksum_text,'token_count',4,'embedding_model','text-embedding-3-small',
            'embedding_dimensions',1536,'projection_version',2,'chunking_version','chunk-v1',
            'approval_status','approved','index_status','pending'
        ),'embedding',to_jsonb(array_fill(0.001::double precision,array[1536]))
    ));
    select result.status into strict publication_status
    from semantic.publish_chunk_embeddings(
        'a0000000-0000-0000-0000-000000000001','c6000000-0000-0000-0000-000000000003',payload,'semantic-project-v2'
    ) result;
    if publication_status <> 'succeeded' then raise exception 'stale-version fixture publication failed'; end if;

    body_text := 'Must not be indexed after projection supersession';
    checksum_text := pg_catalog.encode(extensions.digest(pg_catalog.convert_to(body_text,'UTF8'),'sha256'),'hex');
    payload := jsonb_build_array(jsonb_build_object(
        'chunk',jsonb_build_object(
            'id','c5000000-0000-0000-0000-000000000004','organization_id','a0000000-0000-0000-0000-000000000001',
            'project_id','a2000000-0000-0000-0000-000000000001','semantic_document_id','c4000000-0000-0000-0000-000000000004',
            'construction_document_id',null,'document_revision_id',null,
            'source_entity_type','project_summary','source_entity_id','c9000000-0000-0000-0000-000000000003',
            'source_file_id',null,'import_batch_id',null,'storage_bucket',null,'storage_object_path',null,
            'heading_path',jsonb_build_array(),'chunk_ordinal',0,'body',body_text,
            'content_checksum',checksum_text,'token_count',7,'embedding_model','text-embedding-3-small',
            'embedding_dimensions',1536,'projection_version',3,'chunking_version','chunk-v1',
            'approval_status','approved','index_status','pending'
        ),'embedding',to_jsonb(array_fill(0.001::double precision,array[1536]))
    ));
    update semantic.semantic_projection_versions
    set status = 'superseded'
    where id = 'c3000000-0000-0000-0000-000000000004';
    begin
        perform * from semantic.publish_chunk_embeddings(
            'a0000000-0000-0000-0000-000000000001',
            'c6000000-0000-0000-0000-000000000004',payload,'inactive-projection-v3'
        );
    exception when check_violation then rejected := true;
    end;
    if not rejected then
        raise exception 'semantic publisher accepted a superseded projection version';
    end if;
    if exists (select 1 from semantic.semantic_chunks
        where id = 'c5000000-0000-0000-0000-000000000004') then
        raise exception 'rejected superseded projection left a semantic chunk';
    end if;

    rejected := false;
    body_text := 'Must not be indexed after projection retirement';
    checksum_text := pg_catalog.encode(extensions.digest(pg_catalog.convert_to(body_text,'UTF8'),'sha256'),'hex');
    payload := jsonb_build_array(jsonb_build_object(
        'chunk',jsonb_build_object(
            'id','c5000000-0000-0000-0000-000000000005','organization_id','a0000000-0000-0000-0000-000000000001',
            'project_id','a2000000-0000-0000-0000-000000000001','semantic_document_id','c4000000-0000-0000-0000-000000000005',
            'construction_document_id',null,'document_revision_id',null,
            'source_entity_type','project_summary','source_entity_id','c9000000-0000-0000-0000-000000000004',
            'source_file_id',null,'import_batch_id',null,'storage_bucket',null,'storage_object_path',null,
            'heading_path',jsonb_build_array(),'chunk_ordinal',0,'body',body_text,
            'content_checksum',checksum_text,'token_count',7,'embedding_model','text-embedding-3-small',
            'embedding_dimensions',1536,'projection_version',4,'chunking_version','chunk-v1',
            'approval_status','approved','index_status','pending'
        ),'embedding',to_jsonb(array_fill(0.001::double precision,array[1536]))
    ));
    update semantic.semantic_projection_versions
    set status = 'retired'
    where id = 'c3000000-0000-0000-0000-000000000005';
    begin
        perform * from semantic.publish_chunk_embeddings(
            'a0000000-0000-0000-0000-000000000001',
            'c6000000-0000-0000-0000-000000000005',payload,'inactive-projection-v4'
        );
    exception when check_violation then rejected := true;
    end;
    if not rejected then
        raise exception 'semantic publisher accepted a retired projection version';
    end if;
    if exists (select 1 from semantic.semantic_chunks
        where id = 'c5000000-0000-0000-0000-000000000005') then
        raise exception 'rejected retired projection left a semantic chunk';
    end if;
end
$semantic_other_publications$;

do $hybrid_scope_versions$
declare result_ids uuid[];
begin
    select array_agg(result.chunk_id order by result.chunk_id) into result_ids
    from semantic.hybrid_search(
        'a0000000-0000-0000-0000-000000000001',
        array['a2000000-0000-0000-0000-000000000001']::uuid[],
        'foundation controls',array_fill(0.001::real,array[1536])::extensions.vector,
        1,'chunk-v1','text-embedding-3-small',10
    ) result;
    if result_ids is distinct from array[
        'c5000000-0000-0000-0000-000000000001'::uuid,
        'c5000000-0000-0000-0000-000000000002'::uuid
    ] then
        raise exception 'hybrid search failed project + org-wide inclusion or stale-version exclusion: %', result_ids;
    end if;

    select array_agg(result.chunk_id order by result.chunk_id) into result_ids
    from semantic.hybrid_search(
        'a0000000-0000-0000-0000-000000000001',
        array['a2000000-0000-0000-0000-000000000002']::uuid[],
        'foundation controls',array_fill(0.001::real,array[1536])::extensions.vector,
        1,'chunk-v1','text-embedding-3-small',10
    ) result;
    if result_ids is distinct from array['c5000000-0000-0000-0000-000000000002'::uuid] then
        raise exception 'org-wide semantic chunk was excluded when a project allowlist was supplied: %', result_ids;
    end if;
end
$hybrid_scope_versions$;

reset role;
rollback;
