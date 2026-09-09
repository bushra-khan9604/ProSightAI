"""PostgreSQL adapter for the existing, parameterized repository operations.

Schema installation is explicit. Connecting never seeds samples, modifies schema,
or falls back to SQLite. The backend role is server-only, not tenant authorization.
"""
from __future__ import annotations

import re
from contextlib import closing

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..repository import ProjectRepository

REQUIRED_SCHEMA_VERSION = 2
MIGRATION_COMMAND = "python -m prosight.db.manage migrate"

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
        self.pool = ConnectionPool(
            conninfo="", kwargs={**options, "row_factory": dict_row,
                                  "prepare_threshold": None, "connect_timeout": 10},
            min_size=0, max_size=5, timeout=10, open=True,
        )

    def connect(self):
        return RepositoryConnection(self.pool)

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

    def _ensure(self):
        self.ensure_schema()

    def initialize(self, source=None):
        raise RuntimeError("PostgreSQL never loads demo data automatically; use the reviewed SQLite import command")

    def close(self):
        self.pool.close()
