# ProSightAI database and security design

## Scope and preservation boundary

The redesign is additive. It does not drop, truncate, rewrite, or backfill the
existing `prosight` schema. In particular, `prosight.documents`,
`prosight.document_chunks`, the 70 legacy 1,536-dimensional vectors, the
private `prosight-pdfs` bucket, and its 47 existing objects remain the active
legacy rollback path. Auth and Storage system relations are referenced but are
never recreated.

The new layer has three responsibilities:

- `construction` is the authoritative operational model.
- `ingestion` owns source evidence, deterministic transformation/validation,
  approval, publication, and lineage.
- `semantic` owns rebuildable, approved text projections and embeddings.

Privileged authorization helpers and the internal publication whitelist live
in the non-exposed `construction_private` schema.

## Construction model

The 78 construction tables cover 18 business areas:

| Area | Representative tables |
|---|---|
| Organization governance | `organizations`, `organization_members`, `organization_registrations`, `business_units` |
| Project register and access | `projects`, `project_members`, `project_stakeholders`, `project_phases`, `project_milestones` |
| Employees | `employees`, `employee_assignments` |
| Training | `training_courses`, `employee_training` |
| Attendance and time | `attendance_records`, `timesheets` |
| WBS, BOQ, and estimating | `wbs_items`, `boq_items`, `estimates`, `estimate_items`, `cost_codes` |
| Schedule and progress | `activities`, `activity_dependencies`, `schedule_baselines`, `progress_updates`, `daily_reports` |
| Budget and cost | `budgets`, `budget_lines`, `cost_transactions`, `cost_forecasts` |
| Partners | `business_partners`, `partner_contacts` |
| Procurement and materials | `procurement_packages`, `bids`, `purchase_orders`, `purchase_order_items`, `material_items`, `material_receipts`, `inventory_locations`, `material_inventory_balances`, `material_inventory_movements` |
| Plant and equipment | `equipment`, `equipment_assignments`, `equipment_maintenance` |
| Contracts | `contracts`, `contract_line_items` |
| Billing and cash | `invoices`, `invoice_items`, `payment_applications`, `payments`, `retention_records`, `commitments` |
| Changes and claims | `change_orders`, `contract_notices`, `claims` |
| Risk and insurance | `risks`, `insurance_policies` |
| Document and technical control | `documents`, `document_revisions`, `transmittals`, `drawings`, `rfis`, `submittals`, `meetings`, `action_items` |
| Quality and HSE | `inspection_test_plans`, `quality_inspections`, `nonconformance_reports`, `safety_incidents`, `safety_inspections`, `permits` |
| Handover and final account | `punch_list_items`, `handover_packages`, `handover_items`, `warranties`, `final_accounts` |

Every tenant-owned table carries a non-null `organization_id` and exposes
`unique (organization_id, id)`. Tables with `project_id` also expose a
project-aware identity. Additive composite foreign keys prevent a child from
referencing a parent in another organization or project even if RLS is
bypassed. Every foreign-key column set receives a leading-order index.

Money and rates are exact `numeric`; dates are `date`; instants are
`timestamptz`; externally referenced identifiers are UUIDs. Closed workflows
use checked text vocabularies. Auth identity columns reference `auth.users`.

Materials use one organization-wide `material_items` master. Purchase-order
lines bind to that master; receipts bind the same ordered material and a
project-scoped inventory location. Order, receipt, balance, and movement
quantities use `numeric(20,6)`. Location and movement foreign keys carry the
organization plus project scope, while material references carry the
organization. Inventory balances enforce nonnegative on-hand/reserved values;
movements are positive, direction/type checked, and append-only. Existing
`equipment` is the organization-wide equipment master, with project-aware
assignments and maintenance history; added checks keep meter, rate, and cost
values exact and nonnegative.

`projects.access_mode` is either `organization` or `restricted`. Restricted
projects are visible to active organization owners/admins/managers and active
project members. Project membership never works without active organization
membership.

`construction.documents` contains logical document identity only. Immutable
binary provenance is on `document_revisions`: bucket, object path, checksum,
MIME type, size, upload/verification timestamps, and review/approval evidence.
A deferred trigger permits `current_revision_id` to identify only an approved
revision of the same document and project. Revocation clears that pointer.

