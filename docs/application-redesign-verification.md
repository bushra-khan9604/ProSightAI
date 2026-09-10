# Application redesign verification

Date: 2026-09-10

## Completion and safety boundary

The Application/Ingestion/RAG cycle is implemented against the frozen database
contract. No hosted database command, Storage upload/delete, secret inspection,
or real embedding request was performed. Tests use temporary workbooks, mock
database transactions, fake PDF pages, and deterministic 1,536-dimensional
vectors. Workbook/PDF/manifest content is always treated as untrusted data and
formula text is never evaluated.

No Supabase migration, SQL test, or `docs/database-redesign-contracts.md` file
was edited in this application workstream. Existing legacy tables, the private
`prosight-pdfs` bucket and its 47 registered objects, and the 70-vector legacy
index were not queried or changed by verification.

## Implemented contracts

- Legacy PostgreSQL transactions retain their exact `prosight_backend` role,
  search path, and behavior.
- Redesigned transactions accept only a server-verified `uuid.UUID`. Before an
  application query they enter `authenticated`, bind transaction-local
  `request.jwt.claim.sub` and `request.jwt.claims` with bound
  `pg_catalog.set_config` parameters, and pin the redesigned search path.
  Invalid identities fail before a pool connection is obtained.
- Redesigned startup checks only `pg_catalog` for the construction membership
  table, ingestion and semantic objects/RPCs, and role membership. It never
  initializes or checks `prosight.schema_version`. Redesigned HTTP auth uses the
  verified Supabase identity and does not read or mutate legacy session/audit
  tables.
- Active organization/project membership derives the request scope. Clients
  may select one organization if needed but cannot send a project allowlist or
  actor/approver identity.
- Governed mapping persistence matches the current migration: reusable profile,
  immutable version, and one immutable `mapping_version_sheets` row for each
  sheet/entity. Staged rows bind that exact mapping-sheet ID.
- Batch/file, sheet/column, transformation run, staged row/cell, issue, and
  append-only approval persistence use scoped, bound SQL and only the
  `ingestion` schema. Multi-sheet/multi-entity workbooks retain raw/normalized
  values, formula evidence, and source-cell links.
- Approval independently re-derives and verifies the exact source/profile/
  version/input checksum and compares run, validation, and preview checksums.
  Publication has no row-level application fallback: it calls only
  `ingestion.publish_import_batch(uuid, uuid, text)`, whose database transaction
  owns authorization, idempotency, fact upserts, lineage, and state changes.
- `ConstructionFacts` reads structured data only from `construction`.
  `SemanticSearch` filters organization, allowed projects, approval/index state,
  model, dimensions, projection version, and chunking version in dense,
  lexical, and final branches.
- Semantic publication validates stable chunk provenance and 1,536 finite,
  non-zero values, then calls only
  `semantic.publish_chunk_embeddings(uuid, uuid, jsonb, text)`. Reindexing reads
  existing Storage objects, verifies checksums, deduplicates safely, and makes a
  separate idempotent sink/RPC call for each semantic document/job. It has no
  upload, delete, legacy-vector mutation, or cutover operation.
- `PROSIGHT_SCHEMA_MODE` still defaults to `legacy`. `compare` retains legacy
  rollback/comparison capability. `redesigned` activates only membership-scoped
  three-layer fact/search/governed-ingestion routes and blocks legacy data APIs.

## Focused verification

System interpreter (redesign, PostgreSQL adapter, Storage, and evidence tests):

```powershell
$env:PYTHONPATH='src'
$env:PROSIGHT_AI_PROVIDER='local'
$env:PROSIGHT_DATABASE_BACKEND='sqlite'
$env:PROSIGHT_AUTH_PROVIDER='local'
$env:PROSIGHT_AUTH_REQUIRED='0'
python -m unittest tests.test_governed_persistence tests.test_governed_excel tests.test_semantic_redesign tests.test_semantic_reindex tests.test_redesign_runtime tests.test_postgres_backend tests.test_supabase_storage tests.test_evidence_boundaries -v
```

Result: 83 tests ran in 7.266 seconds; all passed. The only output outside test
results was an existing Chroma/asyncio deprecation warning.

Project environment (including the PDF/reportlab ingestion regressions):

```powershell
$env:PYTHONPATH='src'
$env:PROSIGHT_AI_PROVIDER='local'
$env:PROSIGHT_DATABASE_BACKEND='sqlite'
$env:PROSIGHT_AUTH_PROVIDER='local'
$env:PROSIGHT_AUTH_REQUIRED='0'
& .\prosight_env\Scripts\python.exe -m unittest tests.test_ingestion tests.test_evidence_boundaries tests.test_governed_excel tests.test_governed_persistence tests.test_semantic_redesign tests.test_semantic_reindex tests.test_redesign_runtime -v
```

Result: 69 tests ran in 14.103 seconds; all passed. The environment emitted its
existing Starlette/httpx deprecation warning.

Coverage includes transaction ordering and claims, invalid-identity fail-closed,
legacy preservation/rollback, redesigned activation, membership-derived scope,
no obsolete SQL/session access, lifecycle transitions, source and business-key
dedupe, exact approval binding, RPC-only publication/idempotency, construction
SQL reads, semantic tenant/project filters, stable per-document chunks/jobs, and
read-only no-legacy-mutation reindex behavior.

Syntax and patch hygiene:

```powershell
$env:PYTHONPATH='src'
python -m compileall -q src tools tests
git diff --check
```

Result: both exited 0. `git diff --check` emitted only the worktree's existing
LF-to-CRLF conversion warnings and found no whitespace errors. A separate
trailing-whitespace scan of all 15 owned untracked application/test/tool/doc
files also passed.

## Broad verification and environment blockers

The project-environment discovery run executed 207 tests. 202 passed; five
failed before or outside this redesign scope:

- `tests.test_postgres_backend` could not import because that Python environment
  does not have `psycopg` installed. The same module passed under the system
  interpreter in the 83-test focused run.
- Four pre-existing `tests.test_portfolio_import` cases fail because the
  unmodified portfolio parser currently requires an `Allocation` manpower
  column that those unmodified test workbooks omit. Neither
  `src/prosight/ingestion/portfolio.py` nor `tests/test_portfolio_import.py` was
  changed in this workstream.

The discovery command used the same environment variables above and:

```powershell
& .\prosight_env\Scripts\python.exe -m unittest discover -s tests -v
```

No live-database RLS or migration execution was attempted because the request
forbids hosted operations and no local migrated PostgreSQL fixture is available.
The offline application scope is complete; production cutover remains an
operational decision gated by local migration/RLS verification, checksum-safe
reindex of all registered objects, retrieval comparison, and explicit human
acceptance.
