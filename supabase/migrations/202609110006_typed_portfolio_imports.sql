-- Store every canonical portfolio workbook field in a queryable typed column.

alter table public.manpower_assignments
  add column if not exists serial_number integer,
  add column if not exists mobilized_project text,
  add column if not exists current_project text,
  add column if not exists remarks text;

alter table public.project_invoices
  add column if not exists serial_number integer,
  add column if not exists proforma_date date,
  add column if not exists sap_po_number text,
  add column if not exists po_line_number text,
  add column if not exists contract_number text,
  add column if not exists coo_number text,
  add column if not exists icv_percent numeric(12,6),
  add column if not exists icv_five_percent_usd numeric(18,2),
  add column if not exists invoice_value_excl_tax_icv_usd numeric(18,2),
  add column if not exists invoice_value_excl_tax_icv_aed numeric(18,2),
  add column if not exists tax_invoice_reference text,
  add column if not exists ps_job_officer text,
  add column if not exists client_job_officer text,
  add column if not exists work_description text,
  add column if not exists avl_status text,
  add column if not exists work_year integer,
  add column if not exists asset text,
  add column if not exists icv_claim_year text,
  add column if not exists last_discussion_month date,
  add column if not exists mm_yy text,
  add column if not exists approval_current_date date,
  add column if not exists days_pending_approval integer,
  add column if not exists reason_for_rejection text,
  add column if not exists aging_reference text,
  add column if not exists client_reference text,
  add column if not exists payment_terms_days integer,
  add column if not exists days_pending_remittance integer,
  add column if not exists payment_current_date date,
  add column if not exists outstanding_status text,
  add column if not exists project text,
  add column if not exists tax_invoice_taken_outstanding text,
  add column if not exists aging_of_approval text,
  add column if not exists remarks text;

-- Backfill the columns that can be copied safely from earlier JSON-backed rows.
update public.manpower_assignments set
  serial_number = case
    when coalesce(data_json->>'serial_number', '') ~ '^-?[0-9]+$'
      then (data_json->>'serial_number')::integer else serial_number end,
  mobilized_project = coalesce(data_json->>'mobilized_project', mobilized_project),
  current_project = coalesce(data_json->>'current_project', current_project),
  remarks = coalesce(data_json->>'remarks', remarks)
where data_json is not null;

update public.project_invoices set
  serial_number = case when coalesce(data_json->>'serial_number', '') ~ '^-?[0-9]+$'
    then (data_json->>'serial_number')::integer else serial_number end,
  proforma_date = case when coalesce(data_json->>'proforma_date', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    then (data_json->>'proforma_date')::date else proforma_date end,
  sap_po_number = coalesce(data_json->>'sap_po_nono', sap_po_number),
  po_line_number = coalesce(data_json->>'po_lineno', po_line_number),
  contract_number = coalesce(data_json->>'contract', contract_number),
  coo_number = coalesce(data_json->>'coo', coo_number),
  icv_percent = case when coalesce(data_json->>'icv_%', '') ~ '^-?[0-9]+([.][0-9]+)?$'
    then (data_json->>'icv_%')::numeric else icv_percent end,
  icv_five_percent_usd = case
    when coalesce(data_json->>'icv_@_5%_(usd)', '') ~ '^-?[0-9]+([.][0-9]+)?$'
      then (data_json->>'icv_@_5%_(usd)')::numeric else icv_five_percent_usd end,
  invoice_value_excl_tax_icv_usd = case
    when coalesce(data_json->>'invoice_value_excl_tax_&_icv_(usd)', '') ~ '^-?[0-9]+([.][0-9]+)?$'
      then (data_json->>'invoice_value_excl_tax_&_icv_(usd)')::numeric
      else invoice_value_excl_tax_icv_usd end,
  invoice_value_excl_tax_icv_aed = case
    when coalesce(data_json->>'invoice_value_excl_tax_&_icv_(aed)', '') ~ '^-?[0-9]+([.][0-9]+)?$'
      then (data_json->>'invoice_value_excl_tax_&_icv_(aed)')::numeric
      else invoice_value_excl_tax_icv_aed end,
  tax_invoice_reference = coalesce(data_json->>'tax_invoice__inv_ref', tax_invoice_reference),
  ps_job_officer = coalesce(data_json->>'ps_job_officer', ps_job_officer),
  client_job_officer = coalesce(data_json->>'client_job_officer', client_job_officer),
  work_description = coalesce(data_json->>'work_description', work_description),
  avl_status = coalesce(data_json->>'avl__non-avl', avl_status),
  work_year = case when coalesce(data_json->>'year_of_work_done', '') ~ '^-?[0-9]+$'
    then (data_json->>'year_of_work_done')::integer else work_year end,
  asset = coalesce(data_json->>'asset', asset),
  icv_claim_year = coalesce(data_json->>'icv_claim_year', icv_claim_year),
  last_discussion_month = case
    when coalesce(data_json->>'last_disc_month', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then (data_json->>'last_disc_month')::date else last_discussion_month end,
  mm_yy = coalesce(data_json->>'mm_yy', mm_yy),
  approval_current_date = case
    when coalesce(data_json->>'current_date', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then (data_json->>'current_date')::date else approval_current_date end,
  days_pending_approval = case
    when coalesce(data_json->>'days_pending_approval_action', '') ~ '^-?[0-9]+$'
      then (data_json->>'days_pending_approval_action')::integer
      else days_pending_approval end,
  reason_for_rejection = coalesce(data_json->>'reason_for_rejection', reason_for_rejection),
  aging_reference = coalesce(data_json->>'aging_(ref)', aging_reference),
  client_reference = coalesce(data_json->>'client_ref', client_reference),
  payment_terms_days = case
    when coalesce(data_json->>'payment_terms_(days)', '') ~ '^-?[0-9]+$'
      then (data_json->>'payment_terms_(days)')::integer else payment_terms_days end,
  days_pending_remittance = case
    when coalesce(data_json->>'days_pending_for_remittance', '') ~ '^-?[0-9]+$'
      then (data_json->>'days_pending_for_remittance')::integer
      else days_pending_remittance end,
  payment_current_date = case
    when coalesce(data_json->>'current_date_(payment)', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then (data_json->>'current_date_(payment)')::date else payment_current_date end,
  outstanding_status = coalesce(data_json->>'outstanding_status', outstanding_status),
  project = coalesce(data_json->>'project', project),
  tax_invoice_taken_outstanding = coalesce(
    data_json->>'tax_invoice_taken_outstanding', tax_invoice_taken_outstanding
  ),
  aging_of_approval = coalesce(data_json->>'aging_of_approval', aging_of_approval),
  remarks = coalesce(data_json->>'remarks', remarks)
where data_json is not null;

create index if not exists manpower_department_idx
  on public.manpower_assignments(department);
create index if not exists manpower_category_idx
  on public.manpower_assignments(category);
create index if not exists manpower_location_idx
  on public.manpower_assignments(current_location);
create index if not exists manpower_status_idx
  on public.manpower_assignments(status);
create index if not exists manpower_allocation_idx
  on public.manpower_assignments(allocation);
create index if not exists invoices_status_idx
  on public.project_invoices(status);
create index if not exists invoices_approval_status_idx
  on public.project_invoices(approval_status);
create index if not exists invoices_payment_status_idx
  on public.project_invoices(payment_status);
create index if not exists invoices_risk_profile_idx
  on public.project_invoices(risk_profile);
create index if not exists invoices_submission_date_idx
  on public.project_invoices(submission_date);
