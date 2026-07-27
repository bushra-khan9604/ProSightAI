"""End-to-end behavior matrix for the deterministic local test provider.

These tests deliberately force ``local`` mode. They verify the Project Insights
Agent without making billable OpenAI calls.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prosight.agent import ProSightAgent
from prosight.repository import ProjectRepository


class ProjectInsightsQueryScenarioTests(unittest.TestCase):
    """Exercise representative questions used by construction stakeholders."""

    @classmethod
    def setUpClass(cls) -> None:
        data_path = Path(__file__).parents[1] / "data" / "projects.json"
        cls._temp_directory = tempfile.TemporaryDirectory()
        database_path = Path(cls._temp_directory.name) / "prosight-test.db"
        repository = ProjectRepository(database_path)
        repository.initialize(data_path)
        cls.agent = ProSightAgent(repository)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp_directory.cleanup()

    def test_twenty_representative_queries_use_local_provider(self) -> None:
        """Validate common portfolio, project, progress, and contact questions."""

        scenarios = [
            ("List active projects", "Marina Heights"),
            ("Show completed projects", "Creek Logistics"),
            ("What future projects do we have?", "Green Metro"),
            ("Give me a portfolio summary", "4 projects total"),
            ("Which active project has the highest delay?", "90 days"),
            ("Which projects are behind plan?", "PRJ-2024-001"),
            ("Who is the planning engineer for Marina Heights?", "Daniel Joseph"),
            ("Who is the project manager for Al Noor Hospital?", "Aisha Karim"),
            ("Show manpower details for Al Noor Hospital", "Total listed manpower: 282"),
            ("What equipment is deployed at Marina Heights?", "Tower cranes"),
            ("What are the current activities at Marina Heights?", "Level 34 structural slab"),
            ("Show milestones for Creek Logistics Hub", "Practical completion"),
            ("How many man-hours were used on Creek Logistics Hub?", "2,194,300"),
            ("What is the progress of PRJ-2024-001?", "actual 68.5%"),
            ("What is the contract value of Al Noor Hospital?", "$126,000,000"),
            ("Compare the active projects", "Project comparison"),
            ("How many projects are active?", "2 active"),
            ("Who is the site contact for Marina Heights?", "Imran Siddiqui"),
            ("Who is the client contact for Al Noor Hospital?", "Dr. Huda Salem"),
            ("What is the revised finish date for Marina Heights?", "2027-02-28"),
        ]

        with patch.dict("os.environ", {"PROSIGHT_AI_PROVIDER": "local"}, clear=False):
            for query, expected_text in scenarios:
                with self.subTest(query=query):
                    response = self.agent.ask(query, user_role="project_manager")
                    self.assertEqual(response["mode"], "local")
                    self.assertIn(expected_text, response["answer"])


if __name__ == "__main__":
    unittest.main()
