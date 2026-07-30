"""Tests for safe, bounded Writer Agent table output."""

import unittest

from prosight.agents.writer import WriterAgent, create_table
from prosight.contracts import DatabaseEvidence, WriterInput


class WriterTableTests(unittest.TestCase):
    def test_validates_shape_and_column_limits(self) -> None:
        with self.assertRaises(ValueError):
            create_table(["Only"], [["value"]])
        with self.assertRaises(ValueError):
            create_table(["A", "B"], [["value"]])
        with self.assertRaises(ValueError):
            create_table(["A", "B"], [], omitted_count=-1)

    def test_escapes_structure_and_missing_values(self) -> None:
        output = create_table(
            ["Name", "Details"],
            [["A|B", "line one\n**bold** <tag>"], [None, "https://example.test/a_b"]],
        )
        self.assertIn(r"A\|B", output)
        self.assertIn(r"\*\*bold\*\*", output)
        self.assertIn(r"\<tag\>", output)
        self.assertIn("—", output)
        self.assertEqual(4, len(output.splitlines()))

    def test_truncates_at_twenty_and_reports_all_omissions(self) -> None:
        output = create_table(
            ["Code", "Name"],
            [[index, f"Project {index}"] for index in range(25)],
            omitted_count=3,
        )
        self.assertIn("8 additional records were omitted.", output)
        self.assertIn("| 19 | Project 19 |", output)
        self.assertNotIn("| 20 | Project 20 |", output)

    def test_local_writer_uses_table_for_structured_records(self) -> None:
        answer = WriterAgent().fallback(WriterInput(
            query="Show projects",
            database=DatabaseEvidence(
                summary="Two projects found.",
                records=[
                    {"code": "P-1", "name": "Alpha", "status": "Active"},
                    {"code": "P-2", "name": "Beta", "status": "Complete"},
                ],
            ),
        ))
        self.assertIn("| Code | Name | Status |", answer.answer)
        self.assertIn("| P-1 | Alpha | Active |", answer.answer)


if __name__ == "__main__":
    unittest.main()
