# Database redesign verification report

Verification date: 2026-09-10 (Asia/Dubai)

## Deployment and safety result

The schema was applied to the connected **ProSight AI** Supabase project
`rhtcwtmkgeuvvyuirpup` (PostgreSQL 17.6). No reset, migration-history repair,
seed, destructive DDL, secret read, Storage-object mutation, or real embedding
operation was performed.

The project already contained the 23-table legacy `prosight` schema but had no
Supabase migration-history rows. Before recording its three baselines, live
assertions verified all 23 expected tables and RLS policies, the locked-down
`prosight_backend` role, pgvector 0.8.2 in `extensions`, and the PDF Storage
columns/check/index/private bucket. Assertion-only baseline migrations recorded
that existing state without recreating tables or changing legacy data.

## Migration application

Commands:

```powershell
Get-Command supabase,psql,postgres,pg_isready,docker,podman -ErrorAction SilentlyContinue
Get-Content supabase/.temp/cli-latest
npx --yes supabase@latest --version
npx --yes supabase@latest migration new construction_integrity_hardening
npx --yes supabase@latest migration new ingestion_governance
npx --yes supabase@latest migration new semantic_projection_search
npx --yes supabase@latest migration new materials_inventory_traceability
npx --yes supabase@latest migration new request_scoped_authenticated_role
supabase migration new staged_mapping_generated_scope_fix
supabase migration new publication_conflict_columns_fix
supabase migration new frozen_evidence_generated_scope_fix
supabase migration new semantic_chunk_generated_scope_fix
```

Results:

- The cached Supabase CLI reported **2.117.0**.
- `psql`, `postgres`, `pg_isready`, Docker, and Podman: not found.
- Repository CLI version marker: `v2.117.0`; this marker is not an executable.
- Node and Python 3.13/3.14 are available, but no local PostgreSQL/Supabase
  runtime is available.

All six redesign migrations and four CLI-generated corrective migrations were
applied successfully. Supabase migration history contains 13 rows: three
verified legacy baselines, six redesign migrations, and four runtime fixes.

## Static verification performed

A local Node lexical scanner walked every migration and SQL test while ignoring
comments, quoted strings, identifiers, and dollar-quoted function bodies. It
checked balanced lexical states and parentheses.

Result: all 13 migration files and all four SQL tests reported balanced lexical
state: **17 files, zero lexical failures**.

Table count command:

```powershell
Select-String supabase/migrations/*.sql '^create table construction\.'
Select-String supabase/migrations/20260909224132_ingestion_governance.sql '^create table ingestion\.'
Select-String supabase/migrations/20260909224140_semantic_projection_search.sql '^create table semantic\.'
```

Results:

- construction: 78 tables across the documented 18 business areas
- ingestion: 14 tables
- semantic: 5 tables

Safety-pattern command (redesign migrations/tests only):

```powershell
Select-String <redesign SQL files> '(?i)\bauth\.role\s*\(|\bdrop\s+(schema|table).*prosight|\btruncate\s+.*prosight|\bdelete\s+from\s+prosight'
```

Result: no match after excluding the catalog test's regex/message text.

An AST walk inspected every parsed foreign-key constraint. It found 57
composite `ON DELETE SET NULL` constraints; all 57 have an explicit delete
column list and none includes `organization_id` (`UNSAFE=0`). The runtime
catalog test independently verifies `pg_constraint.confdelsetcols`, and the
behavioral test deletes a referenced business unit and asserts that only the
nullable key is cleared.

`pglast` 8.4 `parse_sql` successfully parsed every final migration and SQL test:
**17 files, 656 top-level statements, zero parse failures**. The migrations and
tests also passed PostgreSQL's server parser during live application/execution.

Application-contract regressions were run offline with local providers and fake
embeddings:

```powershell
$env:PYTHONPATH='src'
$env:PROSIGHT_AI_PROVIDER='local'
$env:PROSIGHT_DATABASE_BACKEND='sqlite'
$env:PROSIGHT_AUTH_PROVIDER='local'
python -m unittest tests.test_governed_excel tests.test_semantic_redesign tests.test_semantic_reindex tests.test_redesign_runtime tests.test_postgres_backend -v
```

Result: **60 tests passed in 3.230 seconds**. No real embedding provider,
database, or Storage service was used.

A later rerun under the bundled Python runtime could execute 30 tests but could
not import the remaining modules because that runtime lacks `fastapi` and
`psycopg`; the Windows Python installation also lacks the project dependencies.
This is an environment-only rerun limitation, not a replacement for the prior
complete 60-test pass.

