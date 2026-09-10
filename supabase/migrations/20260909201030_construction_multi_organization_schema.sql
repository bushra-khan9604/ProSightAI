-- Generic multi-organization construction operations schema.
-- This migration intentionally coexists with the application-owned `prosight`
-- schema. It contains no organization-specific names or seed data.

begin;

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create schema if not exists construction;
create schema if not exists construction_private;

revoke all on schema construction from public, anon, service_role;
revoke all on schema construction_private from public, anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Company and project registers
-- ---------------------------------------------------------------------------

create table construction.organizations (
    id uuid primary key default extensions.gen_random_uuid(),
    code text not null,
    legal_name text not null,
    trading_name text,
    registration_number text,
    tax_registration_number text,
    organization_type text not null default 'contractor',
    base_currency_code text not null default 'USD',
    country_code text,
    timezone text not null default 'UTC',
    email text,
    phone text,
    website text,
    address jsonb not null default '{}'::jsonb,
    settings jsonb not null default '{}'::jsonb,
    status text not null default 'active' check (status in ('active','inactive','suspended')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    unique (code)
);

create table construction.organization_members (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('owner','admin','manager','member','viewer')),
    job_title text,
    is_active boolean not null default true,
    invited_at timestamptz,
    joined_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, user_id)
);

create table construction.business_units (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    parent_id uuid,
    code text not null,
    name text not null,
    unit_type text not null default 'division',
    manager_user_id uuid references auth.users(id) on delete set null,
    cost_center_code text,
    address jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, code),
    unique (organization_id, id)
);

create table construction.clients (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    code text not null,
    legal_name text not null,
    registration_number text,
    tax_registration_number text,
    industry text,
    email text,
    phone text,
    website text,
    billing_address jsonb not null default '{}'::jsonb,
    payment_terms_days integer check (payment_terms_days is null or payment_terms_days >= 0),
    credit_limit numeric(20,2) check (credit_limit is null or credit_limit >= 0),
    status text not null default 'active',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    unique (organization_id, code),
    unique (organization_id, id)
);

create table construction.contacts (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    client_id uuid,
    first_name text not null,
    last_name text,
    company_name text,
    job_title text,
    contact_type text,
    email text,
    phone text,
    mobile text,
    address jsonb not null default '{}'::jsonb,
    is_primary boolean not null default false,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, client_id) references construction.clients(organization_id, id) on delete cascade
);

create table construction.projects (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    business_unit_id uuid,
    client_id uuid,
    code text not null,
    name text not null,
    description text,
    project_type text,
    delivery_method text,
    contract_type text,
    status text not null default 'planning',
    access_mode text not null default 'organization'
        check (access_mode in ('organization','restricted')),
    country_code text,
    location text,
    latitude numeric(10,7),
    longitude numeric(10,7),
    currency_code text not null default 'USD',
    contract_value numeric(20,2) check (contract_value is null or contract_value >= 0),
    original_budget numeric(20,2) check (original_budget is null or original_budget >= 0),
    gross_floor_area numeric(20,3) check (gross_floor_area is null or gross_floor_area >= 0),
    planned_start_date date,
    planned_finish_date date,
    actual_start_date date,
    actual_finish_date date,
    reporting_date date,
    progress_percent numeric(7,4) not null default 0 check (progress_percent between 0 and 100),
    retention_percent numeric(7,4) default 0 check (retention_percent between 0 and 100),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    unique (organization_id, code),
    unique (organization_id, id),
    foreign key (organization_id, business_unit_id) references construction.business_units(organization_id, id) on delete set null (business_unit_id),
    foreign key (organization_id, client_id) references construction.clients(organization_id, id) on delete set null (client_id),
    check (planned_finish_date is null or planned_start_date is null or planned_finish_date >= planned_start_date),
    check (actual_finish_date is null or actual_start_date is null or actual_finish_date >= actual_start_date)
);

create table construction.project_members (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null default 'member',
    discipline text,
    start_date date,
    end_date date,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, user_id) references construction.organization_members(organization_id, user_id) on delete cascade,
    unique (project_id, user_id)
);

create table construction.project_stakeholders (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contact_id uuid,
    stakeholder_type text not null,
    company_name text,
    contact_name text,
    email text,
    phone text,
    responsibility text,
    influence_level text,
    communication_requirements text,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade
);

create table construction.project_phases (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    code text not null,
    name text not null,
    sequence_no integer not null default 0,
    planned_start_date date,
    planned_finish_date date,
    actual_start_date date,
    actual_finish_date date,
    progress_percent numeric(7,4) not null default 0 check (progress_percent between 0 and 100),
    status text not null default 'not_started',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, code)
);

create table construction.project_milestones (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    phase_id uuid,
    code text not null,
    name text not null,
    milestone_type text,
    baseline_date date,
    forecast_date date,
    actual_date date,
    status text not null default 'pending',
    is_contractual boolean not null default false,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, code)
);

-- ---------------------------------------------------------------------------
-- Employees, training and attendance
-- ---------------------------------------------------------------------------

create table construction.employees (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    business_unit_id uuid,
    employee_number text not null,
    auth_user_id uuid references auth.users(id) on delete set null,
    first_name text not null,
    last_name text,
    preferred_name text,
    work_email text,
    personal_email text,
    phone text,
    nationality_code text,
    job_title text,
    department text,
    employment_type text not null default 'employee',
    hire_date date,
    termination_date date,
    standard_hours_per_day numeric(6,2) default 8 check (standard_hours_per_day > 0),
    base_hourly_rate numeric(20,4) check (base_hourly_rate is null or base_hourly_rate >= 0),
    currency_code text,
    emergency_contact jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    unique (organization_id, employee_number),
    unique (organization_id, id),
    foreign key (organization_id, business_unit_id) references construction.business_units(organization_id, id) on delete set null (business_unit_id),
    check (termination_date is null or hire_date is null or termination_date >= hire_date)
);

create table construction.employee_assignments (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    employee_id uuid not null,
    role text,
    discipline text,
    allocation_percent numeric(7,4) default 100 check (allocation_percent between 0 and 100),
    start_date date not null,
    end_date date,
    billing_rate numeric(20,4) check (billing_rate is null or billing_rate >= 0),
    currency_code text,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, employee_id) references construction.employees(organization_id, id) on delete cascade,
    check (end_date is null or end_date >= start_date)
);

create table construction.training_courses (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    code text not null,
    name text not null,
    provider text,
    category text,
    validity_months integer check (validity_months is null or validity_months > 0),
    mandatory boolean not null default false,
    description text,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, code),
    unique (organization_id, id)
);

create table construction.employee_training (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    employee_id uuid not null,
    course_id uuid not null,
    enrollment_date date,
    completion_date date,
    expiry_date date,
    result text,
    score numeric(7,4) check (score is null or score between 0 and 100),
    certificate_number text,
    certificate_document_id uuid,
    status text not null default 'planned',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, employee_id) references construction.employees(organization_id, id) on delete cascade,
    foreign key (organization_id, course_id) references construction.training_courses(organization_id, id) on delete cascade
);

