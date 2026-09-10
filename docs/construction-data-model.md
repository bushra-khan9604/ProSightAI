# Generic construction data model

The `construction` schema is a multi-organization operational model that
coexists with ProSightAI's application-owned `prosight` schema. It contains no
organization-specific names or seed records.

## Tenant model

- `organizations` is the tenant boundary.
- Every operational record carries `organization_id`.
- Project records use `(organization_id, project_id)` foreign keys so a child
  record cannot be attached to a project owned by another organization.
- `organization_members` links Supabase Auth users to an organization with one
  of the generic roles `owner`, `admin`, `manager`, `member`, or `viewer`.
- RLS allows active members to read their organization's records, managers to
  write them, and owners/admins to delete them or manage memberships.
- Creating the first organization and owner membership is a server-side
  bootstrap operation. It is intentionally unavailable to ordinary clients.

## Subject areas

| Subject area | Main tables |
|---|---|
| Company and project registers | `organizations`, `organization_registrations`, `business_units`, `clients`, `contacts`, `projects`, `project_members`, `project_stakeholders`, `project_phases`, `project_milestones` |
| Employees and training | `employees`, `employee_assignments`, `training_courses`, `employee_training` |
| Attendance | `attendance_records`, `timesheets` |
| Planning, BOQ and schedule | `wbs_items`, `cost_codes`, `boq_items`, `estimates`, `estimate_items`, `activities`, `activity_dependencies`, `schedule_baselines`, `progress_updates`, `daily_reports` |
| Budget and cost | `budgets`, `budget_lines`, `cost_transactions`, `commitments`, `cost_forecasts` |
| Procurement and plant | `business_partners`, `partner_contacts`, `procurement_packages`, `bids`, `purchase_orders`, `purchase_order_items`, `material_items`, `material_receipts`, `inventory_locations`, `material_inventory_balances`, `material_inventory_movements`, `equipment`, `equipment_assignments`, `equipment_maintenance` |
| Commercial | `contracts`, `contract_line_items`, `invoices`, `invoice_items`, `payment_applications`, `payments`, `retention_records` |
| Changes, claims and risk | `change_orders`, `contract_notices`, `claims`, `risks`, `insurance_policies` |
| Technical and document control | `documents`, `document_revisions`, `transmittals`, `transmittal_items`, `drawings`, `rfis`, `submittals`, `meetings`, `action_items` |
| Quality and HSE | `inspection_test_plans`, `quality_inspections`, `nonconformance_reports`, `safety_incidents`, `safety_inspections`, `permits` |
| Handover and final accounts | `punch_list_items`, `handover_packages`, `handover_items`, `warranties`, `final_accounts` |

## Deployment notes

The migration is intentionally not applied to the hosted database. Review and
test it locally or on a Supabase preview branch first. If browser clients need
direct Data API access, add `construction` to the project's exposed schemas;
schema exposure and SQL grants are separate from RLS.

The `construction.documents` tables hold business metadata and Storage object
references. Existing approved PDFs and pgvector chunks remain in the `prosight`
schema until an explicit integration migration is designed.