Local Supabase lint was attempted with:

```powershell
npx --yes supabase@latest db lint --local
```

It exited **1** after attempting only `127.0.0.1:54322`, with
`ECONNREFUSED`. No local Supabase/PostgreSQL service is running, so database
lint did not execute and no hosted fallback was attempted.

## Live SQL verification

The following repository suites were executed directly against the connected
project. Each behavioral suite is transaction-wrapped and ends with `ROLLBACK`:

```powershell
supabase/tests/001_database_contract_verification.sql
supabase/tests/010_tenant_rls_and_integrity.sql
supabase/tests/020_ingestion_publication_and_semantic.sql
supabase/tests/030_controlled_publication_regressions.sql
```

Result: **4 of 4 suites passed**. A post-test query found zero fixture
organizations, confirming rollback cleanup.

Coverage:

- exact table counts and required legacy relation survival;
- non-null tenant columns and `unique (organization_id, id)`;
- project-aware identities, all foreign-key leading indexes using ordered
  ordinality/array-bound checks, and column-specific composite `SET NULL`;
- behavioral `SET NULL` preservation of non-null `organization_id`;
- exact material master/order/receipt/inventory/movement quantities, same-tenant
  and same-project stock links, nonnegative equipment values, and append-only
  movement history;
- RLS enabled, `TO authenticated`, explicit non-null `auth.uid()`, and no
  deprecated role helper;
- exact semantic table names and RPC signatures;
- private placement/search path and explicit caller checks for security-definer functions;
- hostile cross-organization and cross-project foreign keys;
- organization and restricted-project RLS;
- approval checksum binding and owner/admin publication authorization;
- idempotent publication and duplicate-lineage prevention;
- rollback of partial facts and lineage after a mid-publication failure;
- source-cell traceability;
- mandatory `uploaded` batch initialization plus rejection of direct lifecycle
  jumps;
- reusable multi-sheet/multi-entity mappings and independent profile/version
  identities (including version 1 under two profiles);
- authenticated direct-DML denial on import targets and semantic chunks;
- successful controlled employee publication through the private publisher;
- publication-whitelist conflict-key/unique-constraint compatibility;
- first-call and idempotent-retry semantic publication without duplicate vectors;
- rejection of wrong organization, project, embedding-job, and source bindings;
- legacy Storage provenance with both ingestion identifiers null and rejection
  of one-sided ingestion provenance;
- semantic typed project filters, org-wide row inclusion, stale-version
  exclusion, restricted-project retrieval, and publication rejection for both
  superseded and retired projection versions;
- stored generated FTS, 1,536-dimensional vector type, cosine HNSW operator
  class, positive-vector constraint, and cosine-distance parity;
- document approval revocation clearing current revision and disabling retrieval;
- direct construction/chunk DML denial, exact private-function EXECUTE allowlist,
  empty pinned `search_path`, internal `auth.uid()` checks, and
  `prosight_backend` membership that permits explicit `SET ROLE authenticated`
  without inherited redesigned-schema access.

## Runtime defects found and corrected

Live execution identified four issues that static parsing could not expose:

- stored `project_scope_id` is not populated while the staged-row `BEFORE`
  trigger runs;
- null rows from the publisher's conflict-key `LEFT JOIN` reached
  `format('%I', null)`;
- the frozen-evidence trigger compared the transient generated scope during its
  permitted status-only publication update;
- the semantic-chunk `BEFORE` trigger queried by the transient generated scope.

Each fix was folded into the original definition for fresh installations and
also recorded in a CLI-generated forward migration for the deployed project.
The failing suite was rerun after every correction and ultimately passed.

## Supabase advisors and remaining follow-up

Security advisor results contain three pre-existing/project-setting warnings:
anonymous and authenticated execution of `public.rls_auto_enable()` (the same
legacy function reported for both roles), plus disabled leaked-password
protection. Neither item is created by the redesign migrations.

Performance advisors report one unindexed FK and two duplicate-index warnings,
all in the legacy `prosight` schema, plus 440 unused-index informational items
immediately after deployment. There is no missing-FK-index advisor finding for
the redesigned `construction`, `ingestion`, or `semantic` schemas. Unused-index
statistics are not actionable until representative production traffic exists.

There is no blocker to the assigned schema application or database verification:
the deployed migrations, server-side DDL, triggers, RLS behavior, controlled
publishers, pgvector contract, tenant isolation, and rollback behavior all
completed their repository SQL checks. The legacy advisor warnings remain
explicit follow-up outside this redesign scope.
