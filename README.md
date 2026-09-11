# ProSight AI

ProSight AI is a Supabase-backed construction intelligence application. It
combines governed portfolio data, private document ingestion, hybrid pgvector
retrieval, reviewed workbook imports, a responsive React command center, and
traceable OpenAI agents.

## Production foundation

- Supabase Auth with email/password signup, login, refresh, logout, and password recovery.
- Protected `/app/*` routes and bearer-token enforcement on every `/api/*` route except health.
- PostgreSQL with RLS, user profiles, project memberships, audits, notifications, and approval ownership.
- Private Supabase Storage buckets for project documents and portfolio imports.
- Page-aware PDF chunks, GIN full-text search, HNSW `halfvec(1536)`, and reciprocal-rank hybrid search.
- `pgmq` embedding jobs processed by a scheduled Edge Function using `text-embedding-3-small`.
- Idempotent legacy SQLite/file migration with dry-run, row-count, and file-checksum verification.

The original FastAPI agent contracts and the established React visual flow are
preserved. The sidebar now displays the verified identity and role rather than
allowing users to impersonate a role.

## Local application setup

Python 3.11+ and Node.js 20+ are required.

```powershell
Copy-Item .env.example .env
# Fill in the Supabase and OpenAI settings in .env.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
pnpm --dir frontend install
pnpm --dir frontend run build
.\.venv\Scripts\python.exe -m prosight.cli serve
```

Open `http://127.0.0.1:8000`. For frontend development, run
`pnpm --dir frontend run dev` alongside the FastAPI server. Vite reads the
repository-root `.env` and proxies `/api` to port 8000.

The public health endpoint is available at `/api/health`. All other API calls
require a valid Supabase access token; the browser client attaches it
automatically.

## Supabase rollout

The complete hosted rollout and rollback checklist is in
[`docs/supabase-rollout.md`](docs/supabase-rollout.md). In outline:

```powershell
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
supabase secrets set OPENAI_API_KEY=... EMBEDDING_WORKER_SECRET=...
supabase functions deploy embedding-worker --no-verify-jwt
supabase functions deploy hybrid-search
python -m prosight.cli migrate-supabase --sqlite data\prosight.db --dry-run
python -m prosight.cli migrate-supabase --sqlite data\prosight.db
```

The bootstrap administrator must first create an account using the configured
email. Set `PROSIGHT_BOOTSTRAP_ADMIN_EMAIL` only for migration. Further role and
membership changes are intentionally handled in the Supabase dashboard.

Do not switch `PROSIGHT_DATA_BACKEND` to `supabase` until the migration report
returns `verified: true`, authentication/RLS checks pass, and all migrated PDFs
have reached `ready`.

## Ingestion and retrieval

PDFs remain within page boundaries and long pages are token-aware chunked with
overlap. Chunk inserts enqueue embedding work. The private worker batches
OpenAI embedding requests, records attempts/errors, retries transient failures,
and advances the parent document/job to `ready` only when all chunks succeed.
Queries use an authenticated Edge Function to create the query embedding and
invoke the security-invoker hybrid-search RPC under the caller's JWT.

Workbook imports continue to create previews and require approval before
governed data changes. Employees are read-only and receive masked contact
details. Administrators retain portfolio-wide access; other users require a
project membership.

## Legacy migration source

SQLite is no longer a production backend. It remains available for isolated
legacy tests and as the cutover source. The migrator preserves stable IDs and
project codes, uploads source files to private Storage, supports repeat runs,
and compares remote row counts and downloaded object SHA-256 checksums.

Keep the SQLite database and upload directories read-only until representative
payloads, counts, checksums, authentication, RLS, and re-indexing have passed.
There are no dual writes.

## Tests

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:PROSIGHT_AI_PROVIDER="local"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
pnpm --dir frontend run build
```

The unit suite runs without OpenAI calls. Supabase RLS/Auth/Storage and Edge
Function integration tests should run against an isolated local or test
project before pushing the migrations to production.

## Repository map

- `supabase/migrations/` — PostgreSQL schema, RLS, Storage policies, queue, search, and cron.
- `supabase/functions/` — authenticated hybrid search and private embedding worker.
- `src/prosight/auth.py` — JWKS token verification and request-scoped identity.
- `src/prosight/supabase_repository.py` — RLS-aware production repository.
- `src/prosight/migration.py` — legacy SQLite and file migration.
- `src/prosight/rag/` — page-aware pgvector retrieval adapter.
- `frontend/src/AuthApp.jsx` — landing, Auth flows, and protected routing.
- `docs/architecture.md` — implemented architecture and trust boundaries.
- `docs/supabase-rollout.md` — deployment, verification, and rollback runbook.

All names, contact details, clients, values, and documents in the sample data
are fictional.
