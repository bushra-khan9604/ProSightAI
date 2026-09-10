-- Additive integrity hardening for the generic construction schema.
-- The local Supabase CLI allocated this migration filename; it is not remotely applied here.

begin;

-- Later nullable project scopes map NULL to this reserved UUID. Prevent a real
-- project from colliding with that sentinel before those schemas are created.
alter table construction.projects
    add constraint projects_reserved_scope_id_check
    check (id <> '00000000-0000-0000-0000-000000000000'::uuid);

-- Every tenant-owned target exposes the two-column tenant identity required by
-- downstream schemas. Project-owned targets additionally expose a project-aware
-- identity so relationships can prove same-project ownership with a foreign key.
do $constraints$
declare
    target record;
    constraint_name text;
begin
    for target in
        select table_name
        from information_schema.columns
        where table_schema = 'construction'
          and column_name = 'organization_id'
          and table_name <> 'organizations'
        order by table_name
    loop
        if not exists (
            select 1
            from pg_constraint constraint_row
            where constraint_row.conrelid = format('construction.%I', target.table_name)::regclass
              and constraint_row.contype = 'u'
              and pg_get_constraintdef(constraint_row.oid) = 'UNIQUE (organization_id, id)'
        ) then
            constraint_name := left(target.table_name || '_org_id_id_key', 63);
            execute format(
                'alter table construction.%I add constraint %I unique (organization_id, id)',
                target.table_name,
                constraint_name
            );
        end if;
    end loop;

    for target in
        select table_name
        from information_schema.columns
        where table_schema = 'construction'
          and column_name = 'project_id'
        order by table_name
    loop
        if not exists (
            select 1
            from pg_constraint constraint_row
            where constraint_row.conrelid = format('construction.%I', target.table_name)::regclass
              and constraint_row.contype = 'u'
              and pg_get_constraintdef(constraint_row.oid) = 'UNIQUE (organization_id, project_id, id)'
        ) then
            constraint_name := left(target.table_name || '_org_project_id_key', 63);
            execute format(
                'alter table construction.%I add constraint %I unique (organization_id, project_id, id)',
                target.table_name,
                constraint_name
            );
        end if;
    end loop;
end
$constraints$;

alter table construction.project_members
    add constraint project_members_org_project_user_key
    unique (organization_id, project_id, user_id);

-- Identity-bearing audit/approval columns reference Supabase Auth; the Auth
-- system table is referenced only and is never created or altered here.
do $auth_foreign_keys$
declare
    identity_link record;
begin
    for identity_link in
        select *
        from (values
            ('organizations','created_by'), ('organizations','updated_by'),
            ('clients','created_by'), ('clients','updated_by'),
            ('projects','created_by'), ('projects','updated_by'),
            ('employees','created_by'), ('employees','updated_by'),
            ('attendance_records','approved_by'), ('timesheets','approved_by'),
            ('schedule_baselines','approved_by'), ('progress_updates','submitted_by'),
            ('progress_updates','approved_by'), ('budgets','approved_by'),
            ('cost_forecasts','approved_by'), ('business_partners','created_by'),
            ('business_partners','updated_by'), ('procurement_packages','responsible_user_id'),
            ('contracts','created_by'), ('contracts','updated_by'),
            ('purchase_orders','approved_by'), ('material_receipts','received_by'),
            ('invoices','approved_by'), ('change_orders','created_by'),
            ('change_orders','updated_by'), ('risks','owner_user_id'),
            ('documents','created_by'), ('documents','updated_by'),
            ('document_revisions','submitted_by'), ('document_revisions','reviewed_by'),
            ('document_revisions','approved_by'), ('action_items','assigned_to_user_id'),
            ('nonconformance_reports','verified_by'), ('permits','responsible_user_id'),
            ('punch_list_items','verified_by'), ('estimates','prepared_by'),
            ('estimates','approved_by'), ('payment_applications','certified_by'),
            ('daily_reports','prepared_by'), ('daily_reports','approved_by'),
            ('inspection_test_plans','approved_by')
        ) as links(table_name, column_name)
    loop
        execute format(
            'alter table construction.%I add constraint %I foreign key (%I) references auth.users(id) on delete set null',
            identity_link.table_name,
            left(identity_link.table_name || '_' || identity_link.column_name || '_auth_fkey', 63),
            identity_link.column_name
        );
    end loop;
end
$auth_foreign_keys$;

