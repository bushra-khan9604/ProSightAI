import json
import os
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from unittest import TestCase
import test_project_register as fixtures
from prosight.ingestion.project_mapping import load_mapping, ProjectMapping, fingerprint
from prosight.ingestion.project_register import parse_project_register


class ProjectMappingTests(TestCase):
    setUp = fixtures.ProjectRegisterTests.setUp
    workbook = fixtures.ProjectRegisterTests.workbook
    def profile(self, **changes):
        data=load_mapping().model_dump()
        data.update(changes)
        return ProjectMapping.model_validate(data)

    def test_alternate_labels_and_status_values(self):
        path=self.workbook([['ALT-001','Alternate Project','In progress']],['Project #','Project Title','Status'])
        row=parse_project_register(path)[0]
        self.assertEqual('ALT-001',row['fields']['code'])
        self.assertEqual('active',row['fields']['status'])
        self.assertEqual('header alias',row['source']['mapping']['code']['method'])

    def test_unlabeled_code_uses_values_and_records_inference(self):
        path=self.workbook([['ALT-001','Alternate Project'],['ALT-002','Another Project']],['','Project name'])
        rows=parse_project_register(path)
        self.assertEqual('ALT-001',rows[0]['fields']['code'])
        self.assertIn('inferred',rows[0]['source']['mapping']['code']['method'])

    def test_ambiguous_unlabeled_columns_are_not_guessed(self):
        path=self.workbook([['ALT-001','Alternate Project','CL-001']],['','Project name',''])
        row=parse_project_register(path)[0]
        self.assertNotIn('code',row['fields'])
        self.assertTrue(any('ambiguous' in warning for warning in row['warnings']))

    def test_headerless_sheet_with_configured_columns(self):
        path=self.root/'no-headers.xlsx';book=Workbook();book.active.append(['HDR-001','Headerless Project']);book.save(path);book.close()
        data=load_mapping().model_dump();data.update(header_row=None,data_start_row=1)
        data['fields']['code']['column']=1;data['fields']['name']['column']=2
        row=parse_project_register(path,ProjectMapping.model_validate(data))[0]
        self.assertEqual('Headerless Project',row['fields']['name'])
        self.assertEqual('configured column',row['source']['mapping']['name']['method'])
        self.assertEqual('HDR-001',row['source']['values']['Column A'])

    def test_configured_date_format_and_explicit_currency_rate(self):
        path=self.workbook([['ALT-001','Alternate Project','31/12/2027',100]],['code','name','planned_finish','Signed value AED'])
        data=load_mapping().model_dump();data['date_format']='day_first'
        data['fields']['contract_value_usd'].update(aliases=['Signed value AED'],source_currency='AED',usd_rate=0.25)
        row=parse_project_register(path,ProjectMapping.model_validate(data))[0]
        self.assertEqual(25,row['fields']['contract_value_usd'])
        self.assertEqual('2027-12-31',row['fields']['planned_finish'])
        self.assertEqual(100,row['source']['values']['Signed value AED'])

    def test_currency_conflict_is_unresolved(self):
        path=self.workbook([['ALT-001','Alternate Project',100]],['code','name','Signed value AED'])
        data=load_mapping().model_dump();data['fields']['contract_value_usd']['aliases']=['Signed value AED']
        row=parse_project_register(path,ProjectMapping.model_validate(data))[0]
        self.assertNotIn('contract_value_usd',row['fields'])
        self.assertTrue(any('conflicts' in warning for warning in row['warnings']))

    def test_profile_rejects_unknown_fields_code_and_conflicting_aliases(self):
        data=load_mapping().model_dump();data['fields']['execute_sql']={'aliases':['SQL']}
        with self.assertRaises(ValueError):ProjectMapping.model_validate(data)
        data=load_mapping().model_dump();data['fields']['name']['aliases']=['code']
        with self.assertRaises(ValueError):ProjectMapping.model_validate(data)
        data=load_mapping().model_dump();data['python']='print(1)'
        with self.assertRaises(ValueError):ProjectMapping.model_validate(data)

    def test_custom_profile_is_used_by_upload_and_snapshot_is_immutable(self):
        import uuid
        path=self.workbook([['ALT-001','Alternate Project']],['Our key','Our title'])
        data=load_mapping().model_dump();data['fields']['code']['aliases']=['Our key'];data['fields']['name']['aliases']=['Our title']
        profile_path=self.root/'custom.json';profile_path.write_text(json.dumps(data),encoding='utf-8')
        batch=str(uuid.uuid4())
        with patch.dict(os.environ,{'PROSIGHT_PROJECT_MAPPING_PATH':str(profile_path)}):
            item=self.agent.import_workbook(path,path.name,batch,self.pm)['items'][0]
            self.assertEqual('ALT-001',item['fields']['code'])
            original=item['source']['mapping_fingerprint']
            data['name']='Revised profile';profile_path.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError):self.agent.import_workbook(path,path.name,batch,self.pm)
            self.assertEqual(original,self.agent.get(item['id'],self.pm)['source']['mapping_fingerprint'])

    def test_invalid_profile_fails_instead_of_silently_using_defaults(self):
        path=self.root/'invalid.json';path.write_text('{"unknown":true}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Invalid project mapping profile'):load_mapping(path)