create table construction.attendance_records (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    employee_id uuid not null,
    attendance_date date not null,
    shift_code text,
    check_in_at timestamptz,
    check_out_at timestamptz,
    regular_hours numeric(7,2) not null default 0 check (regular_hours >= 0),
    overtime_hours numeric(7,2) not null default 0 check (overtime_hours >= 0),
    break_hours numeric(7,2) not null default 0 check (break_hours >= 0),
    attendance_status text not null default 'present',
    source text,
    location jsonb not null default '{}'::jsonb,
    approved_by uuid,
    approved_at timestamptz,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete set null (project_id),
    foreign key (organization_id, employee_id) references construction.employees(organization_id, id) on delete cascade,
    unique (employee_id, attendance_date, shift_code),
    check (check_out_at is null or check_in_at is null or check_out_at >= check_in_at)
);

create table construction.timesheets (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    employee_id uuid not null,
    work_date date not null,
    activity_id uuid,
    cost_code_id uuid,
    regular_hours numeric(7,2) not null default 0 check (regular_hours >= 0),
    overtime_hours numeric(7,2) not null default 0 check (overtime_hours >= 0),
    description text,
    status text not null default 'draft',
    submitted_at timestamptz,
    approved_by uuid,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, employee_id) references construction.employees(organization_id, id) on delete cascade
);

-- ---------------------------------------------------------------------------
-- Planning, BOQ, schedule and cost control
-- ---------------------------------------------------------------------------

create table construction.wbs_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    parent_id uuid,
    code text not null,
    name text not null,
    description text,
    level_no integer not null default 1 check (level_no > 0),
    sequence_no integer not null default 0,
    planned_start_date date,
    planned_finish_date date,
    budget_amount numeric(20,2) check (budget_amount is null or budget_amount >= 0),
    progress_percent numeric(7,4) not null default 0 check (progress_percent between 0 and 100),
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, code)
);

create table construction.cost_codes (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    parent_id uuid,
    code text not null,
    name text not null,
    cost_type text,
    description text,
    is_billable boolean not null default true,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (organization_id, project_id, code),
    unique (organization_id, id)
);

create table construction.boq_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    wbs_item_id uuid,
    cost_code_id uuid,
    item_number text not null,
    description text not null,
    specification_reference text,
    unit_code text not null,
    quantity numeric(20,4) not null default 0 check (quantity >= 0),
    unit_rate numeric(20,4) not null default 0 check (unit_rate >= 0),
    currency_code text not null,
    amount numeric(20,2) generated always as (round(quantity * unit_rate, 2)) stored,
    variation_quantity numeric(20,4) not null default 0,
    completed_quantity numeric(20,4) not null default 0 check (completed_quantity >= 0),
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    unique (project_id, item_number)
);

create table construction.activities (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    wbs_item_id uuid,
    activity_code text not null,
    name text not null,
    description text,
    activity_type text,
    calendar_code text,
    original_duration_days numeric(10,2) check (original_duration_days is null or original_duration_days >= 0),
    remaining_duration_days numeric(10,2) check (remaining_duration_days is null or remaining_duration_days >= 0),
    baseline_start_date date,
    baseline_finish_date date,
    planned_start_date date,
    planned_finish_date date,
    forecast_start_date date,
    forecast_finish_date date,
    actual_start_date date,
    actual_finish_date date,
    progress_percent numeric(7,4) not null default 0 check (progress_percent between 0 and 100),
    is_critical boolean not null default false,
    total_float_days numeric(10,2),
    status text not null default 'not_started',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, activity_code)
);

create table construction.activity_dependencies (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    predecessor_id uuid not null,
    successor_id uuid not null,
    dependency_type text not null default 'FS' check (dependency_type in ('FS','SS','FF','SF')),
    lag_days numeric(10,2) not null default 0,
    created_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (predecessor_id, successor_id, dependency_type),
    check (predecessor_id <> successor_id)
);

create table construction.schedule_baselines (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    code text not null,
    name text not null,
    baseline_date date not null,
    revision_no integer not null default 0,
    approved_by uuid,
    approved_at timestamptz,
    status text not null default 'draft',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, code, revision_no)
);

create table construction.progress_updates (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    activity_id uuid,
    wbs_item_id uuid,
    reporting_date date not null,
    planned_percent numeric(7,4) check (planned_percent is null or planned_percent between 0 and 100),
    actual_percent numeric(7,4) not null check (actual_percent between 0 and 100),
    quantity_completed numeric(20,4),
    remaining_duration_days numeric(10,2),
    forecast_finish_date date,
    narrative text,
    submitted_by uuid,
    approved_by uuid,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    check (activity_id is not null or wbs_item_id is not null)
);

create table construction.budgets (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    code text not null,
    name text not null,
    version_no integer not null default 1,
    currency_code text not null,
    effective_date date,
    approved_by uuid,
    approved_at timestamptz,
    status text not null default 'draft',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, code, version_no),
    unique (organization_id, id)
);

create table construction.budget_lines (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    budget_id uuid not null,
    cost_code_id uuid,
    wbs_item_id uuid,
    description text,
    original_amount numeric(20,2) not null default 0 check (original_amount >= 0),
    approved_changes numeric(20,2) not null default 0,
    current_budget numeric(20,2) generated always as (original_amount + approved_changes) stored,
    forecast_at_completion numeric(20,2),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, budget_id) references construction.budgets(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id)
);

create table construction.cost_transactions (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    cost_code_id uuid,
    transaction_type text not null,
    transaction_date date not null,
    accounting_period date,
    reference_number text,
    description text not null,
    quantity numeric(20,4),
    unit_rate numeric(20,4),
    amount numeric(20,2) not null,
    currency_code text not null,
    exchange_rate numeric(20,8) not null default 1 check (exchange_rate > 0),
    base_currency_amount numeric(20,2) not null,
    source_type text,
    source_id uuid,
    status text not null default 'posted',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id)
);

create table construction.cost_forecasts (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    cost_code_id uuid,
    reporting_date date not null,
    current_budget numeric(20,2) not null default 0,
    actual_cost numeric(20,2) not null default 0,
    committed_cost numeric(20,2) not null default 0,
    estimate_to_complete numeric(20,2) not null default 0,
    estimate_at_completion numeric(20,2) not null default 0,
    variance_at_completion numeric(20,2) not null default 0,
    currency_code text not null,
    basis text,
    approved_by uuid,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    unique (project_id, cost_code_id, reporting_date)
);

-- ---------------------------------------------------------------------------
-- Procurement, partners, equipment and commercial control
-- ---------------------------------------------------------------------------

