"""PostgreSQL adapter for the existing, parameterized repository operations.

Schema installation is explicit. Connecting never seeds samples, modifies schema,
or falls back to SQLite. The backend role is server-only, not tenant authorization.
"""
from __future__ import annotations

import re
import json
import uuid
from contextlib import closing

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..repository import ProjectRepository

REQUIRED_SCHEMA_VERSION = 3
MIGRATION_COMMAND = "python -m prosight.db.manage migrate"
REDESIGN_SCHEMA_CHECK_SQL = """
select
  pg_catalog.to_regclass('construction.organization_members') is not null as has_memberships,
  pg_catalog.to_regclass('ingestion.mapping_version_sheets') is not null as has_ingestion,
  pg_catalog.to_regclass('semantic.semantic_chunks') is not null as has_semantic,
  pg_catalog.to_regprocedure('ingestion.publish_import_batch(uuid,uuid,text)') is not null as has_publish_rpc,
  pg_catalog.to_regprocedure('semantic.publish_chunk_embeddings(uuid,uuid,jsonb,text)') is not null as has_index_rpc,
  pg_catalog.pg_has_role(current_user, 'authenticated', 'MEMBER') as can_enter_authenticated
"""

# Only repository-authored SQL enters this compiler. Quoted text/identifiers and
# PostgreSQL casts are preserved; user values always remain bound parameters.
_SQL_TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|::[A-Za-z_][A-Za-z_0-9]*|:[A-Za-z_][A-Za-z_0-9]*|\?")


def postgres_query(query: str) -> str:
    def replace(match):
        token = match.group()
        if token == "?":
            return "%s"
        if token.startswith(":") and not token.startswith("::"):
            return "%(" + token[1:] + ")s"
        return token
    return _SQL_TOKEN.sub(replace, query.replace("%", "%%"))


class RepositoryConnection:
    """A pooled, transaction-scoped connection compatible with repository calls."""
    def __init__(self, pool):
        self._pool = pool
        self._connection = pool.getconn(timeout=10)
        self._closed = False
        try:
            self._connection.execute("SET LOCAL ROLE prosight_backend")
            self._connection.execute("SET LOCAL search_path = prosight, extensions, pg_catalog")
            self._connection.execute("SET LOCAL statement_timeout = '30s'")
        except Exception:
            self.close()
            raise

    def execute(self, query, params=None):
        return self._connection.execute(postgres_query(query) if params is not None else query, params)

    def execute_native(self, query, params=None):
        return self._connection.execute(query, params)

    def executemany(self, query, params):
        cursor = self._connection.cursor()
        cursor.executemany(postgres_query(query), params)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            self._connection.commit()
        else:
            self._connection.rollback()

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._connection.rollback()
            finally:
                self._pool.putconn(self._connection)


