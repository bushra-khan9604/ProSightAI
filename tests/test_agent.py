import tempfile
import unittest
from pathlib import Path

from prosight.agent import ProSightAgent
from prosight.repository import DEFAULT_DATA, ProjectRepository


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = ProjectRepository(Path(self.temp.name) / "test.db")
        self.repo.initialize(DEFAULT_DATA)
        self.agent = ProSightAgent(self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def test_lists_active_projects(self):
        result = self.agent.ask_local("List ongoing projects", "project_manager")
        self.assertIn("Marina Heights", result["answer"])
        self.assertIn("Al Noor", result["answer"])
        self.assertNotIn("Creek Logistics", result["answer"])

    def test_calculates_delay_and_variance(self):
        project = self.repo.find_project("PRJ-2024-001", "project_manager")
        self.assertEqual(90, project["delay_days"])
        self.assertEqual(-3.5, project["variance_pct"])

    def test_employee_contact_data_is_restricted(self):
        result = self.agent.ask_local(
            "Who is the manager for Marina Heights Residential Tower?", "employee"
        )
        self.assertIn("restricted", result["answer"])
        self.assertNotIn("+971", result["answer"])

    def test_manager_sees_contact_data(self):
        result = self.agent.ask_local(
            "Who is the manager for Marina Heights Residential Tower?", "project_manager"
        )
        self.assertIn("omar.rahman@example.com", result["answer"])

    def test_portfolio_summary(self):
        result = self.agent.ask_local("Give me a portfolio summary", "executive")
        self.assertIn("4 projects", result["answer"])
        self.assertIn("2 active", result["answer"])

    def test_returns_only_requested_contact_role(self):
        result = self.agent.ask_local(
            "Who is the planning engineer for Marina Heights?", "project_manager"
        )
        self.assertIn("Daniel Joseph", result["answer"])
        self.assertNotIn("Omar Rahman", result["answer"])

    def test_finds_most_delayed_active_project(self):
        result = self.agent.ask_local(
            "Which active project has the highest delay?", "executive"
        )
        self.assertIn("Marina Heights", result["answer"])
        self.assertIn("90 days", result["answer"])

    def test_lists_projects_requiring_attention(self):
        result = self.agent.ask_local("Which projects are behind plan?", "executive")
        self.assertIn("PRJ-2024-001", result["answer"])
        self.assertNotIn("PRJ-2025-004", result["answer"])

    def test_fuzzy_project_name(self):
        result = self.agent.ask_local("Show manpower for Al Noor hospital", "project_manager")
        self.assertIn("Total listed manpower", result["answer"])
        self.assertIn("282", result["answer"])

if __name__ == "__main__":
    unittest.main()
