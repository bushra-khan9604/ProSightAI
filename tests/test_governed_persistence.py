"""Database-shape tests for the governed application persistence adapter."""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock

from openpyxl import Workbook

from prosight.ingestion.governed_excel import (
    FieldSpec,
    OrganizationMapping,
    ReferenceCatalog,
    SheetMapping,
    checksum,
    validate_workbook,
)
from prosight.ingestion.persistence import (
    INSERT_MAPPING_PROFILE_SQL,
    INSERT_MAPPING_VERSION_SHEET_SQL,
    INSERT_MAPPING_VERSION_SQL,
    INSERT_STAGED_ROW_SQL,
    GovernedIngestionAdapter,
    MappingRecord,
    _persistence_records,
)


def cursor(*, one=None, all_rows=None):
    result = Mock()
    result.fetchone.return_value = one
    result.fetchall.return_value = [] if all_rows is None else all_rows
    return result


class GovernedPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.organization_id = str(uuid.uuid4())
        self.project_id = str(uuid.uuid4())
        self.actor_id = str(uuid.uuid4())
        self.profile_id = str(uuid.uuid4())
        self.version_id = str(uuid.uuid4())
        self.batch_id = str(uuid.uuid4())
        self.source_id = str(uuid.uuid4())
        self.run_id = str(uuid.uuid4())
        self.mapping = OrganizationMapping(
            self.organization_id,
            self.profile_id,
            self.version_id,
            1,
            (
                SheetMapping(
                    "risks",
                    "Risks",
                    {
                        "project_id": "Project",
                        "risk_number": "Risk",
                        "title": "Title",
                    },
                    {
                        "project_id": FieldSpec("uuid", True),
                        "risk_number": FieldSpec("text", True),
                        "title": FieldSpec("text", True),
                    },
                    ("project_id", "risk_number"),
                ),
                SheetMapping(
                    "daily_reports",
                    "Daily",
                    {
                        "project_id": "Project",
                        "report_date": "Date",
                        "shift_code": "Shift",
                        "work_completed": "Work",
                    },
                    {
                        "project_id": FieldSpec("uuid", True),
                        "report_date": FieldSpec("date", True),
                        "shift_code": FieldSpec("text", True),
                        "work_completed": FieldSpec("text", True),
                    },
                    ("project_id", "report_date", "shift_code"),
                ),
            ),
        )

    def workbook(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "multi.xlsx"
        book = Workbook()
        risks = book.active
        risks.title = "Risks"
        risks.append(["Project", "Risk", "Title"])
        risks.append([self.project_id, "R-1", "Delay"])
        daily = book.create_sheet("Daily")
        daily.append(["Project", "Date", "Shift", "Work"])
        daily.append([self.project_id, "2026-09-10", "day", "Excavation"])
        book.save(path)
        return path

    def test_mapping_sql_matches_current_tables_and_persists_each_sheet(self):
        self.assertNotIn("target_entity_type", INSERT_MAPPING_PROFILE_SQL)
        self.assertNotIn("business_key_columns", INSERT_MAPPING_VERSION_SQL)
        self.assertIn("ingestion.mapping_version_sheets", INSERT_MAPPING_VERSION_SHEET_SQL)
        self.assertIn("mapping_version_sheet_id", INSERT_STAGED_ROW_SQL)

        connection = MagicMock()
        connection.execute_native.side_effect = [
            cursor(one={"id": self.profile_id}),
            cursor(one={"id": self.version_id}),
            cursor(),
            cursor(),
        ]
        adapter = GovernedIngestionAdapter(Mock(return_value=connection))
        adapter.register_mapping(
            MappingRecord(self.mapping, "Project controls", "excel"),
            created_by=self.actor_id,
        )
        calls = connection.execute_native.call_args_list
        self.assertEqual(4, len(calls))
        sheet_calls = calls[2:]
        self.assertEqual(
            ["risks", "daily_reports"],
            [call.args[1]["target_entity_type"] for call in sheet_calls],
        )
        self.assertEqual(
            [
                ["project_id", "risk_number"],
                ["project_id", "report_date", "shift_code"],
            ],
            [call.args[1]["business_key_columns"] for call in sheet_calls],
        )

    def test_multi_sheet_rows_bind_their_immutable_mapping_sheet(self):
        path = self.workbook()
        preview = validate_workbook(
            path,
            self.mapping,
            ReferenceCatalog(
                frozenset({self.organization_id}),
                {self.project_id: self.organization_id},
            ),
            source_file_id=self.source_id,
            import_batch_id=self.batch_id,
        )
        sheets, columns, rows, cells, issues = _persistence_records(
            path, preview, self.mapping, self.project_id, self.run_id
        )
        self.assertTrue(preview.valid)
        self.assertEqual(2, len(sheets))
        self.assertEqual(2, len(rows))
        self.assertEqual(2, len({row["mapping_version_sheet_id"] for row in rows}))
        self.assertEqual({"risks", "daily_reports"}, {row["target_entity_type"] for row in rows})
        self.assertGreater(len(columns), 0)
        self.assertGreater(len(cells), 0)
        self.assertEqual([], issues)

    def test_approval_rederives_source_profile_version_checksum(self):
        expected_input = checksum({
            "source_checksum": "a" * 64,
            "mapping_profile_id": self.profile_id,
            "mapping_version_id": self.version_id,
            "mapping_version_no": 1,
            "profile_checksum": "b" * 64,
        })
        context = {
            "import_batch_id": self.batch_id,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "status": "awaiting_approval",
            "requester_user_id": str(uuid.uuid4()),
            "mapping_version_id": self.version_id,
            "input_profile_checksum": "c" * 64,
            "normalized_preview_checksum": "d" * 64,
            "validation_checksum": "e" * 64,
            "source_file_id": self.source_id,
            "source_checksum": "a" * 64,
            "mapping_profile_id": self.profile_id,
            "version_no": 1,
            "mapping_checksum": "b" * 64,
            "transformation_run_id": self.run_id,
            "run_status": "succeeded",
            "run_input_profile_checksum": expected_input,
            "has_errors": False,
        }
        connection = MagicMock()
        connection.execute_native.side_effect = [
            cursor(all_rows=[context]),
            cursor(one={"role": "admin"}),
        ]
        with self.assertRaisesRegex(ValueError, "source, mapping profile/version"):
            GovernedIngestionAdapter(Mock(return_value=connection)).decide(
                self.organization_id,
                self.batch_id,
                actor_id=self.actor_id,
                decision="approved",
            )
        self.assertEqual(2, connection.execute_native.call_count)

    def test_persistence_sql_never_writes_construction_or_legacy(self):
        sql = "\n".join(
            (
                INSERT_MAPPING_PROFILE_SQL,
                INSERT_MAPPING_VERSION_SQL,
                INSERT_MAPPING_VERSION_SHEET_SQL,
                INSERT_STAGED_ROW_SQL,
            )
        ).lower()
        self.assertNotIn("insert into construction.", sql)
        self.assertNotIn("prosight.", sql)


if __name__ == "__main__":
    unittest.main()