create table construction.business_partners (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    code text not null,
    legal_name text not null,
    trading_name text,
    partner_type text not null check (partner_type in ('vendor','subcontractor','consultant','supplier','other')),
    registration_number text,
    tax_registration_number text,
    country_code text,
    email text,
    phone text,
    address jsonb not null default '{}'::jsonb,
    payment_terms_days integer check (payment_terms_days is null or payment_terms_days >= 0),
    bank_details_encrypted text,
    prequalification_status text,
    safety_rating numeric(7,4),
    quality_rating numeric(7,4),
    commercial_rating numeric(7,4),
    status text not null default 'active',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    unique (organization_id, code),
    unique (organization_id, id)
);

create table construction.partner_contacts (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    partner_id uuid not null,
    first_name text not null,
    last_name text,
    job_title text,
    email text,
    phone text,
    mobile text,
    is_primary boolean not null default false,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete cascade
);

create table construction.procurement_packages (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    package_number text not null,
    title text not null,
    scope_description text,
    procurement_method text,
    budget_amount numeric(20,2) check (budget_amount is null or budget_amount >= 0),
    currency_code text,
    issue_date date,
    bid_due_date timestamptz,
    award_target_date date,
    responsible_user_id uuid,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, package_number),
    unique (organization_id, id)
);

create table construction.bids (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    procurement_package_id uuid not null,
    partner_id uuid not null,
    bid_reference text,
    submitted_at timestamptz,
    bid_amount numeric(20,2) not null check (bid_amount >= 0),
    currency_code text not null,
    normalized_amount numeric(20,2),
    technical_score numeric(7,4),
    commercial_score numeric(7,4),
    overall_score numeric(7,4),
    validity_date date,
    exclusions text,
    clarifications text,
    recommendation text,
    status text not null default 'received',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, procurement_package_id) references construction.procurement_packages(organization_id, id) on delete cascade,
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete restrict,
    unique (procurement_package_id, partner_id)
);

create table construction.contracts (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    partner_id uuid,
    client_id uuid,
    contract_number text not null,
    title text not null,
    contract_category text not null,
    contract_type text,
    scope_description text,
    award_date date,
    commencement_date date,
    planned_completion_date date,
    actual_completion_date date,
    original_value numeric(20,2) not null default 0 check (original_value >= 0),
    approved_variations_value numeric(20,2) not null default 0,
    currency_code text not null,
    retention_percent numeric(7,4) not null default 0 check (retention_percent between 0 and 100),
    advance_payment_percent numeric(7,4) not null default 0 check (advance_payment_percent between 0 and 100),
    payment_terms_days integer check (payment_terms_days is null or payment_terms_days >= 0),
    governing_law text,
    defects_liability_months integer check (defects_liability_months is null or defects_liability_months >= 0),
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete restrict,
    foreign key (organization_id, client_id) references construction.clients(organization_id, id) on delete restrict,
    unique (project_id, contract_number),
    unique (organization_id, id)
);

create table construction.contract_line_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid not null,
    boq_item_id uuid,
    cost_code_id uuid,
    line_number text not null,
    description text not null,
    unit_code text,
    quantity numeric(20,4) not null default 0 check (quantity >= 0),
    unit_rate numeric(20,4) not null default 0 check (unit_rate >= 0),
    amount numeric(20,2) generated always as (round(quantity * unit_rate, 2)) stored,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    unique (contract_id, line_number)
);

create table construction.purchase_orders (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    partner_id uuid not null,
    contract_id uuid,
    po_number text not null,
    order_date date not null,
    required_date date,
    delivery_location text,
    currency_code text not null,
    subtotal numeric(20,2) not null default 0,
    tax_amount numeric(20,2) not null default 0,
    total_amount numeric(20,2) not null default 0,
    payment_terms text,
    incoterms text,
    approved_by uuid,
    approved_at timestamptz,
    status text not null default 'draft',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete restrict,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete set null (contract_id),
    unique (project_id, po_number),
    unique (organization_id, id)
);

create table construction.purchase_order_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    purchase_order_id uuid not null,
    cost_code_id uuid,
    line_number integer not null,
    item_code text,
    description text not null,
    unit_code text,
    quantity numeric(20,4) not null check (quantity > 0),
    unit_price numeric(20,4) not null check (unit_price >= 0),
    tax_rate numeric(7,4) not null default 0 check (tax_rate between 0 and 100),
    line_amount numeric(20,2) not null,
    received_quantity numeric(20,4) not null default 0 check (received_quantity >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, purchase_order_id) references construction.purchase_orders(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    unique (purchase_order_id, line_number),
    unique (organization_id, id)
);

create table construction.material_receipts (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    purchase_order_item_id uuid not null,
    receipt_number text not null,
    received_at timestamptz not null,
    delivery_note_number text,
    batch_number text,
    quantity_received numeric(20,4) not null check (quantity_received > 0),
    quantity_accepted numeric(20,4) not null default 0 check (quantity_accepted >= 0),
    quantity_rejected numeric(20,4) not null default 0 check (quantity_rejected >= 0),
    inspection_status text not null default 'pending',
    storage_location text,
    received_by uuid,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, purchase_order_item_id) references construction.purchase_order_items(organization_id, id) on delete cascade,
    unique (project_id, receipt_number),
    check (quantity_accepted + quantity_rejected <= quantity_received)
);

create table construction.equipment (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    asset_number text not null,
    name text not null,
    equipment_type text,
    manufacturer text,
    model text,
    serial_number text,
    ownership_type text not null default 'owned',
    owner_partner_id uuid,
    purchase_date date,
    purchase_cost numeric(20,2),
    currency_code text,
    registration_number text,
    capacity text,
    current_meter numeric(20,2),
    meter_unit text,
    next_service_date date,
    next_service_meter numeric(20,2),
    status text not null default 'available',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, owner_partner_id) references construction.business_partners(organization_id, id) on delete set null (owner_partner_id),
    unique (organization_id, asset_number),
    unique (organization_id, id)
);

create table construction.equipment_assignments (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    equipment_id uuid not null,
    activity_id uuid,
    assigned_from timestamptz not null,
    assigned_until timestamptz,
    operator_employee_id uuid,
    hourly_rate numeric(20,4),
    currency_code text,
    start_meter numeric(20,2),
    end_meter numeric(20,2),
    status text not null default 'assigned',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, equipment_id) references construction.equipment(organization_id, id) on delete cascade,
    foreign key (organization_id, operator_employee_id) references construction.employees(organization_id, id) on delete set null (operator_employee_id),
    check (assigned_until is null or assigned_until >= assigned_from)
);

create table construction.invoices (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid,
    partner_id uuid,
    client_id uuid,
    invoice_number text not null,
    invoice_type text not null,
    direction text not null check (direction in ('receivable','payable')),
    invoice_date date not null,
    due_date date,
    period_start date,
    period_end date,
    currency_code text not null,
    subtotal numeric(20,2) not null default 0,
    tax_amount numeric(20,2) not null default 0,
    retention_amount numeric(20,2) not null default 0,
    advance_recovery_amount numeric(20,2) not null default 0,
    total_amount numeric(20,2) not null default 0,
    certified_amount numeric(20,2),
    paid_amount numeric(20,2) not null default 0,
    status text not null default 'draft',
    approved_by uuid,
    approved_at timestamptz,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete set null (contract_id),
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete restrict,
    foreign key (organization_id, client_id) references construction.clients(organization_id, id) on delete restrict,
    unique (project_id, direction, invoice_number),
    unique (organization_id, id),
    check (period_end is null or period_start is null or period_end >= period_start)
);

