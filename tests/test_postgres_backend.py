"""PostgreSQL backend contracts, SQL binding and pgvector publication tests."""
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from prosight.config import get_settings
from prosight.db.postgres import PostgresRepository, RepositoryConnection, postgres_query
from prosight.db.manage import _migration_plan, apply_pending_migrations, import_sqlite
from prosight.rag.pgvector_store import PgVectorStore, HYBRID_SQL
from prosight.repository import ProjectRepository, DEFAULT_DATA


class BindingTests(unittest.TestCase):
    def test_values_remain_bound_and_literals_are_preserved(self):
        query = "SELECT '?' AS literal, col::text FROM projects WHERE code=? AND name LIKE :name"
        self.assertEqual("SELECT '?' AS literal, col::text FROM projects WHERE code=%s AND name LIKE %(name)s", postgres_query(query))

    def test_sql_percent_is_escaped_for_psycopg(self):
        self.assertEqual("SELECT '100%%' WHERE code=%s", postgres_query("SELECT '100%' WHERE code=?"))

    def test_repository_connection_uses_restricted_transaction_role(self):
        pool = Mock()
        connection = RepositoryConnection(pool)
        self.assertIn(unittest.mock.call('SET LOCAL ROLE prosight_backend'),pool.getconn.return_value.execute.call_args_list)
        with connection:
            connection.execute('SELECT ? AS value',("x'; DROP TABLE projects; --",))
        pool.getconn.return_value.execute.assert_called_with('SELECT %s AS value',("x'; DROP TABLE projects; --",))
        pool.getconn.return_value.commit.assert_called_once()
        connection.close()
        pool.putconn.assert_called_once()

    def test_failed_repository_transaction_rolls_back(self):
        pool=Mock()
        with closing(RepositoryConnection(pool)) as connection:
            with self.assertRaises(ValueError):
                with connection:
                    raise ValueError('test')
        pool.getconn.return_value.commit.assert_not_called()
        self.assertGreaterEqual(pool.getconn.return_value.rollback.call_count,1)

    def test_postgres_never_seeds_or_falls_back(self):
        with patch('prosight.db.postgres.ConnectionPool'):
            repository=PostgresRepository('postgresql://test:test@localhost/test')
            with self.assertRaises(RuntimeError):
                repository.initialize()
        with self.assertRaises(ValueError):
            PostgresRepository('postgresql://test:test@example.org/test?sslmode=disable')


class ConfigurationTests(unittest.TestCase):
    def test_url_selects_postgres_and_explicit_local_override_is_available(self):
        with patch.dict(os.environ, {'PROSIGHT_DATABASE_URL':'postgresql://local/test','PROSIGHT_DATABASE_BACKEND':'postgres'}):
            self.assertEqual('postgres',get_settings().database_backend)
        with patch.dict(os.environ, {'PROSIGHT_DATABASE_URL':'','PROSIGHT_DATABASE_BACKEND':'postgres'}):
            with self.assertRaises(ValueError):
                get_settings()


class SchemaMigrationTests(unittest.TestCase):
    @patch('prosight.db.postgres.ConnectionPool')
    def test_missing_workforce_migration_closes_pool_and_names_remedy(self, pool_class):
        repository = PostgresRepository('postgresql://test:test@localhost/test')
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [{'version': 1}]
        repository.connect = Mock(return_value=connection)

        with self.assertRaisesRegex(RuntimeError, r'version 2.*found 1.*manage migrate'):
            repository.ensure_schema()

        connection.close.assert_called_once()
        pool_class.return_value.close.assert_called_once()

    @patch('prosight.db.postgres.ConnectionPool')
    def test_current_schema_is_checked_only_once(self, pool_class):
        repository = PostgresRepository('postgresql://test:test@localhost/test')
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [{'version': 1}, {'version': 2}]
        repository.connect = Mock(return_value=connection)

        repository.ensure_schema()
        repository.ensure_schema()

        repository.connect.assert_called_once()
        pool_class.return_value.close.assert_not_called()

    def test_migration_plan_rejects_a_version_gap(self):
        self.assertEqual([2], [version for version, _ in _migration_plan({1})])
        with self.assertRaisesRegex(ValueError, 'not contiguous'):
            _migration_plan({2})

    def test_migrate_applies_only_the_workforce_suffix(self):
        connection = Mock()
        relation = Mock()
        relation.fetchone.return_value = ('prosight.schema_version',)
        versions = Mock()
        versions.fetchall.return_value = [(1,)]
        connection.execute.side_effect = [Mock(), relation, versions, Mock()]

        self.assertEqual([2], apply_pending_migrations(connection))

        applied_sql = connection.execute.call_args_list[-1].args[0]
        self.assertIn('CREATE TABLE employees', applied_sql)
        self.assertIn('INSERT INTO schema_version(version) VALUES (2)', applied_sql)


