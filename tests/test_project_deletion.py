"""Project erasure must be authenticated, scoped, complete, and retryable."""
import json
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from prosight.repository import ProjectRepository, DEFAULT_DATA
from prosight.project_deletion import ProjectDeletion
from prosight.api import create_app

class ProjectDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.repo=ProjectRepository(self.root/'test.db'); self.repo.initialize(DEFAULT_DATA)
        self.code=self.repo.list_projects(user_role='admin')[0]['code']
        self.other=self.repo.list_projects(user_role='admin')[1]['code']
        self.upload=self.root/'uploads'; self.upload.mkdir()
        self.portfolio=self.root/'imports'; self.portfolio.mkdir()
        self.rag=Mock()
        self.service=ProjectDeletion(self.repo,self.rag,self.upload,self.portfolio)
    def document(self,path=None):
        path=path or self.upload/'report.pdf';path.write_bytes(b'%PDF synthetic')
        return self.repo.create_document(self.code,'report.pdf','pdf','checksum',str(path))
    def test_full_cleanup_preserves_other_project_and_rejects_late_upload(self):
        doc=self.document();job=self.repo.create_job(doc['id']);self.repo.update_job(job['id'],'ready',100,'done')
        change=self.repo.create_change_request('document_approve',self.code,{'document_id':doc['id']},{},'admin')
        with closing(self.repo.connect()) as db:
            with db:
                self.repo._insert_audit(db,'admin','document_approve','document',doc['id'],None,{'project_code':self.code},self.repo._now())
        result=self.service.delete(self.code,'admin')
        self.assertTrue(result['deleted']);self.assertFalse((self.upload/'report.pdf').exists())
        self.rag.delete_document.assert_called_once_with(doc['id'])
        self.assertIsNone(self.repo.get_document(doc['id']));self.assertIsNone(self.repo.get_change_request(change['id']))
        self.assertTrue(any(p['code']==self.other for p in self.repo.list_projects(user_role='admin')))
        self.assertFalse(any(p['code']==self.code for p in self.repo.list_projects(user_role='admin')))
        with self.assertRaisesRegex(ValueError,'deleted'):
            self.repo.create_document(self.code,'late.pdf','pdf','late','unused')
        with closing(self.repo.connect()) as db:
            self.assertEqual(0,db.execute('SELECT count(*) FROM notifications WHERE project_code=?',(self.code,)).fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM audit_events WHERE target_id=?',(doc['id'],)).fetchone()[0])
    def test_active_job_blocks_deletion(self):
        doc=self.document();self.repo.create_job(doc['id'])
        with self.assertRaisesRegex(ValueError,'active'):self.service.delete(self.code,'admin')
        self.assertTrue((self.upload/'report.pdf').exists());self.rag.delete_document.assert_not_called()
    def test_outside_storage_is_not_deleted(self):
        outside=self.root/'outside.pdf';self.document(outside)
        with self.assertRaisesRegex(ValueError,'outside'):self.service.delete(self.code,'admin')
        self.assertTrue(outside.exists());self.rag.delete_document.assert_not_called()
    def test_cleanup_failure_keeps_database_for_retry(self):
        doc=self.document();self.rag.delete_document.side_effect=RuntimeError('offline')
        with self.assertRaises(RuntimeError):self.service.delete(self.code,'admin')
        self.assertIsNotNone(self.repo.get_document(doc['id']));self.assertTrue((self.upload/'report.pdf').exists())
        self.rag.delete_document.side_effect=None;self.service.delete(self.code,'admin')
        self.assertIsNone(self.repo.get_document(doc['id']))
    def test_shared_pending_import_removed_without_deleting_other_project(self):
        path=self.portfolio/'shared.xlsx';path.write_bytes(b'PK synthetic')
        imp=self.repo.create_portfolio_import('shared.xlsx','sum',str(path),'admin')
        self.repo.set_portfolio_import_status(imp['id'],'awaiting_approval','pending')
        change=self.repo.create_change_request('portfolio_import','PORTFOLIO',{'import_id':imp['id'],'parsed':{'invoices':[{'project_code':self.code},{'project_code':self.other}]}},{},'admin')
        self.service.delete(self.code,'admin')
        self.assertFalse(path.exists());self.assertIsNone(self.repo.get_portfolio_import(imp['id']))
        self.assertIsNone(self.repo.get_change_request(change['id']))
        self.assertTrue(any(p['code']==self.other for p in self.repo.list_projects(user_role='admin')))
    def test_api_requires_actual_admin_identity_and_exact_confirmation(self):
        with patch('prosight.api.RAGStore',side_effect=RuntimeError('offline')):
            app=create_app(self.repo)
        with TestClient(app) as client:
            url=f'/api/projects/{self.code}?role=admin&confirmation={self.code}'
            self.assertEqual(401,client.delete(url).status_code)
            with patch.object(self.repo,'get_session_user',return_value={'role':'project_manager'}):
                self.assertEqual(403,client.delete(url).status_code)
            with patch.object(self.repo,'get_session_user',return_value={'role':'admin'}):
                self.assertEqual(400,client.delete(f'/api/projects/{self.code}?confirmation=wrong').status_code)
                self.assertEqual(200,client.delete(url).status_code)
                self.assertEqual(404,client.delete(url).status_code)
    def test_service_denies_nonadmin(self):
        with self.assertRaises(PermissionError): self.service.delete(self.code,'project_manager')

    def test_delayed_index_job_does_not_restore_deleted_evidence(self):
        from prosight.ingestion.manager import IngestionManager
        document=self.document()
        self.service.delete(self.code,'admin')
        manager=IngestionManager.__new__(IngestionManager)
        manager.repository=self.repo
        manager.rag_store=Mock()
        manager._index_pdf('delayed-job',document)
        manager.rag_store.add_chunks.assert_not_called()