create table construction.invoice_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    invoice_id uuid not null,
    contract_line_item_id uuid,
    cost_code_id uuid,
    line_number integer not null,
    description text not null,
    quantity numeric(20,4) not null default 1,
    unit_rate numeric(20,4) not null default 0,
    gross_amount numeric(20,2) not null default 0,
    retention_amount numeric(20,2) not null default 0,
    tax_amount numeric(20,2) not null default 0,
    net_amount numeric(20,2) not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, invoice_id) references construction.invoices(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    unique (invoice_id, line_number)
);

create table construction.payments (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    invoice_id uuid,
    payment_reference text not null,
    payment_date date not null,
    payment_method text,
    direction text not null check (direction in ('received','paid')),
    amount numeric(20,2) not null check (amount > 0),
    currency_code text not null,
    exchange_rate numeric(20,8) not null default 1 check (exchange_rate > 0),
    bank_reference text,
    status text not null default 'posted',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, invoice_id) references construction.invoices(organization_id, id) on delete set null (invoice_id),
    unique (project_id, payment_reference)
);

create table construction.commitments (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid,
    purchase_order_id uuid,
    cost_code_id uuid,
    commitment_date date not null,
    description text,
    original_amount numeric(20,2) not null default 0,
    approved_changes numeric(20,2) not null default 0,
    invoiced_amount numeric(20,2) not null default 0,
    paid_amount numeric(20,2) not null default 0,
    currency_code text not null,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete set null (contract_id),
    foreign key (organization_id, purchase_order_id) references construction.purchase_orders(organization_id, id) on delete set null (purchase_order_id),
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    check (contract_id is not null or purchase_order_id is not null)
);

create table construction.retention_records (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid not null,
    invoice_id uuid,
    transaction_date date not null,
    transaction_type text not null check (transaction_type in ('withheld','released','adjusted')),
    amount numeric(20,2) not null,
    currency_code text not null,
    release_due_date date,
    released_at date,
    status text not null default 'held',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete cascade,
    foreign key (organization_id, invoice_id) references construction.invoices(organization_id, id) on delete set null (invoice_id)
);

-- ---------------------------------------------------------------------------
-- Contracts, changes, claims and risk
-- ---------------------------------------------------------------------------

create table construction.change_orders (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid,
    change_number text not null,
    title text not null,
    description text,
    change_type text,
    cause text,
    requested_by text,
    submitted_date date,
    required_decision_date date,
    approved_date date,
    estimated_cost_impact numeric(20,2) not null default 0,
    approved_cost_impact numeric(20,2),
    estimated_time_impact_days integer not null default 0,
    approved_time_impact_days integer,
    currency_code text,
    status text not null default 'draft',
    approval_notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete set null (contract_id),
    unique (project_id, change_number),
    unique (organization_id, id)
);

create table construction.contract_notices (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid not null,
    notice_number text not null,
    notice_type text not null,
    subject text not null,
    description text,
    event_date date,
    notice_date date not null,
    response_due_date date,
    responded_at date,
    issued_by text,
    issued_to text,
    related_change_order_id uuid,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete cascade,
    foreign key (organization_id, related_change_order_id) references construction.change_orders(organization_id, id) on delete set null (related_change_order_id),
    unique (contract_id, notice_number)
);

create table construction.claims (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid not null,
    claim_number text not null,
    claim_type text not null,
    title text not null,
    description text,
    event_start_date date,
    event_end_date date,
    notification_date date,
    submission_date date,
    claimed_amount numeric(20,2) not null default 0,
    assessed_amount numeric(20,2),
    approved_amount numeric(20,2),
    claimed_days integer not null default 0,
    assessed_days integer,
    approved_days integer,
    currency_code text,
    contractual_clause text,
    entitlement_basis text,
    status text not null default 'draft',
    resolution text,
    resolved_at date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete cascade,
    unique (contract_id, claim_number)
);

create table construction.risks (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    risk_number text not null,
    category text,
    title text not null,
    description text not null,
    cause text,
    consequence text,
    probability_score integer not null default 1 check (probability_score between 1 and 5),
    impact_score integer not null default 1 check (impact_score between 1 and 5),
    exposure_score integer generated always as (probability_score * impact_score) stored,
    financial_exposure numeric(20,2),
    currency_code text,
    owner_user_id uuid,
    response_strategy text,
    mitigation_plan text,
    contingency_plan text,
    target_date date,
    residual_probability_score integer check (residual_probability_score between 1 and 5),
    residual_impact_score integer check (residual_impact_score between 1 and 5),
    status text not null default 'open',
    closed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, risk_number)
);

create table construction.insurance_policies (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    partner_id uuid,
    policy_number text not null,
    policy_type text not null,
    insurer_name text not null,
    insured_party text,
    coverage_amount numeric(20,2),
    deductible_amount numeric(20,2),
    currency_code text,
    effective_date date not null,
    expiry_date date not null,
    storage_document_id uuid,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete set null (partner_id),
    unique (organization_id, policy_number),
    check (expiry_date >= effective_date)
);

-- ---------------------------------------------------------------------------
-- Technical and document control
-- ---------------------------------------------------------------------------

create table construction.documents (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    document_number text not null,
    title text not null,
    document_type text not null,
    discipline text,
    originator text,
    confidentiality text not null default 'internal',
    current_revision_id uuid,
    current_status text not null default 'draft',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid,
    updated_by uuid,
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (organization_id, project_id, document_number),
    unique (organization_id, id)
);

create table construction.document_revisions (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid,
    document_id uuid not null,
    revision_code text not null,
    revision_date date not null,
    title text,
    purpose_of_issue text,
    status text not null default 'draft'
        check (status in ('draft','in_review','approved','rejected','withdrawn','superseded')),
    storage_bucket text,
    storage_object_path text,
    checksum_sha256 text not null,
    mime_type text,
    file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
    submitted_by uuid,
    submitted_at timestamptz,
    uploaded_at timestamptz,
    verified_at timestamptz,
    reviewed_by uuid,
    reviewed_at timestamptz,
    approved_by uuid,
    approved_at timestamptz,
    review_comments text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete cascade,
    unique (document_id, revision_code),
    unique (storage_bucket, storage_object_path),
    unique (organization_id, checksum_sha256),
    check (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    check ((storage_bucket is null) = (storage_object_path is null)),
    check (
        status <> 'approved'
        or (
            storage_bucket is not null
            and storage_object_path is not null
            and mime_type is not null
            and file_size_bytes is not null
            and uploaded_at is not null
            and verified_at is not null
            and approved_by is not null
            and approved_at is not null
        )
    )
);

create table construction.transmittals (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    transmittal_number text not null,
    direction text not null check (direction in ('incoming','outgoing','internal')),
    subject text,
    sender_name text,
    recipient_name text,
    issued_at timestamptz not null,
    response_required boolean not null default false,
    response_due_date date,
    purpose text,
    status text not null default 'issued',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, transmittal_number),
    unique (organization_id, id)
);