-- These links must identify a parent in the same organization and project.
-- Existing organization-only constraints retain their declared delete action;
-- the additional project-aware constraint supplies the independent scope proof.
do $project_foreign_keys$
declare
    project_link record;
begin
    for project_link in
        select *
        from (values
            ('project_milestones','phase_id','project_phases'),
            ('timesheets','activity_id','activities'),
            ('boq_items','wbs_item_id','wbs_items'),
            ('activities','wbs_item_id','wbs_items'),
            ('activity_dependencies','predecessor_id','activities'),
            ('activity_dependencies','successor_id','activities'),
            ('progress_updates','activity_id','activities'),
            ('progress_updates','wbs_item_id','wbs_items'),
            ('budget_lines','budget_id','budgets'),
            ('budget_lines','wbs_item_id','wbs_items'),
            ('bids','procurement_package_id','procurement_packages'),
            ('contract_line_items','contract_id','contracts'),
            ('contract_line_items','boq_item_id','boq_items'),
            ('purchase_orders','contract_id','contracts'),
            ('purchase_order_items','purchase_order_id','purchase_orders'),
            ('material_receipts','purchase_order_item_id','purchase_order_items'),
            ('equipment_assignments','activity_id','activities'),
            ('invoices','contract_id','contracts'),
            ('invoice_items','invoice_id','invoices'),
            ('invoice_items','contract_line_item_id','contract_line_items'),
            ('payments','invoice_id','invoices'),
            ('commitments','contract_id','contracts'),
            ('commitments','purchase_order_id','purchase_orders'),
            ('retention_records','contract_id','contracts'),
            ('retention_records','invoice_id','invoices'),
            ('change_orders','contract_id','contracts'),
            ('contract_notices','contract_id','contracts'),
            ('contract_notices','related_change_order_id','change_orders'),
            ('claims','contract_id','contracts'),
            ('insurance_policies','storage_document_id','documents'),
            ('document_revisions','document_id','documents'),
            ('transmittal_items','transmittal_id','transmittals'),
            ('transmittal_items','document_revision_id','document_revisions'),
            ('drawings','document_id','documents'),
            ('rfis','related_document_id','documents'),
            ('submittals','document_id','documents'),
            ('meetings','document_id','documents'),
            ('action_items','meeting_id','meetings'),
            ('quality_inspections','document_id','documents'),
            ('permits','document_id','documents'),
            ('handover_items','handover_package_id','handover_packages'),
            ('handover_items','document_id','documents'),
            ('warranties','document_id','documents'),
            ('final_accounts','contract_id','contracts'),
            ('estimate_items','estimate_id','estimates'),
            ('estimate_items','wbs_item_id','wbs_items'),
            ('payment_applications','contract_id','contracts'),
            ('inspection_test_plans','activity_id','activities'),
            ('documents','current_revision_id','document_revisions')
        ) as links(child_table, child_column, parent_table)
    loop
        execute format(
            'alter table construction.%I add constraint %I foreign key (organization_id, project_id, %I) references construction.%I (organization_id, project_id, id) deferrable initially immediate',
            project_link.child_table,
            left(project_link.child_table || '_' || project_link.child_column || '_project_fkey', 63),
            project_link.child_column,
            project_link.parent_table
        );
    end loop;
end
$project_foreign_keys$;

-- PostgreSQL does not automatically index referencing columns. Repeat the
-- catalog-driven index pass after adding the hardening foreign keys.
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
          and namespace_row.nspname = 'construction'
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

create index document_revisions_retrieval_idx
    on construction.document_revisions (organization_id, project_id, document_id, status, revision_date desc);
create index document_revisions_approved_idx
    on construction.document_revisions (organization_id, project_id, document_id, approved_at desc)
    where status = 'approved';
create index project_members_active_lookup_idx
    on construction.project_members (organization_id, project_id, user_id)
    where is_active;
create index organization_members_active_role_idx
    on construction.organization_members (organization_id, user_id, role)
    where is_active;

revoke all on schema construction from public, anon, service_role;
revoke all on all tables in schema construction from public, anon, service_role;
alter default privileges in schema construction revoke all on tables from public, anon, service_role;

comment on column construction.projects.access_mode is
'organization permits every active organization member; restricted permits owners, admins, managers, and active project members.';
comment on column construction.documents.current_revision_id is
'Points only to an approved revision of the same logical document and project; binary provenance remains on document_revisions.';

commit;