## Ingestion lifecycle

The `ingestion` schema contains 14 tables:

- reusable `mapping_profiles`, immutable `mapping_profile_versions`, and
  per-version `mapping_version_sheets`;
- `import_batches`, `source_files`, `source_sheets`, and `source_columns`;
- `transformation_runs`, `staged_rows`, and `staged_cells`;
- `validation_issues` and append-only `approval_records`;
- database-owned `publish_batches` and `record_lineage`.

All batch children freeze both `organization_id` and nullable `project_id`.
A stored `project_scope_id` maps null project scope to a sentinel UUID, allowing
ordinary composite foreign keys to enforce null-safe parent scope equality.
Source file deduplication is `(organization_id, source_kind, checksum_sha256)`;
logical import deduplication is `(organization_id, idempotency_key)`.

Profile identity (`mapping_profiles.id`) and immutable version identity
(`mapping_profile_versions.id`) are distinct. Version numbers are unique only
within one profile, so unrelated profiles may each have version 1. A version
may contain multiple sheet mappings and multiple target entity types; each
staged row binds the exact `mapping_version_sheets.id` that authorized its
target and business key.

The database transition trigger permits only:

`uploaded -> profiling -> mapping -> validating -> review_ready -> awaiting_approval -> approved -> publishing -> published`

Validation/publish failures and rejection/cancellation have explicit paths.
Approved, rejected, cancelled, publishing, published, and failed evidence is
immutable. An approval must be made by the authenticated active owner/admin,
must be distinct from the requester, and must exactly match the batch, mapping
version, successful transformation run, validation checksum, and normalized
preview checksum. Error-severity validation findings prevent approval.

The application-visible entry point is:

```sql
ingestion.publish_import_batch(batch_id uuid, approval_id uuid, idempotency_key text)
```

It is a security-invoker wrapper around a private security-definer routine. The
private routine checks `auth.uid()`, active owner/admin membership, the complete
approval binding, current validation state, and idempotency. A transaction-level
advisory lock serializes retries. Only an immutable private whitelist of target
tables and exact conflict keys can be used. Each upsert and its
`record_lineage` row occur in one PL/pgSQL subtransaction; any failure rolls
back all facts, lineage, and staged-row publication markers while preserving a
failed publication attempt for controlled retry.

The nine private-whitelist targets (`projects`, `employees`, `activities`,
`invoices`, `risks`, `rfis`, `nonconformance_reports`, `safety_incidents`, and
`daily_reports`) do not grant authenticated clients direct `INSERT` or `UPDATE`.
The private publisher validates that each configured conflict key has an exact,
valid, non-partial unique constraint. Target scope is explicit: employee and
project-register imports are organization-scoped, while the other targets
require a project-scoped batch. Publication returns only the common target
identifier and never assumes that an organization-scoped target has
`project_id`.

## Semantic layer

The semantic schema has five tables:

- immutable-content `semantic_projection_versions`;
- `semantic_documents`;
- `semantic_chunks`;
- `semantic_entity_links`;
- idempotent `embedding_jobs`.

Typed columns, rather than JSON, govern tenant/project filters, source identity,
document/revision provenance, source file/batch lineage, page/sheet/row ranges,
versions, model, dimensions, approval, and index status. A trigger rebuilds the
chunk metadata object from those typed columns so citation metadata cannot
disagree with authorization fields.

Projection versions are integer `version_no` values. Semantic documents bind
them through `projection_version_id` and repeat the integer as
`projection_version`; chunks and jobs repeat the same integer for indexed
filtering. Document language is `language_code`, and both documents and chunks
use stored generated `search_vector`. Approved documents and chunks are
`pending` before vector publication, embedding jobs are `queued` before claim,
and successfully indexed rows are `ready`.

The typed construction-document field is `construction_document_id`; generated
JSON citation metadata deliberately retains the external key `document_id`.
Ingestion provenance is an all-or-none `(source_file_id, import_batch_id)` pair.
Legacy Storage-backed PDFs may leave both null and instead bind an approved
construction document/revision plus bucket and object path.

