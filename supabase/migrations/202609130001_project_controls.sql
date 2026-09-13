-- Versioned project controls. No synthetic project data is installed.
create table public.controls_versions (
 id uuid primary key default gen_random_uuid(),
 project_code text not null references public.projects(code),
 parent_id uuid references public.controls_versions(id),
 status text not null default 'draft' check(status in ('draft','pending_approval','approved','active','rejected','superseded')),
 reporting_date date not null, construction_cutoff date, financial_cutoff date,
 author_id uuid not null references public.profiles(id), synthetic boolean not null default false,
 source_files jsonb not null default '[]', content jsonb not null,
 validation jsonb not null, checksum text not null, created_at timestamptz not null default now(),
 unique(project_code,id), unique(project_code,checksum)
);
create unique index controls_one_active on public.controls_versions(project_code) where status='active';
alter table public.controls_versions enable row level security;
create policy controls_versions_read on public.controls_versions for select to authenticated
 using(public.has_project_access(project_code) and not exists (
 select 1 from jsonb_array_elements(coalesce(content->'Demand','[]')) d where not public.has_project_access(d->>'project_code'))
 and not exists(select 1 from jsonb_array_elements(coalesce(content->'Historical Sources','[]')) h where not public.has_project_access(h->>'project_code')));
revoke all on public.controls_versions from anon, authenticated;
grant select on public.controls_versions to authenticated;

