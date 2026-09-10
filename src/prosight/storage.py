"""Private Supabase Storage client for approved PDF originals."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote

import httpx


class SupabaseStorage:
    """Upload immutable, checksum-addressed PDFs with a server-only key."""

    def __init__(self, url: str, secret_key: str, bucket: str = "prosight-pdfs"):
        if not url or not secret_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for PDF Storage")
        if not bucket or "/" in bucket:
            raise ValueError("SUPABASE_STORAGE_BUCKET must be a single bucket name")
        self.url = url.rstrip("/")
        self.secret_key = secret_key
        self.bucket = bucket
        self.client = httpx.Client(timeout=60)

    @property
    def headers(self) -> dict[str, str]:
        headers = {"apikey": self.secret_key}
        if self.secret_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.secret_key}"
        return headers

    @staticmethod
    def object_path(document: dict) -> str:
        return f"{document['project_code']}/{document['checksum']}.pdf"

    @staticmethod
    def _checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _object_url(self, route: str, bucket: str, object_path: str) -> str:
        encoded = quote(object_path, safe="/")
        return f"{self.url}/storage/v1/object/{route}{quote(bucket, safe='')}/{encoded}"

    def download(self, bucket: str, object_path: str) -> bytes:
        response = self.client.get(
            self._object_url("authenticated/", bucket, object_path), headers=self.headers
        )
        response.raise_for_status()
        return response.content

    def bucket_config(self) -> dict:
        response = self.client.get(
            f"{self.url}/storage/v1/bucket/{quote(self.bucket, safe='')}",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def upload_pdf(self, document: dict, source: Path) -> tuple[str, str]:
        data = source.read_bytes()
        if not data.startswith(b"%PDF-") or self._checksum(data) != document["checksum"]:
            raise ValueError("PDF content no longer matches its approved checksum")
        object_path = self.object_path(document)
        response = self.client.post(
            self._object_url("", self.bucket, object_path),
            headers={**self.headers, "Content-Type": "application/pdf", "x-upsert": "false"},
            content=data,
        )
        if response.status_code in {400, 409}:
            existing = self.download(self.bucket, object_path)
            if self._checksum(existing) != document["checksum"]:
                raise RuntimeError("Supabase Storage object conflicts with the approved PDF")
            return self.bucket, object_path
        response.raise_for_status()
        return self.bucket, object_path

    def delete(self, bucket: str, object_path: str) -> None:
        response = self.client.request(
            "DELETE",
            f"{self.url}/storage/v1/object/{quote(bucket, safe='')}",
            headers={**self.headers, "Content-Type": "application/json"},
            json={"prefixes": [object_path]},
        )
        response.raise_for_status()

    def close(self) -> None:
        self.client.close()
