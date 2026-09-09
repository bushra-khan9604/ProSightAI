import uuid
import tempfile
from pathlib import Path
from contextlib import closing
from unittest import TestCase
from unittest.mock import Mock
from prosight.repository import ProjectRepository,DEFAULT_DATA
from prosight.agents.attachment_update import AttachmentUpdateAgent
from prosight.agents.project_creation import ProjectCreationAgent,DraftFields,Extraction

class ProjectConversationTests(TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
  self.repo=ProjectRepository(root/'db.sqlite');self.repo.initialize(DEFAULT_DATA)
  self.admin={'id':'a','role':'admin'};self.pm={'id':'p','role':'project_manager'}
  self.extractor=Mock(return_value=Extraction(fields=DraftFields(name='Oasis School'),clarification='Who is the client?'))
  self.agent=ProjectCreationAgent(AttachmentUpdateAgent(self.repo,None,root/'uploads'),self.extractor)
  self.fields=dict(code='NL-TEST-001',name='Oasis School',status='future',client='Horizon Education',location='Dubai',contract_value_usd=5000000,planned_start='2027-03-01',planned_finish='2028-06-30',reporting_date='2026-09-08',baseline_progress=0,revised_progress=0,actual_progress=0,revised_finish=None)
 def start(self,user=None):return self.agent.start(str(uuid.uuid4()),user or self.pm)
 def complete(self,user=None):
  user=user or self.pm;op=self.start(user);return self.agent.edit(op['id'],user,op['revision'],self.fields)
 def test_description_collects_missing_and_never_writes_project(self):
  op=self.start();op=self.agent.edit(op['id'],self.pm,op['revision'],message='Create Oasis School',allow_ai=True)
  self.assertEqual('Oasis School',op['fields']['name']);self.assertIn('client',op['missing']);self.assertFalse(op['can_confirm'])
  self.assertIsNone(self.repo.find_project(self.fields['code'],'admin'));self.extractor.assert_called_once()
 def test_external_processing_requires_consent(self):
  op=self.start()
  with self.assertRaises(ValueError):self.agent.edit(op['id'],self.pm,op['revision'],message='Create Oasis School')
  self.extractor.assert_not_called()
 def test_pm_confirmation_then_admin_approval_and_retry(self):
  op=self.complete();self.assertTrue(op['can_confirm'])
  with self.assertRaises(ValueError):self.agent.decide(op['id'],self.admin,op['revision'],'approve')
  op=self.agent.decide(op['id'],self.pm,op['revision'],'confirm');self.assertEqual('pending',op['status'])
  self.assertIsNone(self.repo.find_project(self.fields['code'],'admin'))
  with self.assertRaises(PermissionError):self.agent.decide(op['id'],self.pm,op['revision'],'approve')
  op=self.agent.decide(op['id'],self.admin,op['revision'],'approve');self.assertEqual('completed',op['status'])
  self.agent.decide(op['id'],self.admin,op['revision'],'approve')
  with closing(self.repo.connect()) as db:self.assertEqual(1,db.execute('SELECT count(*) FROM projects WHERE code=?',(self.fields['code'],)).fetchone()[0])
 def test_admin_confirmation_creates_without_separate_approval(self):
  op=self.complete(self.admin);self.assertEqual('completed',self.agent.decide(op['id'],self.admin,op['revision'],'confirm')['status'])
 def test_ownership_and_role_enforcement(self):
  op=self.start()
  with self.assertRaises(PermissionError):self.agent.get(op['id'],{'id':'p2','role':'project_manager'})
  with self.assertRaises(PermissionError):self.agent.edit(op['id'],self.admin,op['revision'],self.fields)
  with self.assertRaises(PermissionError):self.agent.start(str(uuid.uuid4()),{'id':'e','role':'planning_engineer'})
 def test_stale_preview_and_invalid_dates_are_blocked(self):
  op=self.complete();old=op['revision'];op=self.agent.edit(op['id'],self.pm,old,{'planned_finish':'2020-01-01'})
  self.assertTrue(op['issues']);self.assertFalse(op['can_confirm'])
  with self.assertRaises(ValueError):self.agent.decide(op['id'],self.pm,old,'confirm')
  with self.assertRaises(ValueError):self.agent.decide(op['id'],self.pm,op['revision'],'confirm')
 def test_duplicate_code_does_not_overwrite(self):
  existing=self.repo.list_projects(user_role='admin')[0];op=self.complete(self.admin)
  op=self.agent.edit(op['id'],self.admin,op['revision'],{'code':existing['code']})
  with self.assertRaisesRegex(ValueError,'already exists'):self.agent.decide(op['id'],self.admin,op['revision'],'confirm')
  self.assertEqual(existing['name'],self.repo.find_project(existing['code'],'admin')['name'])
 def test_provider_failure_preserves_editable_draft(self):
  self.extractor.side_effect=RuntimeError('provider error');op=self.start()
  op=self.agent.edit(op['id'],self.pm,op['revision'],message='Create a school',allow_ai=True)
  self.assertTrue(op['editable']);self.assertIn('unavailable',op['notice']);self.assertEqual(3,len(op['messages']))
 def test_creation_request_is_idempotent_and_restorable(self):
  identifier=str(uuid.uuid4());one=self.agent.start(identifier,self.pm);two=self.agent.start(identifier,self.pm)
  self.assertEqual(one['revision'],two['revision']);self.assertEqual(1,len(self.agent.list(self.pm)))
