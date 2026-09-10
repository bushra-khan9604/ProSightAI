-- Permit the constrained legacy backend role to enter the redesigned Supabase
-- authenticated role only explicitly inside a verified request transaction.
-- NOINHERIT preserves the legacy prosight_backend privilege surface by default.

begin;

do $role_contract$
declare
    backend_role pg_catalog.pg_roles%rowtype;
begin
    select * into backend_role
    from pg_catalog.pg_roles
    where rolname = 'prosight_backend';

    if not found then
        raise exception 'required legacy role prosight_backend is missing';
    end if;
    if not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
        raise exception 'required Supabase role authenticated is missing';
    end if;
    if backend_role.rolcanlogin
       or backend_role.rolinherit
       or backend_role.rolsuper
       or backend_role.rolcreaterole
       or backend_role.rolcreatedb
       or backend_role.rolreplication
       or backend_role.rolbypassrls then
        raise exception 'prosight_backend must remain NOLOGIN, NOINHERIT, and unprivileged';
    end if;
    if pg_catalog.pg_has_role('authenticated', 'prosight_backend', 'MEMBER') then
        raise exception 'role cycle would allow authenticated to enter prosight_backend';
    end if;

    -- PostgreSQL 16+ records inheritance and SET independently per grant.
    -- Older releases derive inheritance from prosight_backend's NOINHERIT
    -- attribute and permit SET ROLE for an ordinary membership grant.
    if pg_catalog.current_setting('server_version_num')::integer >= 160000 then
        execute 'grant authenticated to prosight_backend with inherit false, set true';
    else
        execute 'grant authenticated to prosight_backend';
    end if;
end
$role_contract$;

-- Construction changes are published by the approval-bound private routine.
-- Authenticated requests retain RLS-filtered reads but no direct base-table DML.
revoke insert, update, delete on all tables in schema construction from authenticated;

comment on role prosight_backend is
    'NOLOGIN NOINHERIT legacy runtime role; may SET ROLE authenticated only in a transaction with verified transaction-local JWT claims';

commit;
