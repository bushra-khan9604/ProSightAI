"""Default project data and additive seed-enrichment tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from prosight.repository import (
    DEFAULT_DATA,
    DEFAULT_PROJECT_CODES,
    DEFAULT_PROJECT_ENRICHMENT,
    ProjectRepository,
)


class DefaultProjectEnrichmentTests(unittest.TestCase):
    """Verify rich fresh seeds and safe enrichment of an existing database."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temporary.name) / "projects.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_fresh_default_projects_have_rich_project_details(self) -> None:
        self.repository.initialize(DEFAULT_DATA)
        projects = {
            project["code"]: project
            for project in self.repository.list_projects(user_role="admin")
            if project["code"] in DEFAULT_PROJECT_CODES
        }

        self.assertEqual(DEFAULT_PROJECT_CODES, frozenset(projects))
        for project in projects.values():
            with self.subTest(project=project["code"]):
                self.assertGreaterEqual(len(project["contacts"]), 5)
                self.assertGreaterEqual(len(project["activities"]), 4)
                self.assertGreaterEqual(len(project["equipment"]), 5)
                self.assertGreaterEqual(len(project["milestones"]), 5)

        creek = projects["PRJ-2022-009"]
        self.assertEqual("completed", creek["status"])
        self.assertEqual(100.0, creek["actual_progress"])
        self.assertEqual(2_194_300, creek["total_manhours"])
        self.assertEqual(5, len(creek["manpower"]))
        self.assertTrue(all(item["status"] == "complete" for item in creek["milestones"]))
        self.assertIn("Practical completion", {item["name"] for item in creek["milestones"]})
        self.assertIn("Final account closeout", creek["activities"])
        self.assertNotIn("active construction", " ".join(creek["activities"]).casefold())

    def test_existing_database_enrichment_is_additive_and_idempotent(self) -> None:
        self.repository.initialize(DEFAULT_DATA)
        with closing(self.repository.connect()) as db:
            creek_row = db.execute(
                "SELECT payload FROM projects WHERE code='PRJ-2022-009'"
            ).fetchone()
            creek = json.loads(creek_row["payload"])
            creek["client"] = "Edited Creek Client"
            creek["contract_value_usd"] = 47_200_123
            creek["contacts"] = creek["contacts"][:2] + [
                {
                    "name": "Custom Closeout Contact",
                    "project_role": "Archive Custodian",
                    "email": "custom@example.com",
                    "mobile": "+971-50-555-0399",
                }
            ]
            creek["activities"] = creek["activities"][:1] + ["Custom retained activity"]
            creek["manpower"] = creek["manpower"][:1]
            creek["equipment"] = creek["equipment"][:1]
            creek["milestones"] = creek["milestones"][-2:]
            db.execute(
                """UPDATE projects SET client=?, contract_value_usd=?, payload=?
                   WHERE code=?""",
                (
                    creek["client"],
                    creek["contract_value_usd"],
                    json.dumps(creek),
                    creek["code"],
                ),
            )

            user_project = dict(creek)
            user_project.update(
                {
                    "code": "PRJ-USER-001",
                    "name": "User Created Project",
                    "contacts": [],
                    "activities": ["User activity"],
                    "manpower": [],
                    "equipment": [],
                    "milestones": [],
                }
            )
            db.execute(
                """INSERT INTO projects VALUES
                   (:code,:name,:status,:client,:location,:contract_value_usd,
                    :planned_start,:planned_finish,:revised_finish,:reporting_date,
                    :baseline_progress,:revised_progress,:actual_progress,:payload)""",
                {**user_project, "payload": json.dumps(user_project)},
            )
            db.commit()

        self.repository.ensure_schema()
        first = self.repository.find_project("PRJ-2022-009", user_role="admin")
        self.repository.ensure_schema()
        second = self.repository.find_project("PRJ-2022-009", user_role="admin")

        self.assertEqual(first, second)
        self.assertEqual("Edited Creek Client", second["client"])
        self.assertEqual(47_200_123, second["contract_value_usd"])
        self.assertIn("Custom retained activity", second["activities"])
        self.assertIn("Custom Closeout Contact", {item["name"] for item in second["contacts"]})
        self.assertGreaterEqual(len(second["contacts"]), 6)
        self.assertGreaterEqual(len(second["activities"]), 5)
        self.assertEqual(5, len(second["manpower"]))
        self.assertEqual(5, len(second["equipment"]))
        self.assertEqual(5, len(second["milestones"]))

        user_after = self.repository.find_project("PRJ-USER-001", user_role="admin")
        self.assertEqual(["User activity"], user_after["activities"])
        self.assertEqual([], user_after["contacts"])
        with closing(self.repository.connect()) as db:
            migrations = db.execute(
                "SELECT migration_key FROM seed_migrations"
            ).fetchall()
        self.assertEqual([DEFAULT_PROJECT_ENRICHMENT], [row["migration_key"] for row in migrations])


if __name__ == "__main__":
    unittest.main()
