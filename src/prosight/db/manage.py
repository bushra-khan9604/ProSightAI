"""Explicit migration and read-only-source import commands; never run on startup."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import psycopg
from psycopg import sql

from ..config import get_settings
from .postgres import PostgresRepository, REQUIRED_SCHEMA_VERSION

MIGRATION_ROOT = Path(__file__).resolve().parents[3] / 'supabase/migrations'
MIGRATIONS = (
    (1, MIGRATION_ROOT / '20260907161807_prosight_postgres_pgvector.sql'),
    (2, MIGRATION_ROOT / '20260908120000_workforce_imports.sql'),
    (3, MIGRATION_ROOT / '20260909183928_add_pdf_storage.sql'),
)
IMPORT_TABLES = (
    'projects', 'documents', 'ingestion_jobs', 'change_requests', 'audit_events',
    'notifications', 'portfolio_imports', 'portfolio_import_jobs',
    'manpower_assignments', 'project_invoices', 'project_schedule_activities',
    'employees', 'employee_training', 'attendance_records', 'payroll_records',
    'direct_allocations', 'subcontract_crews', 'deployment_forecasts', 'seed_migrations',
)


def _migration_plan(installed: set[int]) -> list[tuple[int, Path]]:
    """Return the ordered, unapplied migration suffix and reject history gaps."""
    pending: list[tuple[int, Path]] = []
    for migration in MIGRATIONS:
        version = migration[0]
        if version in installed:
            if pending:
                raise ValueError('ProSight schema version history is not contiguous; review before migrating')
        else:
            pending.append(migration)
    return pending


def apply_pending_migrations(connection) -> list[int]:
    """Apply only missing ProSight migrations in one administrator transaction."""
    connection.execute('SELECT pg_advisory_xact_lock(714028190)')
    relation = connection.execute("SELECT to_regclass('prosight.schema_version')").fetchone()
    installed = set()
    if relation and relation[0] is not None:
        installed = {int(row[0]) for row in connection.execute(
            'SELECT version FROM prosight.schema_version ORDER BY version'
        ).fetchall()}
    plan = _migration_plan(installed)
    for _, migration in plan:
        connection.execute(migration.read_text(encoding='utf-8'))
    return [version for version, _ in plan]


def import_sqlite(repository, source: Path, apply=False):
    """Copy a consistent SQLite snapshot into an empty PostgreSQL destination.

    Local accounts/sessions are intentionally excluded. Original files stay on
    disk; no Chroma vectors are copied. Approval is preserved but document indexes
    become not_indexed until approved originals are explicitly rebuilt.
    """
    if not source.is_file():
        raise ValueError('SQLite source does not exist')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as original:
        original.row_factory = sqlite3.Row
        original.execute('BEGIN')
        tables = {r[0] for r in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {table: original.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                  for table in IMPORT_TABLES if table in tables}
        if not apply:
            return {'applied': False, 'rows': counts, 'excluded': ['users', 'sessions', 'Chroma vectors']}
        repository.ensure_schema()
        with closing(repository.connect()) as destination:
            with destination:
                destination.execute('SELECT pg_advisory_xact_lock(714028190)')
                # Block application writes while checking and importing, preserving
                # the empty-target guarantee even if a request starts concurrently.
                destination.execute('LOCK TABLE '+','.join(IMPORT_TABLES)+' IN EXCLUSIVE MODE')
                for table in IMPORT_TABLES:
                    if destination.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()['count']:
                        raise ValueError('Import requires an empty destination; existing data was not overwritten')
                for table in counts:
                    columns = [r['name'] for r in original.execute(f'PRAGMA table_info("{table}")')]
                    target_columns = {r['column_name'] for r in destination.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='prosight' AND table_name=?",
                        (table,),
                    ).fetchall()}
                    if not set(columns) <= target_columns:
                        raise ValueError('Source schema has unsupported columns; review before importing')
                    statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                        sql.Identifier('prosight',table),
                        sql.SQL(',').join(map(sql.Identifier,columns)),
                        sql.SQL(',').join(sql.Placeholder() for _ in columns),
                    )
                    cursor = original.execute(f'SELECT * FROM "{table}"')
                    while batch := cursor.fetchmany(250):
                        destination._connection.cursor().executemany(statement,[tuple(r) for r in batch])
                destination.execute("""UPDATE documents SET index_status='not_indexed',
                    status=CASE WHEN approval_status='approved' THEN 'approved' ELSE status END WHERE kind='pdf'""")
        return {'applied': True, 'rows': counts, 'notice': 'Approved PDFs require explicit reindexing'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('check',help='Verify connection, schema and vector extension without modifying data')
    sub.add_parser('migrate',help='Apply reviewed, pending PostgreSQL migrations in order')
    source=sub.add_parser('import-sqlite',help='Preview SQLite row counts; --apply copies into an empty destination')
    source.add_argument('source',type=Path)
    source.add_argument('--apply',action='store_true')
    reindex=sub.add_parser('reindex',help='Rebuild one explicitly approved PDF from its original file')
    reindex.add_argument('document_id')
    args=parser.parse_args()
    settings=get_settings()
    if not settings.database_url:
        parser.error('Set PROSIGHT_DATABASE_URL in your ignored local .env file')
    if args.command=='migrate':
        # Administrator connection is used only for explicit migration. Application
        # requests always SET LOCAL ROLE to the constrained backend role instead.
        options=psycopg.conninfo.conninfo_to_dict(settings.database_url)
        if options.get('host') not in {'localhost','127.0.0.1','::1'}:
            if options.get('sslmode','require') not in {'require','verify-ca','verify-full'}:
                parser.error('Remote PostgreSQL requires SSL')
            options.setdefault('sslmode','require')
        with psycopg.connect(**options,connect_timeout=10,prepare_threshold=None) as connection:
            applied = apply_pending_migrations(connection)
        print(json.dumps({
            'applied_versions': applied,
            'schema_version': REQUIRED_SCHEMA_VERSION,
            'source_data_imported': False,
        }))
        return
    repository=PostgresRepository(settings.database_url)
    try:
        if args.command=='import-sqlite':
            print(json.dumps(import_sqlite(repository,args.source,args.apply),indent=2))
        elif args.command=='check':
            repository.ensure_schema()
            with closing(repository.connect()) as db:
                row=db.execute("SELECT current_user AS role, extversion FROM pg_extension WHERE extname='vector'").fetchone()
                version=db.execute('SELECT max(version) AS version FROM schema_version').fetchone()['version']
                print(json.dumps({'connected':True,'schema_version':version,**row}))
        else:
            from ..ingestion.pdf import extract_pdf_chunks
            from ..rag.pgvector_store import PgVectorStore
            repository.ensure_schema()
            document=repository.get_document(args.document_id)
            if not document or document['kind']!='pdf' or document.get('approval_status')!='approved':
                raise ValueError('Only an existing approved PDF may be reindexed')
            chunks=extract_pdf_chunks(Path(document['stored_path']),document)
            PgVectorStore(repository).add_chunks(chunks)
            with closing(repository.connect()) as db:
                with db:
                    db.execute("UPDATE documents SET status='ready',index_status='ready' WHERE id=? AND approval_status='approved'",
                               (document['id'],))
            print(json.dumps({'document_id':document['id'],'indexed_chunks':len(chunks)}))
    finally:
        repository.close()


if __name__=='__main__':
    try:
        main()
    except (psycopg.Error, RuntimeError, ValueError) as error:
        # Connection exceptions may contain user/host information. Do not print
        # connection strings, passwords, source records, or raw server errors.
        print('Operation failed ('+type(error).__name__+'). Verify credentials, migration state and input; no automatic fallback occurred.')
        raise SystemExit(1)