Chunks use exactly `extensions.vector(1536)`, the model
`text-embedding-3-small`, and a positive finite norm. Full-text search uses a
stored generated `tsvector` plus GIN. Vector search uses HNSW with
`extensions.vector_cosine_ops`; the hybrid function uses the matching
`OPERATOR(extensions.<=>)` cosine operator. Lexical candidates, vector
candidates, and the final join each repeat organization, project, approval,
ready-status, model, dimension, requested projection-version, and requested
chunking-version filters. A project allowlist includes tenant-wide rows where
`project_id is null` as well as listed projects. Active projection-version state
is checked in every candidate and final branch. RLS provides an additional
project access boundary.

Vector writes are available only through:

```sql
semantic.publish_chunk_embeddings(
    organization_id uuid,
    embedding_job_id uuid,
    chunks jsonb,
    idempotency_key text
)
```

The security-invoker wrapper calls a private security-definer routine that
requires a non-null `auth.uid()` and active owner/admin/manager membership. One
transaction binds the job and idempotency key to one organization, semantic
document, project, projection version, chunking version, model, dimension, and
canonical payload checksum. It accepts only approved pending chunks, validates
stable UUID/checksum provenance and 1,536 finite non-zero values, inserts or
binds each pending chunk, marks chunks/documents ready, and completes the job.
An identical retry returns `already_succeeded` without adding vectors.
Authenticated clients have `SELECT`, but no direct mutation privilege, on
`semantic_chunks`.

Only approved construction document revisions can be approved or indexed as
semantic documents. Withdrawing, rejecting, or superseding a revision disables
its semantic documents and chunks without deleting provenance or legacy data.
Embedding workers claim queued work with `FOR UPDATE SKIP LOCKED`, bounded
attempts, and a lease.

## Grants and RLS

Policies target only `authenticated`, explicitly require non-null `auth.uid()`,
and call helpers that repeat the identity check. No policy uses `auth.role()` or
user-editable JWT metadata. Active organization membership is always required.
Managers can perform approved workflow operations; direct construction fact
mutation is revoked, and destructive/membership/approval actions remain
owner/admin operations.

Security-definer functions exist only in `construction_private`, use
`search_path = ''`, schema-qualify referenced objects, and check the caller's
`auth.uid()` where they expose privileged behavior. Default `PUBLIC`, `anon`,
`authenticated`, and `service_role` execution is revoked; only the exact helper
signatures needed by authenticated RLS or controlled publication are granted.
The exposed `construction`, `ingestion`, and `semantic` schemas grant only the
table operations used by their RLS workflows.

The legacy `prosight_backend` role remains `NOLOGIN`, `NOINHERIT`, and without
redesigned-schema privileges. Its sole new membership is in `authenticated`,
which allows the already-authorized server login to use `SET LOCAL ROLE
authenticated` only for a verified-user transaction. Without that explicit
role switch, the legacy role retains only its existing `prosight` access.

## Migration order

1. `20260907161807_prosight_postgres_pgvector.sql`
2. `20260908120000_workforce_imports.sql`
3. `20260909183928_add_pdf_storage.sql`
4. `20260909201030_construction_multi_organization_schema.sql`
5. `20260909224126_construction_integrity_hardening.sql`
6. `20260909224132_ingestion_governance.sql`
7. `20260909224140_semantic_projection_search.sql`
8. `20260909232443_materials_inventory_traceability.sql`
9. `20260909232450_request_scoped_authenticated_role.sql`
10. `20260910054913_staged_mapping_generated_scope_fix.sql`
11. `20260910055314_publication_conflict_columns_fix.sql`
12. `20260910055656_frozen_evidence_generated_scope_fix.sql`
13. `20260910055959_semantic_chunk_generated_scope_fix.sql`

The integrity, ingestion, semantic, materials/inventory, request-role, and four
runtime-correction filenames are retained as allocated by the Supabase CLI. The
pre-existing construction draft was not renamed. The full schema and forward
corrections were applied to the connected ProSight AI Supabase project on
2026-09-10.