class PgVectorTests(unittest.TestCase):
    def setUp(self):
        self.repository=Mock()
        self.connection=self.repository.connect.return_value
        self.connection.__enter__=Mock(return_value=self.connection)
        self.connection.__exit__=Mock(return_value=False)
        self.embedder=Mock(side_effect=lambda texts:[[1.0]+[0.0]*1535 for text in texts])
        self.store=PgVectorStore(self.repository,self.embedder)
        self.chunk={'id':'D1:1:1','text':'Commissioning report','metadata':{
            'document_id':'D1','project_code':'P1','approval_status':'approved',
            'filename':'Report.pdf','page_number':1,'chunk_number':1,
        }}

    def test_empty_allowlist_does_not_embed_or_query(self):
        result=self.store.search('report','P1',document_ids=[])
        self.assertEqual([],result.evidence)
        self.embedder.assert_not_called()
        self.repository.connect.assert_not_called()

    def test_embedding_dimensions_and_nonfinite_values_are_rejected(self):
        for vector in ([1.0], [float('nan')]*1536, [0.0]*1536):
            with self.assertRaises(ValueError):
                self.store._vector(vector)

    def test_unapproved_chunks_are_rejected_before_embedding(self):
        self.chunk['metadata']['approval_status']='pending'
        with self.assertRaises(ValueError):
            self.store.add_chunks([self.chunk])
        self.embedder.assert_not_called()

    def test_embedding_failure_does_not_open_publication_transaction(self):
        self.embedder.side_effect=RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            self.store.add_chunks([self.chunk])
        self.repository.connect.assert_not_called()

    def test_approval_is_rechecked_under_lock_before_replacement(self):
        self.connection.execute.return_value.fetchone.return_value={'approval_status':'rejected','project_code':'P1'}
        with self.assertRaises(ValueError):
            self.store.add_chunks([self.chunk])
        self.connection.executemany.assert_not_called()
        self.assertIn('FOR UPDATE',self.connection.execute.call_args.args[0])

    def test_search_passes_scope_and_returns_citations(self):
        self.connection.execute_native.return_value.fetchall.return_value=[{
            'body':'Commissioning report','metadata':self.chunk['metadata'],'relevance':0.01,
        }]
        result=self.store.search('report','P1',document_ids=['D1'])
        params=self.connection.execute_native.call_args.args[1]
        self.assertEqual('P1',params['project'])
        self.assertEqual(['D1'],params['documents'])
        self.assertEqual('Report.pdf, page 1',result.evidence[0].citation)
        self.assertEqual(2,HYBRID_SQL.count("c.project_code=%(project)s"))


class ImportPreviewTests(unittest.TestCase):
    def test_preview_does_not_connect_to_destination_or_copy_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.db'
            repository=ProjectRepository(source)
            repository.initialize(DEFAULT_DATA)
            target=Mock()
            preview=import_sqlite(target,source)
            self.assertFalse(preview['applied'])
            self.assertEqual(4,preview['rows']['projects'])
            self.assertIn('sessions',preview['excluded'])
            target.connect.assert_not_called()


if __name__=='__main__':
    unittest.main()
