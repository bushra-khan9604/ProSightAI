"""Small synchronous Supabase Data API, RPC, Functions, and Storage client."""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from contextvars import ContextVar
from typing import Any

from .config import get_settings


current_access_token: ContextVar[str | None] = ContextVar("prosight_access_token", default=None)


class SupabaseError(RuntimeError):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class SupabaseGateway:
    """Issue authenticated calls without exposing server credentials to callers."""

    def __init__(self, service: bool = False):
        settings = get_settings()
        self.url = settings.supabase_url.rstrip("/")
        self.publishable_key = settings.supabase_publishable_key
        self.service_key = settings.supabase_service_role_key
        self.service = service
        if not self.url or not self.publishable_key:
            raise RuntimeError("Supabase is not configured")
        if service and not self.service_key:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for server operations")

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        key = self.service_key if self.service else self.publishable_key
        token = self.service_key if self.service else current_access_token.get()
        headers = {"apikey": key, "Authorization": f"Bearer {token or key}"}
        headers.update(extra or {})
        return headers

    def request(
        self, method: str, path: str, payload: Any = None,
        *, prefer: str | None = None, headers: dict[str, str] | None = None,
    ) -> Any:
        body = None if payload is None else json.dumps(payload, default=str).encode("utf-8")
        extra = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
        if prefer:
            extra["Prefer"] = prefer
        request = urllib.request.Request(
            f"{self.url}{path}", data=body, method=method, headers=self._headers(extra)
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("message") or json.loads(raw).get("error") or raw
            except ValueError:
                detail = raw or error.reason
            raise SupabaseError(str(detail), error.code) from error
        except OSError as error:
            raise SupabaseError("Supabase is unavailable", 503) from error

    @staticmethod
    def query(**params: Any) -> str:
        return urllib.parse.urlencode({key: value for key, value in params.items() if value is not None}, safe="(),.*:")

    def select(self, table: str, *, select: str = "*", **filters: Any) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": select}
        params.update(filters)
        return self.request("GET", f"/rest/v1/{table}?{self.query(**params)}") or []

    def count(self, table: str) -> int:
        """Return an exact table count without the Data API row limit."""
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{table}?select=*",
            headers=self._headers({
                "Accept": "application/json", "Prefer": "count=exact", "Range": "0-0",
            }),
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                total = (response.headers.get("Content-Range") or "*/0").rsplit("/", 1)[-1]
                return int(total)
        except (urllib.error.HTTPError, OSError, ValueError) as error:
            if isinstance(error, urllib.error.HTTPError):
                detail = error.read().decode("utf-8", errors="replace")
                raise SupabaseError(detail or "Count request failed", error.code) from error
            raise SupabaseError("Supabase count request failed", 503) from error

    def insert(self, table: str, payload: Any, *, upsert: bool = False) -> list[dict[str, Any]]:
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        return self.request("POST", f"/rest/v1/{table}", payload, prefer=prefer) or []

    def update(
        self, table: str, payload: dict[str, Any], *, returning: bool = True, **filters: Any
    ) -> list[dict[str, Any]]:
        return self.request(
            "PATCH", f"/rest/v1/{table}?{self.query(**filters)}", payload,
            prefer="return=representation" if returning else "return=minimal",
        ) or []

    def delete(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        return self.request(
            "DELETE", f"/rest/v1/{table}?{self.query(**filters)}",
            prefer="return=representation",
        ) or []

    def rpc(self, function: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", f"/rest/v1/rpc/{function}", payload)

    def invoke(self, function: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", f"/functions/v1/{function}", payload)

    def upload(self, bucket: str, key: str, content: bytes, content_type: str | None = None,
               *, upsert: bool = False) -> None:
        mime = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
        request = urllib.request.Request(
            f"{self.url}/storage/v1/object/{bucket}/{urllib.parse.quote(key, safe='/')}",
            data=content,
            method="POST",
            headers=self._headers({"Content-Type": mime, "x-upsert": str(upsert).lower()}),
        )
        try:
            with urllib.request.urlopen(request, timeout=120):
                return
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise SupabaseError(detail or "Storage upload failed", error.code) from error

    def remove_objects(self, bucket: str, keys: list[str]) -> None:
        self.request("DELETE", f"/storage/v1/object/{bucket}", {"prefixes": keys})

    def download(self, bucket: str, key: str) -> bytes:
        request = urllib.request.Request(
            f"{self.url}/storage/v1/object/{bucket}/{urllib.parse.quote(key, safe='/')}",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise SupabaseError(detail or "Storage download failed", error.code) from error