create table construction.transmittal_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    transmittal_id uuid not null,
    document_revision_id uuid not null,
    action_required text,
    response_status text,
    response_date date,
    comments text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, transmittal_id) references construction.transmittals(organization_id, id) on delete cascade,
    unique (transmittal_id, document_revision_id)
);

create table construction.drawings (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    document_id uuid not null,
    drawing_number text not null,
    title text not null,
    discipline text,
    drawing_type text,
    area_or_zone text,
    scale text,
    current_revision text,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete cascade,
    unique (project_id, drawing_number)
);

create table construction.rfis (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    rfi_number text not null,
    subject text not null,
    question text not null,
    discipline text,
    location text,
    raised_by text,
    assigned_to text,
    raised_at timestamptz not null,
    response_due_date date,
    responded_at timestamptz,
    response text,
    cost_impact boolean,
    estimated_cost_impact numeric(20,2),
    schedule_impact boolean,
    estimated_delay_days integer,
    related_document_id uuid,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, related_document_id) references construction.documents(organization_id, id) on delete set null (related_document_id),
    unique (project_id, rfi_number)
);

create table construction.submittals (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    submittal_number text not null,
    title text not null,
    submittal_type text,
    discipline text,
    specification_section text,
    responsible_partner_id uuid,
    planned_submission_date date,
    submitted_at timestamptz,
    review_due_date date,
    reviewed_at timestamptz,
    review_status text not null default 'not_submitted',
    review_comments text,
    document_id uuid,
    revision_no integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, responsible_partner_id) references construction.business_partners(organization_id, id) on delete set null (responsible_partner_id),
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id),
    unique (project_id, submittal_number, revision_no)
);

create table construction.meetings (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    meeting_number text,
    meeting_type text not null,
    title text not null,
    scheduled_at timestamptz not null,
    ended_at timestamptz,
    location text,
    chairperson text,
    attendees jsonb not null default '[]'::jsonb,
    agenda text,
    minutes text,
    document_id uuid,
    status text not null default 'scheduled',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id),
    unique (project_id, meeting_number),
    unique (organization_id, id),
    check (ended_at is null or ended_at >= scheduled_at)
);

create table construction.action_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    meeting_id uuid,
    action_number text,
    description text not null,
    assigned_to_user_id uuid,
    assigned_to_name text,
    priority text not null default 'medium',
    due_date date,
    completed_at timestamptz,
    status text not null default 'open',
    closure_notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, meeting_id) references construction.meetings(organization_id, id) on delete set null (meeting_id)
);

-- ---------------------------------------------------------------------------
-- Quality, HSE, handover and final accounts
-- ---------------------------------------------------------------------------

create table construction.quality_inspections (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    inspection_number text not null,
    inspection_type text not null,
    discipline text,
    specification_reference text,
    location text,
    scheduled_date date,
    inspected_at timestamptz,
    inspector_name text,
    partner_id uuid,
    result text not null default 'pending',
    observations text,
    corrective_action_required boolean not null default false,
    closed_at timestamptz,
    document_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete set null (partner_id),
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id),
    unique (project_id, inspection_number)
);

create table construction.nonconformance_reports (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    ncr_number text not null,
    title text not null,
    description text not null,
    category text,
    severity text,
    location text,
    detected_at timestamptz not null,
    detected_by text,
    responsible_partner_id uuid,
    root_cause text,
    corrective_action text,
    preventive_action text,
    target_close_date date,
    closed_at timestamptz,
    verified_by uuid,
    verification_notes text,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, responsible_partner_id) references construction.business_partners(organization_id, id) on delete set null (responsible_partner_id),
    unique (project_id, ncr_number)
);

create table construction.safety_incidents (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    incident_number text not null,
    incident_type text not null,
    severity text not null,
    occurred_at timestamptz not null,
    reported_at timestamptz,
    location text,
    description text not null,
    persons_involved jsonb not null default '[]'::jsonb,
    injury_details text,
    lost_time_days numeric(10,2) not null default 0 check (lost_time_days >= 0),
    immediate_action text,
    root_cause text,
    corrective_action text,
    regulatory_report_required boolean not null default false,
    reported_to_authority_at timestamptz,
    closed_at timestamptz,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, incident_number)
);

create table construction.safety_inspections (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    inspection_number text not null,
    inspection_type text not null,
    scheduled_date date,
    inspected_at timestamptz,
    inspector_name text,
    location text,
    checklist jsonb not null default '[]'::jsonb,
    result text not null default 'pending',
    observations text,
    action_required boolean not null default false,
    action_due_date date,
    closed_at timestamptz,
    status text not null default 'open',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, inspection_number)
);

create table construction.permits (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    permit_number text not null,
    permit_type text not null,
    issuing_authority text,
    description text,
    application_date date,
    issue_date date,
    expiry_date date,
    responsible_user_id uuid,
    document_id uuid,
    conditions text,
    status text not null default 'pending',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id),
    unique (project_id, permit_number),
    check (expiry_date is null or issue_date is null or expiry_date >= issue_date)
);

create table construction.punch_list_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    item_number text not null,
    title text not null,
    description text not null,
    category text,
    location text,
    discipline text,
    priority text not null default 'medium',
    raised_at timestamptz not null,
    raised_by text,
    responsible_partner_id uuid,
    assigned_to text,
    due_date date,
    completed_at timestamptz,
    verified_at timestamptz,
    verified_by uuid,
    status text not null default 'open',
    evidence jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, responsible_partner_id) references construction.business_partners(organization_id, id) on delete set null (responsible_partner_id),
    unique (project_id, item_number)
);

create table construction.handover_packages (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    package_number text not null,
    title text not null,
    area_or_system text,
    planned_handover_date date,
    actual_handover_date date,
    recipient_name text,
    accepted_by text,
    accepted_at timestamptz,
    completion_percent numeric(7,4) not null default 0 check (completion_percent between 0 and 100),
    status text not null default 'open',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, package_number),
    unique (organization_id, id)
);

create table construction.handover_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    handover_package_id uuid not null,
    item_type text not null,
    description text not null,
    document_id uuid,
    required boolean not null default true,
    received_at timestamptz,
    reviewed_at timestamptz,
    accepted_at timestamptz,
    status text not null default 'pending',
    comments text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, handover_package_id) references construction.handover_packages(organization_id, id) on delete cascade,
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id)
);

create table construction.warranties (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    partner_id uuid,
    warranty_number text,
    asset_or_system text not null,
    description text,
    start_date date not null,
    expiry_date date not null,
    warranty_terms text,
    contact_details jsonb not null default '{}'::jsonb,
    document_id uuid,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, partner_id) references construction.business_partners(organization_id, id) on delete set null (partner_id),
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id),
    check (expiry_date >= start_date)
);

