-- Run after all repository migrations against a disposable local Supabase DB.
-- The transaction is read-only and does not alter hosted or local data.

begin transaction read only;

do $verification$
declare
    missing_relation text;
    tenant_table record;
    violation_count integer;
    membership_inherits boolean;
    membership_can_set boolean;
begin
    foreach missing_relation in array array[
        'prosight.documents','prosight.document_chunks',
        'construction.organizations','construction.projects',
        'construction.material_items','construction.inventory_locations',
        'construction.material_inventory_balances','construction.material_inventory_movements',
        'ingestion.import_batches','ingestion.mapping_version_sheets','ingestion.record_lineage',
        'semantic.semantic_projection_versions','semantic.semantic_documents',
        'semantic.semantic_chunks','semantic.semantic_entity_links',
        'semantic.embedding_jobs'
    ] loop
        if to_regclass(missing_relation) is null then
            raise exception 'required relation is missing: %', missing_relation;
        end if;
    end loop;

    if (select count(*) from information_schema.tables where table_schema = 'construction') <> 78 then
        raise exception 'construction must contain exactly 78 base tables';
    end if;
    if (select count(*) from information_schema.tables where table_schema = 'ingestion') <> 14 then
        raise exception 'ingestion must contain exactly 14 base tables';
    end if;
    if (select count(*) from information_schema.tables where table_schema = 'semantic') <> 5 then
        raise exception 'semantic must contain exactly 5 base tables';
    end if;
    if to_regclass('semantic.projection_versions') is not null
       or to_regclass('semantic.entity_links') is not null then
        raise exception 'stale semantic table names remain present';
    end if;

    if to_regprocedure('semantic.publish_chunk_embeddings(uuid,uuid,jsonb,text)') is null then
        raise exception 'semantic embedding publication RPC signature is missing';
    end if;
    if to_regprocedure('semantic.hybrid_search(uuid,uuid[],text,extensions.vector,integer,text,text,integer)') is null then
        raise exception 'version-filtered semantic hybrid search signature is missing';
    end if;
    if (
        select procedure_row.prosecdef
        from pg_proc procedure_row
        where procedure_row.oid = 'ingestion.publish_import_batch(uuid,uuid,text)'::regprocedure
    ) or (
        select procedure_row.prosecdef
        from pg_proc procedure_row
        where procedure_row.oid = 'semantic.publish_chunk_embeddings(uuid,uuid,jsonb,text)'::regprocedure
    ) then
        raise exception 'an exposed publication wrapper is SECURITY DEFINER';
    end if;
    if pg_get_functiondef(
        'construction_private.publish_chunk_embeddings_internal(uuid,uuid,jsonb,text)'::regprocedure
    ) !~ 'projection_row\.status <> ''active''' then
        raise exception 'semantic publisher does not reject inactive projection versions';
    end if;

    for tenant_table in
        select table_schema, table_name
        from information_schema.tables
        where table_schema in ('construction','ingestion','semantic')
          and table_type = 'BASE TABLE'
          and not (table_schema = 'construction' and table_name = 'organizations')
    loop
        if not exists (
            select 1
            from information_schema.columns column_row
            where column_row.table_schema = tenant_table.table_schema
              and column_row.table_name = tenant_table.table_name
              and column_row.column_name = 'organization_id'
              and column_row.is_nullable = 'NO'
        ) then
            raise exception 'tenant table %.% lacks non-null organization_id',
                tenant_table.table_schema, tenant_table.table_name;
        end if;

        if not exists (
            select 1
            from pg_constraint constraint_row
            where constraint_row.conrelid = format('%I.%I', tenant_table.table_schema, tenant_table.table_name)::regclass
              and constraint_row.contype = 'u'
              and pg_get_constraintdef(constraint_row.oid) = 'UNIQUE (organization_id, id)'
        ) then
            raise exception 'tenant table %.% lacks unique (organization_id, id)',
                tenant_table.table_schema, tenant_table.table_name;
        end if;
    end loop;

    -- Nullable project scopes use a generated sentinel so project-aware
    -- identities remain enforceable with ordinary UNIQUE/FK pairs.
    for tenant_table in
        select table_schema, table_name,
               exists (
                   select 1 from information_schema.columns scope_column
                   where scope_column.table_schema = table_row.table_schema
                     and scope_column.table_name = table_row.table_name
                     and scope_column.column_name = 'project_scope_id'
               ) as has_project_scope
        from information_schema.tables table_row
        where table_row.table_schema in ('construction','ingestion','semantic')
          and table_row.table_type = 'BASE TABLE'
          and exists (
              select 1 from information_schema.columns project_column
              where project_column.table_schema = table_row.table_schema
                and project_column.table_name = table_row.table_name
                and project_column.column_name = 'project_id'
          )
    loop
        if not exists (
            select 1
            from pg_constraint constraint_row
            where constraint_row.conrelid = format('%I.%I', tenant_table.table_schema, tenant_table.table_name)::regclass
              and constraint_row.contype = 'u'
              and pg_get_constraintdef(constraint_row.oid) = format(
                  'UNIQUE (organization_id, %s, id)',
                  case when tenant_table.has_project_scope then 'project_scope_id' else 'project_id' end
              )
        ) then
            raise exception 'project table %.% lacks its project-aware tenant identity',
                tenant_table.table_schema, tenant_table.table_name;
        end if;
    end loop;

    select count(*) into violation_count
    from pg_constraint constraint_row
    join pg_namespace namespace_row on namespace_row.oid = constraint_row.connamespace
    where constraint_row.contype = 'f'
      and namespace_row.nspname in ('construction','ingestion','semantic')
      and not exists (
          select 1
          from pg_index index_row
          where index_row.indrelid = constraint_row.conrelid
            and index_row.indisvalid
            and index_row.indisready
            and index_row.indpred is null
            and index_row.indexprs is null
            and index_row.indnkeyatts >= cardinality(constraint_row.conkey)
            and not exists (
                select 1
                from unnest(constraint_row.conkey) with ordinality
                    as foreign_key_column(attnum, position)
                where foreign_key_column.attnum is distinct from
                    (index_row.indkey::smallint[])[
                        coalesce(array_lower(index_row.indkey::smallint[], 1), 1)
                        + foreign_key_column.position - 1
                    ]
            )
      );
    if violation_count <> 0 then
        raise exception '% foreign keys lack a leading-column index', violation_count;
    end if;

    select count(*) into violation_count
    from pg_constraint constraint_row
    join pg_class class_row on class_row.oid = constraint_row.conrelid
    join pg_namespace namespace_row on namespace_row.oid = class_row.relnamespace
    where constraint_row.contype = 'f'
      and namespace_row.nspname in ('construction','ingestion','semantic')
      and constraint_row.confdeltype = 'n'
      and cardinality(constraint_row.conkey) > 1
      and (
          constraint_row.confdelsetcols is null
          or exists (
              select 1
              from unnest(constraint_row.confdelsetcols) delete_column(attnum)
              join pg_attribute attribute_row
                on attribute_row.attrelid = constraint_row.conrelid
               and attribute_row.attnum = delete_column.attnum
              where attribute_row.attname = 'organization_id'
          )
      );
    if violation_count <> 0 then
        raise exception '% composite SET NULL foreign keys can null tenant identity', violation_count;
    end if;

    if not exists (
        select 1
        from pg_constraint constraint_row
        where constraint_row.conrelid = 'construction.employees'::regclass
          and constraint_row.contype = 'f'
          and constraint_row.confdeltype = 'n'
          and (
              select array_agg(attribute_row.attname order by delete_column.position)
              from unnest(constraint_row.confdelsetcols) with ordinality
                  as delete_column(attnum, position)
              join pg_attribute attribute_row
                on attribute_row.attrelid = constraint_row.conrelid
               and attribute_row.attnum = delete_column.attnum
          ) = array['business_unit_id'::name]
    ) then
        raise exception 'representative employee business-unit FK lacks column-specific SET NULL';
    end if;

    if exists (
        select 1
        from information_schema.columns column_row
        where column_row.table_schema = 'construction'
          and column_row.table_name in (
              'purchase_order_items','material_receipts',
              'material_inventory_balances','material_inventory_movements'
          )
          and column_row.column_name in (
              'quantity','received_quantity','quantity_received',
              'quantity_accepted','quantity_rejected','quantity_on_hand',
              'quantity_reserved','quantity_available'
          )
          and (column_row.data_type <> 'numeric' or column_row.numeric_scale <> 6)
    ) then
        raise exception 'material order/delivery/inventory quantities are not exact numeric scale 6';
    end if;

    select count(*) into violation_count
    from pg_class class_row
    join pg_namespace namespace_row on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname in ('construction','ingestion','semantic')
      and class_row.relkind = 'r'
      and not class_row.relrowsecurity;
    if violation_count <> 0 then
        raise exception '% application tables do not have RLS enabled', violation_count;
    end if;

    if exists (
        select 1
        from pg_policy policy_row
        join pg_class class_row on class_row.oid = policy_row.polrelid
        join pg_namespace namespace_row on namespace_row.oid = class_row.relnamespace
        where namespace_row.nspname in ('construction','ingestion','semantic')
          and (
              policy_row.polroles <> array[(select oid from pg_roles where rolname = 'authenticated')]
              or coalesce(pg_get_expr(policy_row.polqual, policy_row.polrelid), '') ~ 'auth\.role'
              or coalesce(pg_get_expr(policy_row.polwithcheck, policy_row.polrelid), '') ~ 'auth\.role'
              or (
                  coalesce(pg_get_expr(policy_row.polqual, policy_row.polrelid), '')
                  || coalesce(pg_get_expr(policy_row.polwithcheck, policy_row.polrelid), '')
              ) !~ 'auth\.uid'
          )
    ) then
        raise exception 'RLS policies must target only authenticated, require auth.uid(), and avoid auth.role()';
    end if;

    if exists (
        select 1
        from pg_proc procedure_row
        join pg_namespace namespace_row on namespace_row.oid = procedure_row.pronamespace
        where procedure_row.prosecdef
          and namespace_row.nspname in ('construction','ingestion','semantic')
    ) then
        raise exception 'SECURITY DEFINER function exists in an exposed application schema';
    end if;

    if exists (
        select 1
        from pg_proc procedure_row
        join pg_namespace namespace_row on namespace_row.oid = procedure_row.pronamespace
        where procedure_row.prosecdef
          and namespace_row.nspname = 'construction_private'
          and not exists (
              select 1
              from unnest(coalesce(procedure_row.proconfig, array[]::text[])) setting
              where setting in ('search_path=','search_path=""')
          )
    ) then
        raise exception 'private SECURITY DEFINER function lacks an empty search_path';
    end if;

    if exists (
        select 1
        from pg_proc procedure_row
        join pg_namespace namespace_row on namespace_row.oid = procedure_row.pronamespace
        where procedure_row.prosecdef
          and namespace_row.nspname = 'construction_private'
          and pg_get_functiondef(procedure_row.oid) !~ 'auth\.uid\(\)'
    ) then
        raise exception 'private SECURITY DEFINER function lacks an internal auth.uid() check';
    end if;

    if exists (
        select 1
        from pg_proc procedure_row
        join pg_namespace namespace_row on namespace_row.oid = procedure_row.pronamespace
        where namespace_row.nspname = 'construction_private'
          and (
              has_function_privilege('anon', procedure_row.oid, 'EXECUTE')
              or has_function_privilege('service_role', procedure_row.oid, 'EXECUTE')
          )
    ) then
        raise exception 'anon or service_role can execute a private helper';
    end if;

    if exists (
        select 1
        from pg_proc procedure_row
        join pg_namespace namespace_row on namespace_row.oid = procedure_row.pronamespace
        where namespace_row.nspname = 'construction_private'
          and has_function_privilege('authenticated', procedure_row.oid, 'EXECUTE')
          and procedure_row.proname not in (
              'is_org_member','can_manage_org','can_admin_org','can_read_project',
              'publish_import_batch_internal','publish_chunk_embeddings_internal'
          )
    ) then
        raise exception 'authenticated can execute an unapproved private helper';
    end if;

    if not has_function_privilege(
        'authenticated',
        'construction_private.publish_import_batch_internal(uuid,uuid,text)',
        'EXECUTE'
    ) or not has_function_privilege(
        'authenticated',
        'construction_private.publish_chunk_embeddings_internal(uuid,uuid,jsonb,text)',
        'EXECUTE'
    ) then
        raise exception 'an authenticated controlled-publication gateway is not executable';
    end if;
    if not has_function_privilege(
        'authenticated', 'ingestion.publish_import_batch(uuid,uuid,text)', 'EXECUTE'
    ) or not has_function_privilege(
        'authenticated', 'semantic.publish_chunk_embeddings(uuid,uuid,jsonb,text)', 'EXECUTE'
    ) or has_function_privilege(
        'anon', 'ingestion.publish_import_batch(uuid,uuid,text)', 'EXECUTE'
    ) or has_function_privilege(
        'anon', 'semantic.publish_chunk_embeddings(uuid,uuid,jsonb,text)', 'EXECUTE'
    ) or has_function_privilege(
        'service_role', 'ingestion.publish_import_batch(uuid,uuid,text)', 'EXECUTE'
    ) or has_function_privilege(
        'service_role', 'semantic.publish_chunk_embeddings(uuid,uuid,jsonb,text)', 'EXECUTE'
    ) then
        raise exception 'controlled-publication wrapper EXECUTE grants are not least privilege';
    end if;

    if not exists (
        select 1
        from pg_attribute attribute_row
        where attribute_row.attrelid = 'semantic.semantic_chunks'::regclass
          and attribute_row.attname = 'embedding'
          and pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) like '%vector(1536)'
    ) then
        raise exception 'semantic chunk embedding is not vector(1536)';
    end if;

    if not exists (
        select 1
        from pg_index index_row
        join pg_class index_class on index_class.oid = index_row.indexrelid
        join pg_opclass operator_class on operator_class.oid = any(index_row.indclass)
        join pg_namespace operator_namespace on operator_namespace.oid = operator_class.opcnamespace
        where index_row.indrelid = 'semantic.semantic_chunks'::regclass
          and index_class.relam = (select oid from pg_am where amname = 'hnsw')
          and operator_class.opcname = 'vector_cosine_ops'
          and operator_namespace.nspname = 'extensions'
    ) then
        raise exception 'semantic chunk HNSW index does not use extensions.vector_cosine_ops';
    end if;

    if not exists (
        select 1
        from pg_attribute attribute_row
        where attribute_row.attrelid = 'semantic.semantic_chunks'::regclass
          and attribute_row.attname = 'search_vector'
          and attribute_row.attgenerated = 's'
    ) then
        raise exception 'semantic chunk search_vector is not stored-generated';
    end if;

    if has_schema_privilege('anon', 'construction_private', 'USAGE')
       or has_table_privilege('authenticated', 'construction_private.ingestion_publication_targets', 'SELECT') then
        raise exception 'private helper schema or publication whitelist is exposed';
    end if;

    if has_table_privilege('authenticated', 'semantic.semantic_chunks', 'INSERT')
       or has_table_privilege('authenticated', 'semantic.semantic_chunks', 'UPDATE')
       or has_table_privilege('authenticated', 'semantic.semantic_chunks', 'DELETE') then
        raise exception 'authenticated may mutate semantic chunks outside the controlled routine';
    end if;
    if has_table_privilege('anon', 'semantic.semantic_chunks', 'SELECT')
       or has_table_privilege('service_role', 'semantic.semantic_chunks', 'SELECT') then
        raise exception 'semantic chunks are readable by a non-authenticated application role';
    end if;

    if exists (
        select 1
        from information_schema.tables table_row
        where table_row.table_schema = 'construction'
          and table_row.table_type = 'BASE TABLE'
          and (
              has_table_privilege('authenticated', format('%I.%I', table_row.table_schema, table_row.table_name), 'INSERT')
              or has_table_privilege('authenticated', format('%I.%I', table_row.table_schema, table_row.table_name), 'UPDATE')
              or has_table_privilege('authenticated', format('%I.%I', table_row.table_schema, table_row.table_name), 'DELETE')
          )
    ) then
        raise exception 'authenticated retains direct construction base-table write privileges';
    end if;

    if exists (
        select 1
        from construction_private.ingestion_publication_targets target
        where not exists (
            select 1
            from pg_index index_row
            where index_row.indrelid = format('construction.%I', target.target_table)::regclass
              and index_row.indisunique
              and index_row.indisvalid
              and index_row.indpred is null
              and (
                  select array_agg(attribute_row.attname::text order by key_row.ordinality)
                  from unnest(index_row.indkey) with ordinality key_row(attnum, ordinality)
                  join pg_attribute attribute_row
                    on attribute_row.attrelid = index_row.indrelid
                   and attribute_row.attnum = key_row.attnum
                  where key_row.ordinality <= index_row.indnkeyatts
              ) = target.business_key_columns
        )
    ) then
        raise exception 'a publication whitelist conflict key lacks a usable unique constraint';
    end if;

    if exists (
        select 1
        from construction_private.ingestion_publication_targets target
        where target.requires_project_id
          and not exists (
              select 1 from information_schema.columns column_row
              where column_row.table_schema = 'construction'
                and column_row.table_name = target.target_table
                and column_row.column_name = 'project_id'
          )
    ) then
        raise exception 'a project-scoped publication target lacks project_id';
    end if;

    if pg_get_functiondef('construction_private.publish_import_batch_internal(uuid,uuid,text)'::regprocedure)
       ~* 'returning[[:space:]]+id[[:space:]]*,[[:space:]]*project_id' then
        raise exception 'publication SQL still assumes every target returns project_id';
    end if;

    if (
        select count(*)
        from regexp_matches(
            pg_get_functiondef('semantic.hybrid_search(uuid,uuid[],text,extensions.vector,integer,text,text,integer)'::regprocedure),
            'chunk\.projection_version = requested_projection_version',
            'g'
        )
    ) <> 3 or (
        select count(*)
        from regexp_matches(
            pg_get_functiondef('semantic.hybrid_search(uuid,uuid[],text,extensions.vector,integer,text,text,integer)'::regprocedure),
            'chunk\.chunking_version = requested_chunking_version',
            'g'
        )
    ) <> 3 or (
        select count(*)
        from regexp_matches(
            pg_get_functiondef('semantic.hybrid_search(uuid,uuid[],text,extensions.vector,integer,text,text,integer)'::regprocedure),
            'chunk\.embedding_dimensions = 1536',
            'g'
        )
    ) <> 3 then
        raise exception 'hybrid search does not repeat version/chunking/dimension filters in all branches';
    end if;

    if not pg_has_role('prosight_backend', 'authenticated', 'MEMBER') then
        raise exception 'prosight_backend cannot explicitly enter authenticated for redesigned requests';
    end if;
    if exists (
        select 1 from pg_roles role_row
        where role_row.rolname = 'prosight_backend'
          and (
              role_row.rolcanlogin or role_row.rolinherit or role_row.rolsuper
              or role_row.rolcreaterole or role_row.rolcreatedb
              or role_row.rolreplication or role_row.rolbypassrls
          )
    ) then
        raise exception 'prosight_backend lost its NOLOGIN/NOINHERIT least-privilege posture';
    end if;
    if has_schema_privilege('prosight_backend', 'construction', 'USAGE')
       or has_schema_privilege('prosight_backend', 'ingestion', 'USAGE')
       or has_schema_privilege('prosight_backend', 'semantic', 'USAGE') then
        raise exception 'prosight_backend inherited redesigned-schema access without SET ROLE';
    end if;
    if current_setting('server_version_num')::integer >= 160000 then
        execute $membership$
            select membership.inherit_option, membership.set_option
            from pg_catalog.pg_auth_members membership
            where membership.roleid = (select oid from pg_catalog.pg_roles where rolname = 'authenticated')
              and membership.member = (select oid from pg_catalog.pg_roles where rolname = 'prosight_backend')
        $membership$
        into strict membership_inherits, membership_can_set;
        if membership_inherits or not membership_can_set then
            raise exception 'prosight_backend membership must be INHERIT FALSE, SET TRUE';
        end if;
    end if;
end
$verification$;

set local role prosight_backend;
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
do $request_role_contract$
begin
    if auth.uid() is distinct from '00000000-0000-0000-0000-000000000001'::uuid
       or current_user <> 'authenticated' then
        raise exception 'request-scoped authenticated role/JWT contract is not operational';
    end if;
end
$request_role_contract$;
reset role;

rollback;
