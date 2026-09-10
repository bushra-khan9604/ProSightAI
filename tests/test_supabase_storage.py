"""Supabase Storage boundary tests without network access."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from prosight.storage import SupabaseStorage


class SupabaseStorageTests(unittest.TestCase):
    def test_modern_secret_key_is_not_sent_as_a_bearer_token(self):
        storage = SupabaseStorage("https://example.supabase.co", "sb_secret_example")
        self.addCleanup(storage.close)
        self.assertEqual({"apikey": "sb_secret_example"}, storage.headers)

    def test_upload_is_immutable_and_checksum_addressed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            path.write_bytes(b"%PDF-test")
            document = {
                "project_code": "P1", "checksum": SupabaseStorage._checksum(path.read_bytes())
            }
            storage = SupabaseStorage("https://example.supabase.co", "sb_secret_example")
            response = Mock(status_code=200)
            storage.client = Mock()
            storage.client.post.return_value = response
            bucket, object_path = storage.upload_pdf(document, path)
            self.assertEqual("prosight-pdfs", bucket)
            self.assertEqual(f"P1/{document['checksum']}.pdf", object_path)
            self.assertEqual("false", storage.client.post.call_args.kwargs["headers"]["x-upsert"])
            response.raise_for_status.assert_called_once()

    def test_existing_object_must_match_approved_checksum(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            path.write_bytes(b"%PDF-test")
            document = {
                "project_code": "P1", "checksum": SupabaseStorage._checksum(path.read_bytes())
            }
            storage = SupabaseStorage("https://example.supabase.co", "sb_secret_example")
            storage.client = Mock()
            storage.client.post.return_value = Mock(status_code=400)
            storage.download = Mock(return_value=path.read_bytes())
            self.assertEqual(
                ("prosight-pdfs", f"P1/{document['checksum']}.pdf"),
                storage.upload_pdf(document, path),
            )


if __name__ == "__main__":
    unittest.main()