create table construction.final_accounts (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid not null,
    account_number text not null,
    original_contract_value numeric(20,2) not null default 0,
    approved_variations numeric(20,2) not null default 0,
    claims_settlement numeric(20,2) not null default 0,
    provisional_sums_adjustment numeric(20,2) not null default 0,
    deductions numeric(20,2) not null default 0,
    final_contract_value numeric(20,2) not null default 0,
    amount_previously_certified numeric(20,2) not null default 0,
    final_payment_due numeric(20,2) not null default 0,
    retention_release_due numeric(20,2) not null default 0,
    currency_code text not null,
    submitted_at timestamptz,
    agreed_at timestamptz,
    certified_at timestamptz,
    settled_at timestamptz,
    status text not null default 'draft',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete cascade,
    unique (contract_id, account_number)
);

create table construction.organization_registrations (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    registration_type text not null,
    registration_number text not null,
    issuing_authority text,
    country_code text,
    issue_date date,
    expiry_date date,
    document_id uuid,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, document_id) references construction.documents(organization_id, id) on delete set null (document_id),
    unique (organization_id, registration_type, registration_number),
    check (expiry_date is null or issue_date is null or expiry_date >= issue_date)
);

create table construction.estimates (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    estimate_number text not null,
    title text not null,
    estimate_type text not null,
    version_no integer not null default 1 check (version_no > 0),
    basis_date date,
    currency_code text not null,
    direct_cost numeric(20,2) not null default 0,
    indirect_cost numeric(20,2) not null default 0,
    contingency_amount numeric(20,2) not null default 0,
    overhead_amount numeric(20,2) not null default 0,
    profit_amount numeric(20,2) not null default 0,
    total_amount numeric(20,2) not null default 0,
    prepared_by uuid,
    approved_by uuid,
    approved_at timestamptz,
    assumptions text,
    exclusions text,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, estimate_number, version_no),
    unique (organization_id, id)
);

create table construction.estimate_items (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    estimate_id uuid not null,
    wbs_item_id uuid,
    cost_code_id uuid,
    line_number integer not null,
    description text not null,
    unit_code text,
    quantity numeric(20,4) not null default 0 check (quantity >= 0),
    labor_rate numeric(20,4) not null default 0,
    material_rate numeric(20,4) not null default 0,
    equipment_rate numeric(20,4) not null default 0,
    subcontract_rate numeric(20,4) not null default 0,
    other_rate numeric(20,4) not null default 0,
    total_rate numeric(20,4) not null default 0,
    total_amount numeric(20,2) not null default 0,
    productivity_rate numeric(20,4),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, estimate_id) references construction.estimates(organization_id, id) on delete cascade,
    foreign key (organization_id, cost_code_id) references construction.cost_codes(organization_id, id) on delete set null (cost_code_id),
    unique (estimate_id, line_number)
);

create table construction.payment_applications (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    contract_id uuid not null,
    application_number text not null,
    valuation_date date not null,
    period_start date,
    period_end date,
    gross_work_value numeric(20,2) not null default 0,
    materials_on_site_value numeric(20,2) not null default 0,
    approved_variations_value numeric(20,2) not null default 0,
    retention_amount numeric(20,2) not null default 0,
    advance_recovery_amount numeric(20,2) not null default 0,
    other_deductions numeric(20,2) not null default 0,
    amount_previously_certified numeric(20,2) not null default 0,
    amount_this_period numeric(20,2) not null default 0,
    cumulative_certified_amount numeric(20,2) not null default 0,
    currency_code text not null,
    submitted_at timestamptz,
    certified_at timestamptz,
    certified_by uuid,
    status text not null default 'draft',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    foreign key (organization_id, contract_id) references construction.contracts(organization_id, id) on delete cascade,
    unique (contract_id, application_number)
);

create table construction.daily_reports (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    report_date date not null,
    shift_code text,
    weather jsonb not null default '{}'::jsonb,
    manpower_summary jsonb not null default '{}'::jsonb,
    equipment_summary jsonb not null default '{}'::jsonb,
    work_completed text,
    planned_work text,
    delays_and_constraints text,
    visitors text,
    deliveries text,
    safety_observations text,
    quality_observations text,
    prepared_by uuid,
    submitted_at timestamptz,
    approved_by uuid,
    approved_at timestamptz,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique nulls not distinct (project_id, report_date, shift_code)
);

create table construction.equipment_maintenance (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    equipment_id uuid not null,
    project_id uuid,
    maintenance_type text not null,
    work_order_number text,
    scheduled_date date,
    started_at timestamptz,
    completed_at timestamptz,
    meter_reading numeric(20,2),
    provider_partner_id uuid,
    description text,
    findings text,
    action_taken text,
    parts_cost numeric(20,2) not null default 0,
    labor_cost numeric(20,2) not null default 0,
    currency_code text,
    next_service_date date,
    next_service_meter numeric(20,2),
    status text not null default 'planned',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, equipment_id) references construction.equipment(organization_id, id) on delete cascade,
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete set null (project_id),
    foreign key (organization_id, provider_partner_id) references construction.business_partners(organization_id, id) on delete set null (provider_partner_id)
);

create table construction.inspection_test_plans (
    id uuid primary key default extensions.gen_random_uuid(),
    organization_id uuid not null references construction.organizations(id) on delete cascade,
    project_id uuid not null,
    itp_number text not null,
    title text not null,
    discipline text,
    specification_reference text,
    activity_id uuid,
    inspection_points jsonb not null default '[]'::jsonb,
    acceptance_criteria text,
    responsible_party text,
    witness_parties text,
    approved_by uuid,
    approved_at timestamptz,
    revision_no integer not null default 0,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    foreign key (organization_id, project_id) references construction.projects(organization_id, id) on delete cascade,
    unique (project_id, itp_number, revision_no)
);

-- Deferred relationships for tables declared before their targets.
alter table construction.contacts add constraint contacts_org_id_id_key unique (organization_id, id);
alter table construction.project_phases add constraint project_phases_org_id_id_key unique (organization_id, id);
alter table construction.wbs_items add constraint wbs_items_org_id_id_key unique (organization_id, id);
alter table construction.activities add constraint activities_org_id_id_key unique (organization_id, id);
alter table construction.boq_items add constraint boq_items_org_id_id_key unique (organization_id, id);
alter table construction.contract_line_items add constraint contract_line_items_org_id_id_key unique (organization_id, id);
alter table construction.document_revisions add constraint document_revisions_org_id_id_key unique (organization_id, id);

alter table construction.business_units
    add constraint business_units_parent_tenant_fkey foreign key (organization_id, parent_id)
    references construction.business_units(organization_id, id) on delete set null (parent_id);
alter table construction.project_stakeholders
    add constraint project_stakeholders_contact_tenant_fkey foreign key (organization_id, contact_id)
    references construction.contacts(organization_id, id) on delete set null (contact_id);
