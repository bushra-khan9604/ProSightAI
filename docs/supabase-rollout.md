# Supabase hosted rollout

Run this procedure against an isolated test project first. None of the values
below belong in source control.

## 1. Required settings

Configure the repository-root `.env` from `.env.example`:

- `SUPABASE_PROJECT_REF`, `SUPABASE_URL`, and `VITE_SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY` and `VITE_SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY` (server and migration process only)
- `SUPABASE_DB_URL` (CLI/operations only)
- `OPENAI_API_KEY` and `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`
- `PROSIGHT_APP_URL`
- `PROSIGHT_BOOTSTRAP_ADMIN_EMAIL`
- optional `RAG_*` tuning values documented in `.env.example`

Never expose the service-role key, database URL, or OpenAI key
to Vite. Only variables prefixed `VITE_` are bundled into the browser.

## 2. Auth and schema

In Supabase Auth settings, enable email/password signup, disable email
confirmation, set the Site URL to the deployed app, and allow both the deployed
root URL and local root URL as password-recovery redirects.

```powershell
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

Create the first user through the app using exactly the configured bootstrap
email. The migration command promotes that existing profile to `admin`. This is
the only automated elevation; later role and membership changes are made in the
Supabase dashboard.

## 3. In-application RAG

No Edge Function, Vault secret, cron schedule, or separate worker is required.
The latest migration disables the old queue triggers and schedule. FastAPI uses
its server-only OpenAI key to embed documents in its two-thread ingestion pool
and uses the caller JWT for hybrid retrieval.

## 4. Dry run and migration

Take read-only copies of `data/prosight.db`, `data/uploads`, and
`data/portfolio_imports` before proceeding.

```powershell
python -m prosight.cli migrate-supabase --sqlite data\prosight.db --dry-run
python -m prosight.cli migrate-supabase --sqlite data\prosight.db
```

The real run is successful only when `verified` is `true`, every target row
count is at least its source count, and `file_checksums.mismatches` is empty.
Reruns merge rows by their stable primary keys and overwrite the same scoped
object keys.

Legacy Chroma vectors are deliberately ignored. Allow the imported source PDFs
to be parsed and re-indexed into pgvector with the configured embedding model.

## 5. Verification gate

Before cutover, verify:

1. Signup creates an immediate employee session, profile, and memberships.
2. Login, refresh, password recovery, and logout work at deployed URLs.
3. Missing, expired, and malformed tokens receive `401`; valid users without a
   project membership receive `403` or no RLS-visible rows.
4. Employees see masked contacts and cannot mutate data.
5. Cross-project Data API, Storage, and hybrid-search requests return no data.
6. Project counts, representative JSON payloads, dates, stable IDs, and object
   SHA-256 values match the source report.
7. PDF jobs progress from parsing to embedding to ready; failed chunks retry
   and terminal failures are visible on their job/document.
8. Keyword, semantic, effective-date, project isolation, page citations,
   duplicate rejection, and deletion cascades behave as expected.
9. Portfolio queries, streamed assistant states, approvals, notifications,
   uploads, schedules, invoices, manpower, responsive layout, and theme all
   pass regression checks.

After the gate passes, set `PROSIGHT_DATA_BACKEND=supabase`, deploy the backend
and frontend together, and smoke-test `/api/health`, `/api/me`, and one cited
query.

## 6. Rollback

If verification fails, do not cut over. Keep serving the preserved SQLite and
upload copy read-only, correct the migration or policy, and rerun the idempotent
import. Because there are no dual writes, rollback before cutover is simply
leaving the legacy deployment active. Retain backups until Auth, relational
data, Storage, and RAG all pass acceptance.