create table public.controls_scope_quantities (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "scope_id" text, "wbs_id" text, "work_item" text, "quantity" numeric, "unit" text, "productivity_per_labor_hour" numeric, "crew_size" numeric, "working_hours_per_day" numeric, "acceptance" text, "engineering_ref" text, "exclusion" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_scope_quantities enable row level security;
create policy controls_scope_quantities_read on public.controls_scope_quantities for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_scope_quantities from anon, authenticated;
grant select on public.controls_scope_quantities to authenticated;
create unique index controls_scope_quantities_identity on public.controls_scope_quantities(controls_version_id,"scope_id");

create table public.controls_resources (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "resource_id" text, "trade" text, "skill" text, "crew_size" numeric, "available_crews" numeric, "labor_hour_rate_usd" numeric, "equipment_day_rate_usd" numeric, "available_from" date, "available_to" date, "mobilization_days" numeric, "restriction" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_resources enable row level security;
create policy controls_resources_read on public.controls_resources for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_resources from anon, authenticated;
grant select on public.controls_resources to authenticated;
create unique index controls_resources_identity on public.controls_resources(controls_version_id,"resource_id");

create table public.controls_calendars (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "calendar_id" text, "working_days" text, "hours_per_day" numeric, "exceptions" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_calendars enable row level security;
create policy controls_calendars_read on public.controls_calendars for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_calendars from anon, authenticated;
grant select on public.controls_calendars to authenticated;
create unique index controls_calendars_identity on public.controls_calendars(controls_version_id,"calendar_id");

create table public.controls_commercial (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "contract_value_usd" numeric, "target_start" date, "target_finish" date, "retention_fraction" numeric, "receipt_lag_days" numeric, "supplier_payment_days" numeric, "advance_usd" numeric, "tax_fraction" numeric, "currency" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_commercial enable row level security;
create policy controls_commercial_read on public.controls_commercial for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_commercial from anon, authenticated;
grant select on public.controls_commercial to authenticated;

create table public.controls_assumptions (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "assumption_id" text, "topic" text, "value" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_assumptions enable row level security;
create policy controls_assumptions_read on public.controls_assumptions for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_assumptions from anon, authenticated;
grant select on public.controls_assumptions to authenticated;
create unique index controls_assumptions_identity on public.controls_assumptions(controls_version_id,"assumption_id");

create table public.controls_source_snapshot (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "code" text, "name" text, "status" text, "client" text, "location" text, "contract_value_usd" numeric, "planned_start" date, "planned_finish" date, "revised_finish" date, "reporting_date" date, "baseline_progress" numeric, "revised_progress" numeric, "actual_progress" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_source_snapshot enable row level security;
create policy controls_source_snapshot_read on public.controls_source_snapshot for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_source_snapshot from anon, authenticated;
grant select on public.controls_source_snapshot to authenticated;
create unique index controls_source_snapshot_identity on public.controls_source_snapshot(controls_version_id,"code","reporting_date");

create table public.controls_overview (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "status" text, "data_date" date, "construction_finish" date, "financial_asof" date, "contract_revenue_usd" numeric, "bac_usd" numeric, "ev_usd" numeric, "ac_usd" numeric, "pv_usd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_overview enable row level security;
create policy controls_overview_read on public.controls_overview for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_overview from anon, authenticated;
grant select on public.controls_overview to authenticated;

create table public.controls_schedule (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "activity_id" text, "wbs_id" text, "name" text, "calendar_id" text, "duration_wd" numeric, "baseline_start" date, "baseline_finish" date, "forecast_start" date, "forecast_finish" date, "actual_start" date, "actual_finish" date, "remaining_duration_wd" numeric, "quantity" numeric, "unit" text, "crew_size" numeric, "productivity_per_labor_hour" numeric, "budget_usd" numeric, "cost_code" text, "resource_id" text, "baseline_float_wd" numeric, "forecast_float_wd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_schedule enable row level security;
create policy controls_schedule_read on public.controls_schedule for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_schedule from anon, authenticated;
grant select on public.controls_schedule to authenticated;
create unique index controls_schedule_identity on public.controls_schedule(controls_version_id,"activity_id");

create table public.controls_relationships (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "relationship_id" text, "predecessor_id" text, "successor_id" text, "type" text, "baseline_lag_wd" numeric, "forecast_lag_wd" numeric, "event_id" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_relationships enable row level security;
create policy controls_relationships_read on public.controls_relationships for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_relationships from anon, authenticated;
grant select on public.controls_relationships to authenticated;
create unique index controls_relationships_identity on public.controls_relationships(controls_version_id,"relationship_id");

create table public.controls_milestones (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "activity_id" text, "name" text, "date" date, "kind" text, "duration_wd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_milestones enable row level security;
create policy controls_milestones_read on public.controls_milestones for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_milestones from anon, authenticated;
grant select on public.controls_milestones to authenticated;
create unique index controls_milestones_identity on public.controls_milestones(controls_version_id,"activity_id","kind");

create table public.controls_snapshots (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "version_id" text, "data_date" date, "activity_id" text, "actual_start" date, "actual_finish" date, "remaining_duration_wd" numeric, "forecast_start" date, "forecast_finish" date, "synthetic" boolean,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_snapshots enable row level security;
create policy controls_snapshots_read on public.controls_snapshots for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_snapshots from anon, authenticated;
grant select on public.controls_snapshots to authenticated;
create unique index controls_snapshots_identity on public.controls_snapshots(controls_version_id,"version_id","activity_id");

create table public.controls_cost_baseline (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "cost_code" text, "activity_id" text, "quantity" numeric, "unit" text, "unit_rate_usd" numeric, "labor_budget_usd" numeric, "equipment_budget_usd" numeric, "material_subcontract_usd" numeric, "budget_usd" numeric, "earning_method" text, "budget_weight" numeric, "labor_hour_rate_usd" numeric, "equipment_day_rate_usd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_cost_baseline enable row level security;
create policy controls_cost_baseline_read on public.controls_cost_baseline for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_cost_baseline from anon, authenticated;
grant select on public.controls_cost_baseline to authenticated;
create unique index controls_cost_baseline_identity on public.controls_cost_baseline(controls_version_id,"cost_code");

create table public.controls_budget_periods (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "period_end" date, "activity_id" text, "cost_code" text, "planned_value_usd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_budget_periods enable row level security;
create policy controls_budget_periods_read on public.controls_budget_periods for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_budget_periods from anon, authenticated;
grant select on public.controls_budget_periods to authenticated;
create unique index controls_budget_periods_identity on public.controls_budget_periods(controls_version_id,"period_end","activity_id");

create table public.controls_measurements (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "measurement_id" text, "period_end" date, "activity_id" text, "quantity_this_period" numeric, "cumulative_quantity" numeric, "unit" text, "completion_fraction" numeric, "earned_value_usd" numeric, "evidence_id" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_measurements enable row level security;
create policy controls_measurements_read on public.controls_measurements for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_measurements from anon, authenticated;
grant select on public.controls_measurements to authenticated;
create unique index controls_measurements_identity on public.controls_measurements(controls_version_id,"measurement_id");

create table public.controls_actual_costs (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "transaction_id" text, "date" date, "activity_id" text, "cost_code" text, "labor_hours" numeric, "cost_usd" numeric, "type" text, "evidence_id" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_actual_costs enable row level security;
create policy controls_actual_costs_read on public.controls_actual_costs for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_actual_costs from anon, authenticated;
grant select on public.controls_actual_costs to authenticated;
create unique index controls_actual_costs_identity on public.controls_actual_costs(controls_version_id,"transaction_id");

create table public.controls_performance (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "period_end" date, "record_kind" text, "pv_usd" numeric, "ev_usd" numeric, "ac_usd" numeric, "bac_usd" numeric, "cpi" numeric, "spi" numeric, "eac_usd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_performance enable row level security;
create policy controls_performance_read on public.controls_performance for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_performance from anon, authenticated;
grant select on public.controls_performance to authenticated;
create unique index controls_performance_identity on public.controls_performance(controls_version_id,"period_end");

create table public.controls_assignments (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "assignment_id" text, "activity_id" text, "resource_id" text, "start_date" date, "finish_date" date, "people" numeric, "daily_hours" numeric, "planned_labor_hours" numeric, "equipment_units" numeric, "kind" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_assignments enable row level security;
create policy controls_assignments_read on public.controls_assignments for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_assignments from anon, authenticated;
grant select on public.controls_assignments to authenticated;
create unique index controls_assignments_identity on public.controls_assignments(controls_version_id,"assignment_id");

create table public.controls_procurement (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "package_id" text, "activity_id" text, "description" text, "quantity" numeric, "unit" text, "lead_days" numeric, "required_on_site" date, "planned_order_date" date, "actual_order_date" date, "planned_delivery" date, "actual_delivery" date, "forecast_delivery" date, "approval_due" date, "supplier" text, "owner" text, "commitment_usd" numeric, "status" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_procurement enable row level security;
create policy controls_procurement_read on public.controls_procurement for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_procurement from anon, authenticated;
grant select on public.controls_procurement to authenticated;
create unique index controls_procurement_identity on public.controls_procurement(controls_version_id,"package_id");

create table public.controls_constraints (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "constraint_id" text, "activity_id" text, "event_id" text, "owner" text, "required_date" date, "status" text, "action" text, "due_date" date,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_constraints enable row level security;
create policy controls_constraints_read on public.controls_constraints for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_constraints from anon, authenticated;
grant select on public.controls_constraints to authenticated;
create unique index controls_constraints_identity on public.controls_constraints(controls_version_id,"constraint_id");

create table public.controls_risks (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "risk_id" text, "activity_id" text, "description" text, "probability" numeric, "impact_cost_usd" numeric, "impact_days" numeric, "owner" text, "mitigation" text, "status" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_risks enable row level security;
create policy controls_risks_read on public.controls_risks for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_risks from anon, authenticated;
grant select on public.controls_risks to authenticated;
create unique index controls_risks_identity on public.controls_risks(controls_version_id,"risk_id");

create table public.controls_changes (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "change_id" text, "date" date, "description" text, "approval" text, "budget_delta_usd" numeric, "baseline_preserved" boolean,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_changes enable row level security;
create policy controls_changes_read on public.controls_changes for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_changes from anon, authenticated;
grant select on public.controls_changes to authenticated;
create unique index controls_changes_identity on public.controls_changes(controls_version_id,"change_id");

create table public.controls_delay_events (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "event_id" text, "activity_id" text, "event_date" date, "description" text, "lag_wd" numeric, "project_impact_wd" numeric, "classification" text, "evidence_doc" text, "owner" text, "resolution_date" date,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_delay_events enable row level security;
create policy controls_delay_events_read on public.controls_delay_events for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_delay_events from anon, authenticated;
grant select on public.controls_delay_events to authenticated;
create unique index controls_delay_events_identity on public.controls_delay_events(controls_version_id,"event_id");

create table public.controls_billing (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "invoice_id" text, "period_end" date, "gross_usd" numeric, "retention_usd" numeric, "net_due_usd" numeric, "due_date" date, "paid_date" date, "kind" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_billing enable row level security;
create policy controls_billing_read on public.controls_billing for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_billing from anon, authenticated;
grant select on public.controls_billing to authenticated;
create unique index controls_billing_identity on public.controls_billing(controls_version_id,"invoice_id");

create table public.controls_cash_flow (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "period_end" date, "kind" text, "opening_cash_usd" numeric, "receipts_usd" numeric, "payments_usd" numeric, "closing_cash_usd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_cash_flow enable row level security;
create policy controls_cash_flow_read on public.controls_cash_flow for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_cash_flow from anon, authenticated;
grant select on public.controls_cash_flow to authenticated;
create unique index controls_cash_flow_identity on public.controls_cash_flow(controls_version_id,"period_end");

create table public.controls_recovery_options (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "option_id" text, "name" text, "activity_id" text, "activity_reduction_wd" numeric, "project_reduction_wd" numeric, "completion_date" date, "incremental_cost_usd" numeric, "status" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_recovery_options enable row level security;
create policy controls_recovery_options_read on public.controls_recovery_options for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_recovery_options from anon, authenticated;
grant select on public.controls_recovery_options to authenticated;
create unique index controls_recovery_options_identity on public.controls_recovery_options(controls_version_id,"option_id");

create table public.controls_measurement_plan (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "measurement_rule_id" text, "activity_id" text, "baseline_quantity" numeric, "unit" text, "earning_method" text, "budget_weight" numeric, "acceptance_record" text, "approver" text, "status" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_measurement_plan enable row level security;
create policy controls_measurement_plan_read on public.controls_measurement_plan for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_measurement_plan from anon, authenticated;
grant select on public.controls_measurement_plan to authenticated;
create unique index controls_measurement_plan_identity on public.controls_measurement_plan(controls_version_id,"measurement_rule_id");

create table public.controls_benchmarks (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "benchmark_id" text, "activity_id" text, "work_type" text, "location" text, "price_date" date, "unit" text, "quantity" numeric, "actual_labor_hours" numeric, "quantity_per_labor_hour" numeric, "actual_cost_usd" numeric, "unit_cost_usd" numeric, "crew_size" numeric, "source" text, "limitation" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_benchmarks enable row level security;
create policy controls_benchmarks_read on public.controls_benchmarks for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_benchmarks from anon, authenticated;
grant select on public.controls_benchmarks to authenticated;
create unique index controls_benchmarks_identity on public.controls_benchmarks(controls_version_id,"benchmark_id");

create table public.controls_lead_times (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "package_id" text, "activity_id" text, "planned_lead_days" numeric, "actual_lead_days" numeric, "source" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_lead_times enable row level security;
create policy controls_lead_times_read on public.controls_lead_times for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_lead_times from anon, authenticated;
grant select on public.controls_lead_times to authenticated;
create unique index controls_lead_times_identity on public.controls_lead_times(controls_version_id,"package_id");

create table public.controls_demand (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "scenario_id" text, "resource_id" text, "start_date" date, "finish_date" date, "requested_teams" numeric, "portfolio_available_teams" numeric, "activity_id" text, "kind" text, "warning" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_demand enable row level security;
create policy controls_demand_read on public.controls_demand for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_demand from anon, authenticated;
grant select on public.controls_demand to authenticated;
create unique index controls_demand_identity on public.controls_demand(controls_version_id,"scenario_id");

create table public.controls_capacity (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "resource_id" text, "start_date" date, "finish_date" date, "available_teams" numeric, "team_size" numeric, "team_day_cost_usd" numeric,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_capacity enable row level security;
create policy controls_capacity_read on public.controls_capacity for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_capacity from anon, authenticated;
grant select on public.controls_capacity to authenticated;
create unique index controls_capacity_identity on public.controls_capacity(controls_version_id,"resource_id","start_date");

create table public.controls_options (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "option" text, "first_project" text, "second_project" text, "second_start" date, "incremental_cost_usd" numeric, "tradeoff" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_options enable row level security;
create policy controls_options_read on public.controls_options for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_options from anon, authenticated;
grant select on public.controls_options to authenticated;
create unique index controls_options_identity on public.controls_options(controls_version_id,"option");

create table public.controls_wbs (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "wbs_id" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_wbs enable row level security;
create policy controls_wbs_read on public.controls_wbs for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_wbs from anon, authenticated;
grant select on public.controls_wbs to authenticated;
create unique index controls_wbs_identity on public.controls_wbs(controls_version_id,"wbs_id");

create table public.controls_requirements (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "requirement_id" text, "category" text, "text" text, "source_id" text, "source_quote" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_requirements enable row level security;
create policy controls_requirements_read on public.controls_requirements for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_requirements from anon, authenticated;
grant select on public.controls_requirements to authenticated;
create unique index controls_requirements_identity on public.controls_requirements(controls_version_id,"requirement_id");

create table public.controls_planning_documents (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "document" text, "text" text, "status" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_planning_documents enable row level security;
create policy controls_planning_documents_read on public.controls_planning_documents for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_planning_documents from anon, authenticated;
grant select on public.controls_planning_documents to authenticated;
create unique index controls_planning_documents_identity on public.controls_planning_documents(controls_version_id,"document");

create table public.controls_proposed_recovery (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "activity_id" text, "activity_reduction_wd" numeric, "incremental_cost_usd" numeric, "basis" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_proposed_recovery enable row level security;
create policy controls_proposed_recovery_read on public.controls_proposed_recovery for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_proposed_recovery from anon, authenticated;
grant select on public.controls_proposed_recovery to authenticated;
create unique index controls_proposed_recovery_identity on public.controls_proposed_recovery(controls_version_id,"activity_id");

create table public.controls_historical_sources (
 controls_version_id uuid not null,
 project_code text not null,
 record_number integer not null,
 "version_id" text,
 primary key(controls_version_id,record_number),
 foreign key(project_code,controls_version_id) references public.controls_versions(project_code,id) on delete cascade
);
alter table public.controls_historical_sources enable row level security;
create policy controls_historical_sources_read on public.controls_historical_sources for select to authenticated using(public.has_project_access(project_code) and exists(select 1 from public.controls_versions v where v.id=controls_version_id));
revoke all on public.controls_historical_sources from anon, authenticated;
grant select on public.controls_historical_sources to authenticated;
create unique index controls_historical_sources_identity on public.controls_historical_sources(controls_version_id,"version_id");

create or replace function public.stage_controls_version(p_code text,p_parent uuid,p_content jsonb,p_metadata jsonb,p_validation jsonb,p_checksum text)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_id uuid; item jsonb;
begin
 if not public.has_project_access(p_code) or public.current_app_role() not in ('admin','planning_engineer','project_manager') then
  raise exception 'Project editor access required';
 end if;
 if jsonb_typeof(p_content) <> 'object' or octet_length(p_content::text)>25000000 then raise exception 'Invalid controls payload'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p_code,0));
 if p_parent is not null and not exists(select 1 from controls_versions where id=p_parent and project_code=p_code) then raise exception 'Invalid parent'; end if;
 for item in select value from jsonb_array_elements(coalesce(p_content->'Demand','[]')) loop
  if not public.has_project_access(item->>'project_code') then raise exception 'Unauthorized shared demand'; end if;
 end loop;
 for item in select value from jsonb_array_elements(coalesce(p_content->'Historical Sources','[]')) loop
  if not public.has_project_access(item->>'project_code') then raise exception 'Unauthorized historical source'; end if;
  if not exists(select 1 from controls_versions where id=(item->>'version_id')::uuid and project_code=item->>'project_code') then raise exception 'Historical source version mismatch'; end if;
 end loop;
 if exists(select 1 from jsonb_array_elements(coalesce(p_content->'Relationships','[]')) r where r->>'type'<>'FS') then raise exception 'Only FS relationships are supported'; end if;
 if jsonb_array_length(coalesce(p_content->'Schedule','[]'))>1000 then raise exception 'Version supports at most 1000 activities'; end if;
 if jsonb_array_length(coalesce(p_content->'Schedule','[]'))>0 and exists(
  select 1 from jsonb_array_elements(coalesce(p_content->'Relationships','[]')) r
  where not exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')||coalesce(p_content->'Milestones','[]')) a where a->>'activity_id'=r->>'predecessor_id')
  or not exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')||coalesce(p_content->'Milestones','[]')) a where a->>'activity_id'=r->>'successor_id')
 ) then raise exception 'Broken schedule relationship'; end if;
 if exists(with recursive edges as (select r->>'predecessor_id' p,r->>'successor_id' s from jsonb_array_elements(coalesce(p_content->'Relationships','[]')) r),
 reach(p,s) as (select p,s from edges union select r.p,e.s from reach r join edges e on r.s=e.p) select 1 from reach where p=s) then raise exception 'Schedule contains a cycle'; end if;
 if exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')) a where (a->>'duration_wd')::numeric<0 or (a->>'duration_wd')::numeric<>trunc((a->>'duration_wd')::numeric)) then raise exception 'Invalid activity duration'; end if;
 if exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')) a where (a->>'actual_start')::date>(p_metadata->>'reporting_date')::date or (a->>'actual_finish')::date>(p_metadata->>'reporting_date')::date) then raise exception 'Actuals exceed reporting cutoff'; end if;
 if (select status from projects where code=p_code)='future' and (jsonb_array_length(coalesce(p_content->'Actual Costs','[]'))>0 or jsonb_array_length(coalesce(p_content->'Measurements','[]'))>0) then raise exception 'Future execution actuals are prohibited'; end if;
 if (select status from projects where code=p_code)='future' and exists(select 1 from jsonb_array_elements(coalesce(p_content->'Schedule','[]')) a where nullif(a->>'actual_start','') is not null or nullif(a->>'actual_finish','') is not null) then raise exception 'Future schedule cannot contain actual dates'; end if;
 if (select status from projects where code=p_code)='completed' and jsonb_array_length(coalesce(p_content->'Current Manpower','[]'))>0 then raise exception 'Historical manpower cannot become current manpower'; end if;
 select id into v_id from controls_versions where project_code=p_code and checksum=p_checksum;
 if v_id is not null then return (select to_jsonb(v) from controls_versions v where id=v_id); end if;
 insert into controls_versions(project_code,parent_id,reporting_date,construction_cutoff,financial_cutoff,author_id,synthetic,source_files,content,validation,checksum)
 values(p_code,p_parent,(p_metadata->>'reporting_date')::date,(p_metadata->>'construction_cutoff')::date,(p_metadata->>'financial_cutoff')::date,
 auth.uid(),coalesce((p_metadata->>'synthetic')::boolean,false),coalesce(p_metadata->'source_files','[]'),p_content,p_validation,p_checksum) returning id into v_id;
insert into public.controls_scope_quantities(controls_version_id,project_code,record_number,"scope_id","wbs_id","work_item","quantity","unit","productivity_per_labor_hour","crew_size","working_hours_per_day","acceptance","engineering_ref","exclusion")
 select v_id,p_code,row_number() over()::integer,r."scope_id",r."wbs_id",r."work_item",r."quantity",r."unit",r."productivity_per_labor_hour",r."crew_size",r."working_hours_per_day",r."acceptance",r."engineering_ref",r."exclusion"
 from jsonb_populate_recordset(null::public.controls_scope_quantities,coalesce(p_content->'Scope Quantities', '[]')) r;
insert into public.controls_resources(controls_version_id,project_code,record_number,"resource_id","trade","skill","crew_size","available_crews","labor_hour_rate_usd","equipment_day_rate_usd","available_from","available_to","mobilization_days","restriction")
 select v_id,p_code,row_number() over()::integer,r."resource_id",r."trade",r."skill",r."crew_size",r."available_crews",r."labor_hour_rate_usd",r."equipment_day_rate_usd",r."available_from",r."available_to",r."mobilization_days",r."restriction"
 from jsonb_populate_recordset(null::public.controls_resources,coalesce(p_content->'Resources', '[]')) r;
insert into public.controls_calendars(controls_version_id,project_code,record_number,"calendar_id","working_days","hours_per_day","exceptions")
 select v_id,p_code,row_number() over()::integer,r."calendar_id",r."working_days",r."hours_per_day",r."exceptions"
 from jsonb_populate_recordset(null::public.controls_calendars,coalesce(p_content->'Calendars', '[]')) r;
insert into public.controls_commercial(controls_version_id,project_code,record_number,"contract_value_usd","target_start","target_finish","retention_fraction","receipt_lag_days","supplier_payment_days","advance_usd","tax_fraction","currency")
 select v_id,p_code,row_number() over()::integer,r."contract_value_usd",r."target_start",r."target_finish",r."retention_fraction",r."receipt_lag_days",r."supplier_payment_days",r."advance_usd",r."tax_fraction",r."currency"
 from jsonb_populate_recordset(null::public.controls_commercial,coalesce(p_content->'Commercial', '[]')) r;
insert into public.controls_assumptions(controls_version_id,project_code,record_number,"assumption_id","topic","value")
 select v_id,p_code,row_number() over()::integer,r."assumption_id",r."topic",r."value"
 from jsonb_populate_recordset(null::public.controls_assumptions,coalesce(p_content->'Assumptions', '[]')) r;
insert into public.controls_source_snapshot(controls_version_id,project_code,record_number,"code","name","status","client","location","contract_value_usd","planned_start","planned_finish","revised_finish","reporting_date","baseline_progress","revised_progress","actual_progress")
 select v_id,p_code,row_number() over()::integer,r."code",r."name",r."status",r."client",r."location",r."contract_value_usd",r."planned_start",r."planned_finish",r."revised_finish",r."reporting_date",r."baseline_progress",r."revised_progress",r."actual_progress"
 from jsonb_populate_recordset(null::public.controls_source_snapshot,coalesce(p_content->'Source Snapshot', '[]')) r;
insert into public.controls_overview(controls_version_id,project_code,record_number,"status","data_date","construction_finish","financial_asof","contract_revenue_usd","bac_usd","ev_usd","ac_usd","pv_usd")
 select v_id,p_code,row_number() over()::integer,r."status",r."data_date",r."construction_finish",r."financial_asof",r."contract_revenue_usd",r."bac_usd",r."ev_usd",r."ac_usd",r."pv_usd"
 from jsonb_populate_recordset(null::public.controls_overview,coalesce(p_content->'Overview', '[]')) r;
insert into public.controls_schedule(controls_version_id,project_code,record_number,"activity_id","wbs_id","name","calendar_id","duration_wd","baseline_start","baseline_finish","forecast_start","forecast_finish","actual_start","actual_finish","remaining_duration_wd","quantity","unit","crew_size","productivity_per_labor_hour","budget_usd","cost_code","resource_id","baseline_float_wd","forecast_float_wd")
 select v_id,p_code,row_number() over()::integer,r."activity_id",r."wbs_id",r."name",r."calendar_id",r."duration_wd",r."baseline_start",r."baseline_finish",r."forecast_start",r."forecast_finish",r."actual_start",r."actual_finish",r."remaining_duration_wd",r."quantity",r."unit",r."crew_size",r."productivity_per_labor_hour",r."budget_usd",r."cost_code",r."resource_id",r."baseline_float_wd",r."forecast_float_wd"
 from jsonb_populate_recordset(null::public.controls_schedule,coalesce(p_content->'Schedule', '[]')) r;
insert into public.controls_relationships(controls_version_id,project_code,record_number,"relationship_id","predecessor_id","successor_id","type","baseline_lag_wd","forecast_lag_wd","event_id")
 select v_id,p_code,row_number() over()::integer,r."relationship_id",r."predecessor_id",r."successor_id",r."type",r."baseline_lag_wd",r."forecast_lag_wd",r."event_id"
 from jsonb_populate_recordset(null::public.controls_relationships,coalesce(p_content->'Relationships', '[]')) r;
insert into public.controls_milestones(controls_version_id,project_code,record_number,"activity_id","name","date","kind","duration_wd")
 select v_id,p_code,row_number() over()::integer,r."activity_id",r."name",r."date",r."kind",r."duration_wd"
 from jsonb_populate_recordset(null::public.controls_milestones,coalesce(p_content->'Milestones', '[]')) r;
insert into public.controls_snapshots(controls_version_id,project_code,record_number,"version_id","data_date","activity_id","actual_start","actual_finish","remaining_duration_wd","forecast_start","forecast_finish","synthetic")
 select v_id,p_code,row_number() over()::integer,r."version_id",r."data_date",r."activity_id",r."actual_start",r."actual_finish",r."remaining_duration_wd",r."forecast_start",r."forecast_finish",r."synthetic"
 from jsonb_populate_recordset(null::public.controls_snapshots,coalesce(p_content->'Snapshots', '[]')) r;
insert into public.controls_cost_baseline(controls_version_id,project_code,record_number,"cost_code","activity_id","quantity","unit","unit_rate_usd","labor_budget_usd","equipment_budget_usd","material_subcontract_usd","budget_usd","earning_method","budget_weight","labor_hour_rate_usd","equipment_day_rate_usd")
 select v_id,p_code,row_number() over()::integer,r."cost_code",r."activity_id",r."quantity",r."unit",r."unit_rate_usd",r."labor_budget_usd",r."equipment_budget_usd",r."material_subcontract_usd",r."budget_usd",r."earning_method",r."budget_weight",r."labor_hour_rate_usd",r."equipment_day_rate_usd"
 from jsonb_populate_recordset(null::public.controls_cost_baseline,coalesce(p_content->'Cost Baseline', '[]')) r;
insert into public.controls_budget_periods(controls_version_id,project_code,record_number,"period_end","activity_id","cost_code","planned_value_usd")
 select v_id,p_code,row_number() over()::integer,r."period_end",r."activity_id",r."cost_code",r."planned_value_usd"
 from jsonb_populate_recordset(null::public.controls_budget_periods,coalesce(p_content->'Budget Periods', '[]')) r;
insert into public.controls_measurements(controls_version_id,project_code,record_number,"measurement_id","period_end","activity_id","quantity_this_period","cumulative_quantity","unit","completion_fraction","earned_value_usd","evidence_id")
 select v_id,p_code,row_number() over()::integer,r."measurement_id",r."period_end",r."activity_id",r."quantity_this_period",r."cumulative_quantity",r."unit",r."completion_fraction",r."earned_value_usd",r."evidence_id"
 from jsonb_populate_recordset(null::public.controls_measurements,coalesce(p_content->'Measurements', '[]')) r;
insert into public.controls_actual_costs(controls_version_id,project_code,record_number,"transaction_id","date","activity_id","cost_code","labor_hours","cost_usd","type","evidence_id")
 select v_id,p_code,row_number() over()::integer,r."transaction_id",r."date",r."activity_id",r."cost_code",r."labor_hours",r."cost_usd",r."type",r."evidence_id"
 from jsonb_populate_recordset(null::public.controls_actual_costs,coalesce(p_content->'Actual Costs', '[]')) r;
insert into public.controls_performance(controls_version_id,project_code,record_number,"period_end","record_kind","pv_usd","ev_usd","ac_usd","bac_usd","cpi","spi","eac_usd")
 select v_id,p_code,row_number() over()::integer,r."period_end",r."record_kind",r."pv_usd",r."ev_usd",r."ac_usd",r."bac_usd",r."cpi",r."spi",r."eac_usd"
 from jsonb_populate_recordset(null::public.controls_performance,coalesce(p_content->'Performance', '[]')) r;
insert into public.controls_assignments(controls_version_id,project_code,record_number,"assignment_id","activity_id","resource_id","start_date","finish_date","people","daily_hours","planned_labor_hours","equipment_units","kind")
 select v_id,p_code,row_number() over()::integer,r."assignment_id",r."activity_id",r."resource_id",r."start_date",r."finish_date",r."people",r."daily_hours",r."planned_labor_hours",r."equipment_units",r."kind"
 from jsonb_populate_recordset(null::public.controls_assignments,coalesce(p_content->'Assignments', '[]')) r;
insert into public.controls_procurement(controls_version_id,project_code,record_number,"package_id","activity_id","description","quantity","unit","lead_days","required_on_site","planned_order_date","actual_order_date","planned_delivery","actual_delivery","forecast_delivery","approval_due","supplier","owner","commitment_usd","status")
 select v_id,p_code,row_number() over()::integer,r."package_id",r."activity_id",r."description",r."quantity",r."unit",r."lead_days",r."required_on_site",r."planned_order_date",r."actual_order_date",r."planned_delivery",r."actual_delivery",r."forecast_delivery",r."approval_due",r."supplier",r."owner",r."commitment_usd",r."status"
 from jsonb_populate_recordset(null::public.controls_procurement,coalesce(p_content->'Procurement', '[]')) r;
insert into public.controls_constraints(controls_version_id,project_code,record_number,"constraint_id","activity_id","event_id","owner","required_date","status","action","due_date")
 select v_id,p_code,row_number() over()::integer,r."constraint_id",r."activity_id",r."event_id",r."owner",r."required_date",r."status",r."action",r."due_date"
 from jsonb_populate_recordset(null::public.controls_constraints,coalesce(p_content->'Constraints', '[]')) r;
insert into public.controls_risks(controls_version_id,project_code,record_number,"risk_id","activity_id","description","probability","impact_cost_usd","impact_days","owner","mitigation","status")
 select v_id,p_code,row_number() over()::integer,r."risk_id",r."activity_id",r."description",r."probability",r."impact_cost_usd",r."impact_days",r."owner",r."mitigation",r."status"
 from jsonb_populate_recordset(null::public.controls_risks,coalesce(p_content->'Risks', '[]')) r;
insert into public.controls_changes(controls_version_id,project_code,record_number,"change_id","date","description","approval","budget_delta_usd","baseline_preserved")
 select v_id,p_code,row_number() over()::integer,r."change_id",r."date",r."description",r."approval",r."budget_delta_usd",r."baseline_preserved"
 from jsonb_populate_recordset(null::public.controls_changes,coalesce(p_content->'Changes', '[]')) r;
insert into public.controls_delay_events(controls_version_id,project_code,record_number,"event_id","activity_id","event_date","description","lag_wd","project_impact_wd","classification","evidence_doc","owner","resolution_date")
 select v_id,p_code,row_number() over()::integer,r."event_id",r."activity_id",r."event_date",r."description",r."lag_wd",r."project_impact_wd",r."classification",r."evidence_doc",r."owner",r."resolution_date"
 from jsonb_populate_recordset(null::public.controls_delay_events,coalesce(p_content->'Delay Events', '[]')) r;
insert into public.controls_billing(controls_version_id,project_code,record_number,"invoice_id","period_end","gross_usd","retention_usd","net_due_usd","due_date","paid_date","kind")
 select v_id,p_code,row_number() over()::integer,r."invoice_id",r."period_end",r."gross_usd",r."retention_usd",r."net_due_usd",r."due_date",r."paid_date",r."kind"
 from jsonb_populate_recordset(null::public.controls_billing,coalesce(p_content->'Billing', '[]')) r;
insert into public.controls_cash_flow(controls_version_id,project_code,record_number,"period_end","kind","opening_cash_usd","receipts_usd","payments_usd","closing_cash_usd")
 select v_id,p_code,row_number() over()::integer,r."period_end",r."kind",r."opening_cash_usd",r."receipts_usd",r."payments_usd",r."closing_cash_usd"
 from jsonb_populate_recordset(null::public.controls_cash_flow,coalesce(p_content->'Cash Flow', '[]')) r;
insert into public.controls_recovery_options(controls_version_id,project_code,record_number,"option_id","name","activity_id","activity_reduction_wd","project_reduction_wd","completion_date","incremental_cost_usd","status")
 select v_id,p_code,row_number() over()::integer,r."option_id",r."name",r."activity_id",r."activity_reduction_wd",r."project_reduction_wd",r."completion_date",r."incremental_cost_usd",r."status"
 from jsonb_populate_recordset(null::public.controls_recovery_options,coalesce(p_content->'Recovery Options', '[]')) r;
insert into public.controls_measurement_plan(controls_version_id,project_code,record_number,"measurement_rule_id","activity_id","baseline_quantity","unit","earning_method","budget_weight","acceptance_record","approver","status")
 select v_id,p_code,row_number() over()::integer,r."measurement_rule_id",r."activity_id",r."baseline_quantity",r."unit",r."earning_method",r."budget_weight",r."acceptance_record",r."approver",r."status"
 from jsonb_populate_recordset(null::public.controls_measurement_plan,coalesce(p_content->'Measurement Plan', '[]')) r;
insert into public.controls_benchmarks(controls_version_id,project_code,record_number,"benchmark_id","activity_id","work_type","location","price_date","unit","quantity","actual_labor_hours","quantity_per_labor_hour","actual_cost_usd","unit_cost_usd","crew_size","source","limitation")
 select v_id,p_code,row_number() over()::integer,r."benchmark_id",r."activity_id",r."work_type",r."location",r."price_date",r."unit",r."quantity",r."actual_labor_hours",r."quantity_per_labor_hour",r."actual_cost_usd",r."unit_cost_usd",r."crew_size",r."source",r."limitation"
 from jsonb_populate_recordset(null::public.controls_benchmarks,coalesce(p_content->'Benchmarks', '[]')) r;
insert into public.controls_lead_times(controls_version_id,project_code,record_number,"package_id","activity_id","planned_lead_days","actual_lead_days","source")
 select v_id,p_code,row_number() over()::integer,r."package_id",r."activity_id",r."planned_lead_days",r."actual_lead_days",r."source"
 from jsonb_populate_recordset(null::public.controls_lead_times,coalesce(p_content->'Lead Times', '[]')) r;
insert into public.controls_demand(controls_version_id,project_code,record_number,"scenario_id","resource_id","start_date","finish_date","requested_teams","portfolio_available_teams","activity_id","kind","warning")
 select v_id,p_code,row_number() over()::integer,r."scenario_id",r."resource_id",r."start_date",r."finish_date",r."requested_teams",r."portfolio_available_teams",r."activity_id",r."kind",r."warning"
 from jsonb_populate_recordset(null::public.controls_demand,coalesce(p_content->'Demand', '[]')) r;
insert into public.controls_capacity(controls_version_id,project_code,record_number,"resource_id","start_date","finish_date","available_teams","team_size","team_day_cost_usd")
 select v_id,p_code,row_number() over()::integer,r."resource_id",r."start_date",r."finish_date",r."available_teams",r."team_size",r."team_day_cost_usd"
 from jsonb_populate_recordset(null::public.controls_capacity,coalesce(p_content->'Capacity', '[]')) r;
insert into public.controls_options(controls_version_id,project_code,record_number,"option","first_project","second_project","second_start","incremental_cost_usd","tradeoff")
 select v_id,p_code,row_number() over()::integer,r."option",r."first_project",r."second_project",r."second_start",r."incremental_cost_usd",r."tradeoff"
 from jsonb_populate_recordset(null::public.controls_options,coalesce(p_content->'Options', '[]')) r;
insert into public.controls_wbs(controls_version_id,project_code,record_number,"wbs_id")
 select v_id,p_code,row_number() over()::integer,r."wbs_id"
 from jsonb_populate_recordset(null::public.controls_wbs,coalesce(p_content->'WBS', '[]')) r;
insert into public.controls_requirements(controls_version_id,project_code,record_number,"requirement_id","category","text","source_id","source_quote")
 select v_id,p_code,row_number() over()::integer,r."requirement_id",r."category",r."text",r."source_id",r."source_quote"
 from jsonb_populate_recordset(null::public.controls_requirements,coalesce(p_content->'Requirements', '[]')) r;
insert into public.controls_planning_documents(controls_version_id,project_code,record_number,"document","text","status")
 select v_id,p_code,row_number() over()::integer,r."document",r."text",r."status"
 from jsonb_populate_recordset(null::public.controls_planning_documents,coalesce(p_content->'Planning Documents', '[]')) r;
insert into public.controls_proposed_recovery(controls_version_id,project_code,record_number,"activity_id","activity_reduction_wd","incremental_cost_usd","basis")
 select v_id,p_code,row_number() over()::integer,r."activity_id",r."activity_reduction_wd",r."incremental_cost_usd",r."basis"
 from jsonb_populate_recordset(null::public.controls_proposed_recovery,coalesce(p_content->'Proposed Recovery', '[]')) r;
insert into public.controls_historical_sources(controls_version_id,project_code,record_number,"version_id")
 select v_id,p_code,row_number() over()::integer,r."version_id"
 from jsonb_populate_recordset(null::public.controls_historical_sources,coalesce(p_content->'Historical Sources', '[]')) r;
 return (select to_jsonb(v) from controls_versions v where id=v_id);
end $$;
revoke all on function public.stage_controls_version(text,uuid,jsonb,jsonb,jsonb,text) from public;
grant execute on function public.stage_controls_version(text,uuid,jsonb,jsonb,jsonb,text) to authenticated;

create or replace function public.submit_controls_version(p_id uuid) returns jsonb
language plpgsql security definer set search_path=public as $$
declare v controls_versions; c change_requests;
begin
 select * into v from controls_versions where id=p_id for update;
 if v.id is null or not public.has_project_access(v.project_code) or public.current_app_role() not in ('admin','planning_engineer','project_manager') then raise exception 'Project editor access required'; end if;
 if v.status='pending_approval' then return (select to_jsonb(x) from change_requests x where payload->>'version_id'=p_id::text and status='pending' limit 1); end if;
 if v.status<>'draft' then raise exception 'Only drafts can be submitted'; end if;
 insert into change_requests(action,project_code,payload,preview,requested_by,requested_role)
 values('controls_activation',v.project_code,jsonb_build_object('version_id',v.id),jsonb_build_object('before',v.parent_id,'after',v.validation,'reporting_date',v.reporting_date),auth.uid(),public.current_app_role()) returning * into c;
 update controls_versions set status='pending_approval' where id=p_id;
 insert into notifications(recipient_user_id,event_type,project_code,change_request_id,title,message)
 select id,'approval_required',v.project_code,c.id,'Project controls approval required','Review validated counts and activate the proposed controls version.' from profiles where role='admin';
 return to_jsonb(c);
end $$;
revoke all on function public.submit_controls_version(uuid) from public;
grant execute on function public.submit_controls_version(uuid) to authenticated;

create or replace function public.decide_controls_version(p_change uuid,p_approve boolean) returns jsonb
language plpgsql security definer set search_path=public as $$
declare c change_requests; v controls_versions; active_id uuid; base_id uuid;
begin
 if not public.is_admin() then raise exception 'Admin approval required'; end if;
 select * into c from change_requests where id=p_change for update;
 if c.id is null or c.action<>'controls_activation' then raise exception 'Controls approval not found'; end if;
 if c.status<>'pending' then return to_jsonb(c); end if;
 perform pg_advisory_xact_lock(hashtextextended(c.project_code,0));
 select * into v from controls_versions where id=(c.payload->>'version_id')::uuid and project_code=c.project_code for update;
 if v.id is null or v.status<>'pending_approval' then raise exception 'Version is not pending approval'; end if;
 if p_approve then
  select id into active_id from controls_versions where project_code=v.project_code and status='active';
  base_id := v.parent_id;
  while base_id is not null and base_id is distinct from active_id loop
   if exists(select 1 from controls_versions where id=base_id and status in ('active','superseded')) then exit; end if;
   select parent_id into base_id from controls_versions where id=base_id;
  end loop;
  if base_id is distinct from active_id then raise exception 'Active version changed; rebase and review the draft'; end if;
  update controls_versions set status='superseded' where id=active_id;
  update controls_versions set status='active' where id=v.id;
 else
  update controls_versions set status='rejected' where id=v.id;
 end if;
 update change_requests set status=case when p_approve then 'approved' else 'rejected' end,
 decided_by=auth.uid(),decided_role='admin',decided_at=now() where id=p_change returning * into c;
 insert into audit_events(actor_user_id,actor_role,action,target_type,target_id,before_json,after_json)
 values(auth.uid(),'admin','controls_activation','controls_version',v.id::text,to_jsonb(active_id),to_jsonb(c));
 return to_jsonb(c);
end $$;
revoke all on function public.decide_controls_version(uuid,boolean) from public;
grant execute on function public.decide_controls_version(uuid,boolean) to authenticated;

create table public.controls_jobs (
 id uuid primary key default gen_random_uuid(), project_code text not null references projects(code),
 requested_by uuid not null references profiles(id), kind text not null check(kind in ('import','analyst','planner','export')),
 status text not null default 'queued' check(status in ('queued','running','completed','failed','cancelled')),
 version_id uuid references controls_versions(id), input jsonb not null default '{}', result jsonb, error text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.controls_jobs enable row level security;
create policy controls_jobs_read on public.controls_jobs for select to authenticated using(has_project_access(project_code) and (requested_by=auth.uid() or is_admin()));
create policy controls_jobs_insert on public.controls_jobs for insert to authenticated with check(has_project_access(project_code) and requested_by=auth.uid());
create policy controls_jobs_update on public.controls_jobs for update to authenticated using(has_project_access(project_code) and requested_by=auth.uid()) with check(has_project_access(project_code) and requested_by=auth.uid());
grant select,insert,update on public.controls_jobs to authenticated;
create table public.controls_artifacts (
 id uuid primary key default gen_random_uuid(), project_code text not null references projects(code),
 version_id uuid not null references controls_versions(id), filename text not null, format text not null check(format in ('xlsx','pdf')),
 created_at timestamptz not null default now()
);
alter table public.controls_artifacts enable row level security;
create policy controls_artifacts_read on public.controls_artifacts for select to authenticated using(has_project_access(project_code));
create policy controls_artifacts_insert on public.controls_artifacts for insert to authenticated with check(has_project_access(project_code) and exists(select 1 from controls_versions v where v.id=version_id and v.project_code=controls_artifacts.project_code));
grant select,insert on public.controls_artifacts to authenticated;