alter table construction.project_milestones
    add constraint project_milestones_phase_tenant_fkey foreign key (organization_id, phase_id)
    references construction.project_phases(organization_id, id) on delete set null (phase_id);
alter table construction.wbs_items
    add constraint wbs_items_parent_tenant_fkey foreign key (organization_id, parent_id)
    references construction.wbs_items(organization_id, id) on delete cascade;
alter table construction.cost_codes
    add constraint cost_codes_parent_tenant_fkey foreign key (organization_id, parent_id)
    references construction.cost_codes(organization_id, id) on delete set null (parent_id);
alter table construction.boq_items
    add constraint boq_items_wbs_tenant_fkey foreign key (organization_id, wbs_item_id)
    references construction.wbs_items(organization_id, id) on delete set null (wbs_item_id);
alter table construction.activities
    add constraint activities_wbs_tenant_fkey foreign key (organization_id, wbs_item_id)
    references construction.wbs_items(organization_id, id) on delete set null (wbs_item_id);
alter table construction.activity_dependencies
    add constraint activity_dependencies_predecessor_tenant_fkey foreign key (organization_id, predecessor_id)
    references construction.activities(organization_id, id) on delete cascade,
    add constraint activity_dependencies_successor_tenant_fkey foreign key (organization_id, successor_id)
    references construction.activities(organization_id, id) on delete cascade;
alter table construction.progress_updates
    add constraint progress_updates_activity_tenant_fkey foreign key (organization_id, activity_id)
    references construction.activities(organization_id, id) on delete cascade,
    add constraint progress_updates_wbs_tenant_fkey foreign key (organization_id, wbs_item_id)
    references construction.wbs_items(organization_id, id) on delete cascade;
alter table construction.budget_lines
    add constraint budget_lines_wbs_tenant_fkey foreign key (organization_id, wbs_item_id)
    references construction.wbs_items(organization_id, id) on delete set null (wbs_item_id);
alter table construction.contract_line_items
    add constraint contract_line_items_boq_tenant_fkey foreign key (organization_id, boq_item_id)
    references construction.boq_items(organization_id, id) on delete set null (boq_item_id);
alter table construction.invoice_items
    add constraint invoice_items_contract_line_tenant_fkey foreign key (organization_id, contract_line_item_id)
    references construction.contract_line_items(organization_id, id) on delete set null (contract_line_item_id);
alter table construction.equipment_assignments
    add constraint equipment_assignments_activity_tenant_fkey foreign key (organization_id, activity_id)
    references construction.activities(organization_id, id) on delete set null (activity_id);
alter table construction.transmittal_items
    add constraint transmittal_items_revision_tenant_fkey foreign key (organization_id, document_revision_id)
    references construction.document_revisions(organization_id, id) on delete restrict;
alter table construction.inspection_test_plans
    add constraint inspection_test_plans_activity_tenant_fkey foreign key (organization_id, activity_id)
    references construction.activities(organization_id, id) on delete set null (activity_id);
alter table construction.estimate_items
    add constraint estimate_items_wbs_tenant_fkey foreign key (organization_id, wbs_item_id)
    references construction.wbs_items(organization_id, id) on delete set null (wbs_item_id);
alter table construction.employee_training
    add constraint employee_training_certificate_document_tenant_fkey
    foreign key (organization_id, certificate_document_id)
    references construction.documents(organization_id, id) on delete set null (certificate_document_id);
alter table construction.timesheets
    add constraint timesheets_activity_tenant_fkey foreign key (organization_id, activity_id)
    references construction.activities(organization_id, id) on delete set null (activity_id),
    add constraint timesheets_cost_code_tenant_fkey foreign key (organization_id, cost_code_id)
    references construction.cost_codes(organization_id, id) on delete set null (cost_code_id);
alter table construction.insurance_policies
    add constraint insurance_policies_document_tenant_fkey
    foreign key (organization_id, storage_document_id)
    references construction.documents(organization_id, id) on delete set null (storage_document_id);
alter table construction.documents
    add constraint documents_current_revision_tenant_fkey
    foreign key (organization_id, current_revision_id)
    references construction.document_revisions(organization_id, id) on delete set null (current_revision_id);

-- ---------------------------------------------------------------------------
-- Tenant authorization helpers. These live outside the exposed data schema.
-- ---------------------------------------------------------------------------

