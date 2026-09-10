# PostgreSQL and pgvector setup

ProSight selects PostgreSQL when the server has `PROSIGHT_DATABASE_URL`. Without it,
the default remains SQLite. `PROSIGHT_DATABASE_BACKEND` can explicitly select
`postgres` or `sqlite`. A PostgreSQL failure never silently falls back to SQLite.

Keep the PostgreSQL connection URI in the ignored root `.env` or your deployment's
server secret settings. Use the Supabase **Session pooler** connection URI and fill
in its password locally. Do not put it in a `VITE_` variable or commit it. Remote
connections require TLS; the driver defaults to `sslmode=require`. Use
`verify-full` with appropriate trusted certificates for certificate verification.

Install the updated dependencies in the Python environment that runs the backend,
then restart the backend so it reads the new environment:

```powershell
python -m pip install -e .
python -m prosight.db.manage check
python -m prosight.cli serve
```

The existing Windows Store Python environment was unavailable to the coding
session. Validation used the bundled Python runtime with isolated dependencies;
it did not update `prosight_env`. Stop the old backend before restarting it.

## Database initialization and migration

Reviewed migrations live in `supabase/migrations`. Version 1 creates the private
`prosight` schema, pgvector indexes, and backend role. Version 2 adds the governed
employee, training, attendance, payroll, manpower, and deployment tables. The
migration at version 3 creates the private `prosight-pdfs` Storage bucket and adds
immutable object references to approved PDF metadata. The
migration command reads `prosight.schema_version` and applies only the missing
ordered suffix, so it is safe to run against the existing version-1 installation.

For a new, reviewed destination only:

```powershell
python -m prosight.db.manage migrate
python -m prosight.db.manage check
python -m prosight.db.manage import-sqlite data/prosight.db
python -m prosight.db.manage import-sqlite data/prosight.db --apply
```

The migration command executes pending SQL transactionally and records each version
in `prosight.schema_version`; it does not update the Supabase CLI migration-history
table. Reconcile that history before adopting CLI-driven deployments. Startup
requires schema version 3, names the migration command when an older version is
found, and never creates tables or loads demo data. `prosight init` is intentionally
unavailable with PostgreSQL.

The importer reads a consistent, read-only SQLite snapshot. It locks the target
tables, requires an empty destination, and copies records in one transaction.
Local accounts, sessions, and Chroma vectors are excluded. Supabase Auth remains
the login provider; identity and trusted role setup are documented in
`supabase-auth.md`. Original uploaded files remain at their existing disk paths.
PDF approval is preserved, but imported PDFs need explicit reindexing:

```powershell
python -m prosight.db.manage reindex DOCUMENT_ID
```

Only approved PDFs with readable original files can be rebuilt. Embedding calls
use the configured OpenAI API key and incur provider usage. The vector schema
expects 1536-dimensional embeddings; the default is `text-embedding-3-small`.
Changing dimensions requires a migration; changing the embedding model requires
reindexing. Never mix embeddings from different models.

## Retrieval and access boundaries

Structured data and PDF chunks share PostgreSQL. Retrieval combines cosine vector
search with English full-text search using reciprocal rank fusion. Both candidate
queries filter project scope and authoritative document approval/readiness before
ranking. HNSW iterative scans support filtered retrieval. Citation metadata keeps
the source document and page. Embeddings are generated in batches before opening
a transaction; chunk replacement is atomic and rechecks approval under a row lock.
Deleting a document cascades to its vectors.

Every private table has forced RLS. Application transactions assume the constrained
`prosight_backend` role, with a five-connection pool and a 30-second statement
timeout. Supabase `anon`, `authenticated`, and `service_role` cannot directly use
this schema. API authorization must still protect all backend operations.

This is **single-organization persistence**, not tenant isolation. The backend RLS
policy permits all rows for its service role. The configured connection still
authenticates with an administrative credential before assuming that role; use a
dedicated least-privilege login for production and reserve administrator
credentials for migrations.

Tenant membership and per-project authorization, durable ingestion workers,
backup/restore verification, monitoring,
and agent-flow concurrency remain separate production steps. Local PDF paths and
in-process jobs require particular attention before deploying multiple instances.

## Verified project state (2026-09-08)

- Hosted connection succeeds through the session pooler; pgvector version 0.8.2.
- ProSight schema versions 1 through 3 are installed. The seven additive workforce
  tables exist with forced RLS and remain empty; no reference-workbook rows were
  imported by the migration.
- Hosted repository project reads, invoice aggregation, and portfolio summary pass.
- Hosted hybrid SQL, project/approval filtering, approval revocation, and cascading
  vector deletion pass using synthetic records in a rolled-back transaction.
- All 23 private tables have RLS enabled and direct Supabase API roles lack schema
  access. The seven workforce tables also force RLS.
- Targeted PostgreSQL and workforce regression suite: 23 tests passed. A startup
  smoke test completed with the restricted `prosight_backend` role.

Real PDF upload-to-answer validation remains pending an approved PDF. The SQL
retrieval checks used synthetic vectors and do not measure answer quality or latency.
