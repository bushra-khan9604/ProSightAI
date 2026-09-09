"""Security regression tests; all Supabase responses are isolated HTTP fixtures."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from prosight.api import create_app
from prosight.repository import ProjectRepository, DEFAULT_DATA


class SupabaseAuthTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'PROSIGHT_AUTH_PROVIDER': 'supabase', 'PROSIGHT_AUTH_REQUIRED': 'false',
            'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_test',
            'PROSIGHT_AI_PROVIDER': 'local', 'OPENAI_API_KEY': '',
            'PROSIGHT_SEED_DEMO_USERS': 'false',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        repository = ProjectRepository(Path(self.temp.name) / 'auth.db')
        repository.initialize(DEFAULT_DATA)
        with patch('prosight.api.RAGStore', side_effect=RuntimeError('offline')):
            self.app = create_app(repository)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def response(self, role='planning_engineer', **extra):
        return httpx.Response(200, json={
            'id': 'test-user', 'email': 'test@example.test',
            'app_metadata': {'prosight_role': role}, **extra,
        })

    def test_private_routes_require_auth_even_with_legacy_opt_out(self):
        for path in ['/api/projects', '/api/query', '/api/uploads', '/api/approvals',
                     '/api/portfolio-imports/template', '/api/auth/me']:
            response = self.client.get(path)
            self.assertEqual(401, response.status_code, path)
            self.assertIn('no-store', response.headers['cache-control'])

    def test_config_public_and_local_password_login_disabled(self):
        self.assertEqual('supabase', self.client.get('/api/auth/config').json()['provider'])
        self.assertEqual(400, self.client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'Admin123!'}).status_code)

    def test_legacy_cookie_cannot_bypass_supabase(self):
        self.client.cookies.set('prosight_session', 'forged-cookie')
        self.assertEqual(401, self.client.get('/api/projects').status_code)

    def test_online_validation_and_identity(self):
        with patch('prosight.supabase_auth.httpx.AsyncClient.get', new=AsyncMock(return_value=self.response())) as get:
            response = self.client.get('/api/auth/me', headers={'Authorization': 'Bearer test-token'})
            self.assertEqual(200, response.status_code)
            self.assertEqual('planning_engineer', response.json()['role'])
            self.assertEqual('Bearer test-token', get.call_args.kwargs['headers']['Authorization'])
            self.assertEqual('https://example.supabase.co/auth/v1/user', get.call_args.args[0])

    def test_query_role_spoofing_and_missing_role_use_verified_identity(self):
        with patch('prosight.supabase_auth.httpx.AsyncClient.get', new=AsyncMock(return_value=self.response())):
            for query in ['', '?role=admin', '?role=admin&role=admin']:
                response = self.client.get('/api/approvals' + query, headers={'Authorization': 'Bearer test-token'})
                self.assertEqual(403, response.status_code)
            self.assertEqual(200, self.client.get('/api/projects', headers={'Authorization': 'Bearer test-token'}).status_code)

    def test_metadata_cannot_grant_access(self):
        responses = [self.response(None, user_metadata={'prosight_role': 'admin'}),
                     self.response('admin', is_anonymous=True), self.response('unknown')]
        for response in responses:
            with patch('prosight.supabase_auth.httpx.AsyncClient.get', new=AsyncMock(return_value=response)):
                self.assertIn(self.client.get('/api/projects', headers={'Authorization': 'Bearer test-token'}).status_code, [401, 403])

    def test_invalid_token_and_upstream_failure_fail_closed(self):
        for status, expected in [(401, 401), (403, 401), (429, 503), (500, 503)]:
            with patch('prosight.supabase_auth.httpx.AsyncClient.get', new=AsyncMock(return_value=httpx.Response(status))):
                self.assertEqual(expected, self.client.get('/api/projects', headers={'Authorization': 'Bearer bad'}).status_code)
        with patch('prosight.supabase_auth.httpx.AsyncClient.get', new=AsyncMock(side_effect=httpx.ConnectError('offline'))):
            self.assertEqual(503, self.client.get('/api/projects', headers={'Authorization': 'Bearer bad'}).status_code)

    def test_admin_can_reach_approval_queue(self):
        with patch('prosight.supabase_auth.httpx.AsyncClient.get', new=AsyncMock(return_value=self.response('admin'))):
            self.assertEqual(200, self.client.get('/api/approvals?role=planning_engineer', headers={'Authorization': 'Bearer test-token'}).status_code)


if __name__ == '__main__':
    unittest.main()