create or replace function construction_private.is_org_member(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select (select auth.uid()) is not null
       and exists (
           select 1
           from construction.organization_members membership
           where membership.organization_id = target_organization_id
             and membership.user_id = (select auth.uid())
             and membership.is_active
       );
$$;

create or replace function construction_private.can_manage_org(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select (select auth.uid()) is not null
       and exists (
           select 1
           from construction.organization_members membership
           where membership.organization_id = target_organization_id
             and membership.user_id = (select auth.uid())
             and membership.is_active
             and membership.role in ('owner','admin','manager')
       );
$$;

create or replace function construction_private.can_admin_org(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select (select auth.uid()) is not null
       and exists (
           select 1
           from construction.organization_members membership
           where membership.organization_id = target_organization_id
             and membership.user_id = (select auth.uid())
             and membership.is_active
             and membership.role in ('owner','admin')
       );
$$;

create or replace function construction_private.can_read_project(
    target_organization_id uuid,
    target_project_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select (select auth.uid()) is not null
       and exists (
           select 1
           from construction.organization_members membership
           where membership.organization_id = target_organization_id
             and membership.user_id = (select auth.uid())
             and membership.is_active
             and (
                 target_project_id is null
                 or membership.role in ('owner','admin','manager')
                 or exists (
                     select 1
                     from construction.projects project
                     where project.organization_id = target_organization_id
                       and project.id = target_project_id
                       and (
                           project.access_mode = 'organization'
                           or exists (
                               select 1
                               from construction.project_members project_membership
                               where project_membership.organization_id = target_organization_id
                                 and project_membership.project_id = target_project_id
                                 and project_membership.user_id = (select auth.uid())
                                 and project_membership.is_active
                           )
                       )
                 )
             )
       );
$$;

create or replace function construction_private.validate_current_document_revision()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if new.current_revision_id is not null and not exists (
        select 1
        from construction.document_revisions revision
        where revision.organization_id = new.organization_id
          and revision.id = new.current_revision_id
          and revision.project_id is not distinct from new.project_id
          and revision.document_id = new.id
          and revision.status = 'approved'
    ) then
        raise exception 'current_revision_id must identify an approved revision of the same document and project'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

create constraint trigger documents_validate_current_revision
after insert or update of organization_id, project_id, current_revision_id
on construction.documents
deferrable initially deferred
for each row execute function construction_private.validate_current_document_revision();

create or replace function construction_private.clear_revoked_current_revision()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if old.status = 'approved' and new.status <> 'approved' then
        update construction.documents document
        set current_revision_id = null
        where document.organization_id = new.organization_id
          and document.current_revision_id = new.id;
    end if;
    return new;
end;
$$;

create trigger document_revisions_clear_current
after update of status on construction.document_revisions
for each row execute function construction_private.clear_revoked_current_revision();

revoke all on all functions in schema construction_private from public, anon, authenticated, service_role;
grant usage on schema construction_private to authenticated;
grant execute on function construction_private.is_org_member(uuid) to authenticated;
grant execute on function construction_private.can_manage_org(uuid) to authenticated;
grant execute on function construction_private.can_admin_org(uuid) to authenticated;
grant execute on function construction_private.can_read_project(uuid, uuid) to authenticated;

-- Organizations and memberships need explicit policies because they do not
-- follow the standard tenant-table lifecycle.
alter table construction.organizations enable row level security;
alter table construction.organization_members enable row level security;

create policy organizations_read on construction.organizations
for select to authenticated
using ((select auth.uid()) is not null and (select construction_private.is_org_member(id)));

create policy organizations_update on construction.organizations
for update to authenticated
using ((select auth.uid()) is not null and (select construction_private.can_admin_org(id)))
with check ((select auth.uid()) is not null and (select construction_private.can_admin_org(id)));

create policy organization_members_read on construction.organization_members
for select to authenticated
using (
    (select auth.uid()) is not null
    and (user_id = (select auth.uid())
    or (select construction_private.is_org_member(organization_id))
    )
);

create policy organization_members_insert on construction.organization_members
for insert to authenticated
with check ((select auth.uid()) is not null and (select construction_private.can_admin_org(organization_id)));

create policy organization_members_update on construction.organization_members
for update to authenticated
using ((select auth.uid()) is not null and (select construction_private.can_admin_org(organization_id)))
with check ((select auth.uid()) is not null and (select construction_private.can_admin_org(organization_id)));

create policy organization_members_delete on construction.organization_members
for delete to authenticated
using ((select auth.uid()) is not null and (select construction_private.can_admin_org(organization_id)));

-- Apply a consistent organization boundary to every operational table.
do $policies$
declare
    tenant_table text;
    read_predicate text;
begin
    foreach tenant_table in array array[
        'business_units','clients','contacts','projects','project_members',
        'project_stakeholders','project_phases','project_milestones','employees',
        'employee_assignments','training_courses','employee_training',
        'attendance_records','timesheets','wbs_items','cost_codes','boq_items',
        'activities','activity_dependencies','schedule_baselines','progress_updates',
        'budgets','budget_lines','cost_transactions','cost_forecasts',
        'business_partners','partner_contacts','procurement_packages','bids',
        'contracts','contract_line_items','purchase_orders','purchase_order_items',
        'material_receipts','equipment','equipment_assignments','invoices',
        'invoice_items','payments','commitments','retention_records','change_orders',
        'contract_notices','claims','risks','insurance_policies','documents',
        'document_revisions','transmittals','transmittal_items','drawings','rfis',
        'submittals','meetings','action_items','quality_inspections',
        'nonconformance_reports','safety_incidents','safety_inspections','permits',
        'punch_list_items','handover_packages','handover_items','warranties',
        'final_accounts','organization_registrations','estimates','estimate_items',
        'payment_applications','daily_reports','equipment_maintenance',
        'inspection_test_plans'
    ]
    loop
        if tenant_table = 'projects' then
            read_predicate := '(select auth.uid()) is not null and (select construction_private.can_read_project(organization_id, id))';
        elsif exists (
            select 1
            from information_schema.columns
            where table_schema = 'construction'
              and table_name = tenant_table
              and column_name = 'project_id'
        ) then
            read_predicate := '(select auth.uid()) is not null and (select construction_private.can_read_project(organization_id, project_id))';
        else
            read_predicate := '(select auth.uid()) is not null and (select construction_private.is_org_member(organization_id))';
        end if;
        execute format('alter table construction.%I enable row level security', tenant_table);
        execute format(
            'create policy tenant_read on construction.%I for select to authenticated using (%s)',
            tenant_table,
            read_predicate
        );
        execute format(
            'create policy tenant_insert on construction.%I for insert to authenticated with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            tenant_table
        );
        execute format(
            'create policy tenant_update on construction.%I for update to authenticated using ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id))) with check ((select auth.uid()) is not null and (select construction_private.can_manage_org(organization_id)))',
            tenant_table
        );
        execute format(
            'create policy tenant_delete on construction.%I for delete to authenticated using ((select auth.uid()) is not null and (select construction_private.can_admin_org(organization_id)))',
            tenant_table
        );
    end loop;
end
$policies$;

-- ---------------------------------------------------------------------------
-- Indexes and timestamp maintenance
-- ---------------------------------------------------------------------------

-- Every foreign-key column set receives an index. PostgreSQL does not create
-- these automatically, and they are essential for joins and cascade deletes.
do $indexes$
declare
    fk record;
begin
    for fk in
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
            left(fk.conname || '_idx', 63),
            fk.relation_name,
            fk.column_list
        );
    end loop;
end
$indexes$;

create index projects_org_status_idx on construction.projects (organization_id, status);
create index projects_org_reporting_date_idx on construction.projects (organization_id, reporting_date desc);
create index attendance_org_employee_date_idx on construction.attendance_records (organization_id, employee_id, attendance_date desc);
create index activities_org_project_status_idx on construction.activities (organization_id, project_id, status);
create index cost_transactions_org_project_date_idx on construction.cost_transactions (organization_id, project_id, transaction_date desc);
create index invoices_org_project_status_due_idx on construction.invoices (organization_id, project_id, status, due_date);
create index documents_org_project_status_idx on construction.documents (organization_id, project_id, current_status);
create index risks_org_project_status_idx on construction.risks (organization_id, project_id, status);
create index punch_list_org_project_status_idx on construction.punch_list_items (organization_id, project_id, status);
create index projects_restricted_idx on construction.projects (organization_id, id)
where access_mode = 'restricted';

-- Not every table exposes updated_by, so the generic trigger only maintains
-- updated_at. Audit user columns are set by the API where present.
create or replace function construction_private.touch_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

do $timestamps$
declare
    target_table text;
begin
    for target_table in
        select table_name
        from information_schema.columns
        where table_schema = 'construction'
          and column_name = 'updated_at'
    loop
        execute format(
            'create trigger %I before update on construction.%I for each row execute function construction_private.touch_updated_at()',
            left(target_table || '_touch_updated_at', 63),
            target_table
        );
    end loop;
end
$timestamps$;

revoke execute on function construction_private.touch_updated_at() from public, anon, authenticated, service_role;

-- The schema can be added to the Supabase Data API's exposed schemas after
-- application review. RLS still protects every row when it is exposed.
grant usage on schema construction to authenticated;
revoke all on all tables in schema construction from anon, authenticated;
grant select, insert, update, delete on all tables in schema construction to authenticated;

comment on schema construction is
'Generic multi-organization construction operations data model. Tenant isolation is enforced with organization-scoped RLS.';

commit;
