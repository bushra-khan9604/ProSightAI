# Supabase authentication

The existing Supabase project is **ProSight AI** (`rhtcwtmkgeuvvyuirpup`).
The local `.env` is configured with its URL and publishable key. No service-role
key is needed. Restart the Python server after changing these settings:

```dotenv
PROSIGHT_AUTH_PROVIDER=supabase
PROSIGHT_AUTH_REQUIRED=true
PROSIGHT_SEED_DEMO_USERS=false
SUPABASE_URL=https://rhtcwtmkgeuvvyuirpup.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

Install Python dependencies with `python -m pip install -e .`, then build the
frontend with `pnpm --dir frontend install --frozen-lockfile` and
`pnpm --dir frontend run build`. Start with `python -m prosight.cli serve`.

## First account

The project had no Auth users when this integration was installed.

1. In [Supabase Auth Users](https://supabase.com/dashboard/project/rhtcwtmkgeuvvyuirpup/auth/users),
   create an email/password user. The app uses administrator-provisioned accounts.
2. Assign its role from a trusted administrator environment. For example, run
   the following in the Supabase SQL editor after replacing the email:

```sql
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
    || jsonb_build_object('prosight_role', 'admin')
where email = 'replace-with-your-email@example.com';
```

Use `admin`, `project_manager`, or `planning_engineer`. New users without an
assigned role see an access-pending message and cannot read private API data.
Never place this role in user metadata: users can edit that metadata themselves.
For routine account management, the Supabase Admin API can also update
`app_metadata.prosight_role` from a trusted server.

3. Open `/login` and sign in with the account's email and password.

## Protected routes and sessions

`/assistant`, `/dashboard`, `/projects`, and `/resource-allocation` require a
verified identity. Opening a protected URL while signed out redirects to
`/login`; signing in restores that destination. The workspace unmounts on
sign-out, clearing in-memory project and chat state. Browser back/forward and
session changes in other tabs are handled. The SDK persists and refreshes
sessions; API calls, streaming queries, uploads, and template downloads attach
the current access token.

The FastAPI middleware validates tokens against the configured project's
`/auth/v1/user` endpoint on requests. Authorization uses the returned
`app_metadata.prosight_role`. Missing, invalid, anonymous, and unassigned
identities fail closed. Client-supplied query and form roles cannot elevate
access. Private API responses are marked `private, no-store`.

Supabase mode always requires authentication, even if the legacy
`PROSIGHT_AUTH_REQUIRED` flag is false. Local username/password login and local
cookies cannot bypass Supabase. Setting `PROSIGHT_AUTH_PROVIDER=local` explicitly
retains the pre-existing local development mode; do not enable demo users for a
shared deployment.

Project data continues to use the application's existing SQLite repository and
role policies. This change does not introduce Supabase data tables or per-project
membership rules. Supabase Auth user creation does not migrate legacy accounts.

## Verification

```powershell
$env:PYTHONPATH="src"
$env:PROSIGHT_AI_PROVIDER="local"
python -m unittest discover -s tests -p test_supabase_auth.py -v
pnpm --dir frontend run build
```

These security tests mock the Supabase HTTP boundary and use an isolated SQLite
database. A real successful sign-in still requires the first provisioned account.

References: [password sign-in](https://supabase.com/docs/reference/javascript/auth-signinwithpassword),
[trusted user lookup](https://supabase.com/docs/reference/javascript/auth-getuser),
[Admin user updates](https://supabase.com/docs/reference/javascript/auth-admin-updateuserbyid).

Validation during setup: production build passed; 8 new auth tests and 10
existing role-access tests passed. Browser verification confirmed protected URL
redirection, the email sign-in screen, and live Supabase rejection of invalid
credentials without runtime errors. The full offline suite ran 92 tests with
13 errors: missing Chroma/Agents dependencies and portfolio Allocation mapping
validation. Successful live sign-in awaits the first provisioned user.