class AuthenticatedRepositoryConnection:
    """One redesigned-schema transaction bound to a verified Supabase user.

    The caller must pass a ``uuid.UUID`` produced only after server-side session
    verification.  Tenant and project claims are deliberately absent: RLS
    derives authorization from current membership rows using ``auth.uid()``.
    """

    def __init__(self, pool, server_verified_user_id: uuid.UUID):
        if not isinstance(server_verified_user_id, uuid.UUID):
            raise ValueError("A server-verified UUID user identity is required")
        self._pool = pool
        self._connection = pool.getconn(timeout=10)
        self._closed = False
        self._finished = False
        subject = str(server_verified_user_id)
        claims = json.dumps(
            {"role": "authenticated", "sub": subject},
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            # These statements start and configure the same transaction before
            # any application query can observe RLS-protected rows.
            self._connection.execute("SET LOCAL ROLE authenticated")
            self._connection.execute(
                "SELECT pg_catalog.set_config(%s, %s, true)",
                ("request.jwt.claim.sub", subject),
            )
            self._connection.execute(
                "SELECT pg_catalog.set_config(%s, %s, true)",
                ("request.jwt.claims", claims),
            )
            self._connection.execute(
                "SET LOCAL search_path = construction, ingestion, semantic, extensions, pg_catalog"
            )
            self._connection.execute("SET LOCAL statement_timeout = '30s'")
        except Exception:
            self.close()
            raise

    def _require_active(self) -> None:
        if self._closed or self._finished:
            raise RuntimeError("Authenticated database transaction is no longer active")

    def execute(self, query, params=None):
        self._require_active()
        return self._connection.execute(
            postgres_query(query) if params is not None else query, params
        )

    def execute_native(self, query, params=None):
        self._require_active()
        return self._connection.execute(query, params)

    def executemany(self, query, params):
        self._require_active()
        cursor = self._connection.cursor()
        cursor.executemany(postgres_query(query), params)
        return cursor

    def __enter__(self):
        self._require_active()
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        self._finished = True

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                if not self._finished:
                    self._connection.rollback()
            finally:
                self._pool.putconn(self._connection)


class PostgresRepository(ProjectRepository):
    """Reuse governed operations with an explicitly migrated PostgreSQL schema."""
    integrity_error = psycopg.IntegrityError
    backend = "postgres"

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("Set PROSIGHT_DATABASE_URL in the server environment")
        try:
            options = conninfo_to_dict(database_url)
        except psycopg.Error:
            raise ValueError("PROSIGHT_DATABASE_URL must be a PostgreSQL connection URI") from None
        host = options.get("host", "")
        if host not in {"localhost", "127.0.0.1", "::1"}:
            if options.get("sslmode", "require") not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("Remote PostgreSQL requires SSL")
            options.setdefault("sslmode", "require")
        self._schema_checked = False
        self._redesign_schema_checked = False
        self.pool = ConnectionPool(
            conninfo="", kwargs={**options, "row_factory": dict_row,
                                  "prepare_threshold": None, "connect_timeout": 10},
            min_size=0, max_size=5, timeout=10, open=True,
        )

    def connect(self):
        return RepositoryConnection(self.pool)

    def connect_authenticated(self, server_verified_user_id: uuid.UUID):
        """Open a redesigned-schema transaction under request-scoped RLS."""
        return AuthenticatedRepositoryConnection(self.pool, server_verified_user_id)

    def ensure_schema(self):
        if self._schema_checked:
            return
        try:
            with closing(self.connect()) as db:
                rows = db.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
        except psycopg.Error:
            # Runtime construction happens before FastAPI's lifespan starts. Close
            # the pool here so failed startup cannot leave worker threads behind.
            self.close()
            raise RuntimeError(
                "PostgreSQL is unavailable or the ProSight schema cannot be read"
            ) from None
        versions = {int(row["version"]) for row in rows}
        if REQUIRED_SCHEMA_VERSION not in versions:
            self.close()
            installed = max(versions) if versions else "none"
            raise RuntimeError(
                f"PostgreSQL schema version {REQUIRED_SCHEMA_VERSION} is required "
                f"(found {installed}). Run `{MIGRATION_COMMAND}` before starting ProSight."
            )
        self._schema_checked = True

    def ensure_redesign_schema(self) -> None:
        """Verify only redesigned catalog objects, without touching legacy tables."""
        if self._redesign_schema_checked:
            return
        connection = self.pool.getconn(timeout=10)
        try:
            row = connection.execute(REDESIGN_SCHEMA_CHECK_SQL).fetchone()
            checks = dict(row) if row is not None else {}
            missing = [name for name, present in checks.items() if not present]
            if missing:
                raise RuntimeError(
                    "Database redesign is not ready (failed checks: "
                    + ", ".join(sorted(missing))
                    + ")"
                )
            self._redesign_schema_checked = True
        except psycopg.Error:
            raise RuntimeError("PostgreSQL redesign catalog cannot be verified") from None
        finally:
            connection.rollback()
            self.pool.putconn(connection)

    def _ensure(self):
        self.ensure_schema()

    def initialize(self, source=None):
        raise RuntimeError("PostgreSQL never loads demo data automatically; use the reviewed SQLite import command")

    def close(self):
        self.pool.close()
