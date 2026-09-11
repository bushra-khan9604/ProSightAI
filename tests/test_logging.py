import json
import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from prosight.agent import ProSightAgent
from prosight.api import create_app
from prosight.observability import RequestTrace, configure_logging, sanitize
from prosight.repository import DEFAULT_DATA, ProjectRepository


class LoggingTests(unittest.TestCase):
    @staticmethod
    def close_handlers(logger):
        """Release Windows file handles before temporary directories are removed."""
        for handler in list(logger.handlers):
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    def test_sanitize_redacts_private_values_and_bounds_preview(self):
        value = (
            "email user@example.com mobile +971-50-555-0101 "
            "Authorization: Bearer secret-token and more diagnostic content"
        )
        preview = sanitize(value, limit=100)
        self.assertNotIn("user@example.com", preview)
        self.assertNotIn("+971-50-555-0101", preview)
        self.assertNotIn("secret-token", preview)
        self.assertLessEqual(len(preview), 101)

    def test_api_emits_ordered_query_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "PROSIGHT_LOG_DIR": temp_dir,
                "PROSIGHT_LOG_LEVEL": "INFO",
                "PROSIGHT_AI_PROVIDER": "local",
            }
            with patch.dict("os.environ", env, clear=False):
                logger = configure_logging(force=True)
                repository = ProjectRepository(Path(temp_dir) / "api-test.db")
                repository.initialize(DEFAULT_DATA)
                client = TestClient(create_app(repository))
                response = client.post("/api/query", json={
                    "query": "Who is the manager for Marina Heights?",
                    "project_code": "PRJ-2024-001",
                })
                self.assertEqual(200, response.status_code)
                payload = response.json()
                for handler in logger.handlers:
                    handler.flush()
                records = [
                    json.loads(line)
                    for line in (Path(temp_dir) / "prosight.log").read_text(encoding="utf-8").splitlines()
                ]
                request_records = [
                    record for record in records
                    if record.get("request_id") == payload["request_id"]
                ]
                events = [record["event"] for record in request_records]
                expected = [
                    "query_received", "query_validated", "orchestration_planned",
                    "database_query_completed", "evidence_collected",
                    "provider_selected", "response_generated", "response_sent",
                ]
                self.assertEqual(expected, events)
                self.assertIn("duration_ms", payload)
                serialized = json.dumps(request_records)
                self.assertNotIn("omar.rahman@example.com", serialized)
                self.assertNotIn("+971-50-555-0101", serialized)
                self.close_handlers(logger)

    def test_logging_failure_does_not_block_answer(self):
        class ExplodingLogger:
            def log(self, *args, **kwargs):
                raise RuntimeError("logging unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ProjectRepository(Path(temp_dir) / "test.db")
            repository.initialize(DEFAULT_DATA)
            trace = RequestTrace(logger=ExplodingLogger())
            result = ProSightAgent(repository).ask(
                "List active projects", "project_manager", trace
            )
        self.assertEqual("local", result["mode"])

    def test_rotating_file_handler_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "PROSIGHT_LOG_DIR": temp_dir,
                "PROSIGHT_LOG_LEVEL": "INFO",
                "PROSIGHT_LOG_MAX_BYTES": "300",
                "PROSIGHT_LOG_BACKUP_COUNT": "2",
            }
            with patch.dict("os.environ", env, clear=False):
                logger = configure_logging(force=True)
                # Rotation behavior only needs the file handler; silence console noise.
                for handler in list(logger.handlers):
                    if type(handler) is logging.StreamHandler:
                        handler.close()
                        logger.removeHandler(handler)
                trace = RequestTrace(logger=logger)
                for index in range(30):
                    trace.event("rotation_test", sequence=index, text="x" * 80)
                for handler in logger.handlers:
                    handler.flush()
                self.assertTrue((Path(temp_dir) / "prosight.log.1").exists())
                self.close_handlers(logger)


if __name__ == "__main__":
    unittest.main()
