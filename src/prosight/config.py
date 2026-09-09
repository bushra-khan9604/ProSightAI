"""Application configuration loaded from environment variables and `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ROOT / ".env"
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    """Load simple KEY=VALUE entries without overwriting process variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    """Typed runtime settings for OpenAI and deterministic local test mode."""

    ai_provider: str
    openai_api_key: str
    openai_model: str
    orchestrator_reasoning: ReasoningEffort
    writer_reasoning: ReasoningEffort
    embedding_model: str
    auth_required: bool
    auth_cookie_name: str
    auth_cookie_secure: bool
    auth_session_ttl_seconds: int
    database_backend: str = "sqlite"
    database_url: str = ""
    auth_provider: str = "local"
    supabase_url: str = ""
    supabase_publishable_key: str = ""


def _reasoning_effort(name: str, default: ReasoningEffort) -> ReasoningEffort:
    """Return a validated reasoning effort from one environment setting."""
    value = os.environ.get(name, default).strip().lower()
    if value not in REASONING_EFFORTS:
        supported = ", ".join(sorted(REASONING_EFFORTS))
        raise ValueError(f"{name} must be one of: {supported}")
    return value  # type: ignore[return-value]


def get_settings() -> Settings:
    """Load `.env` and return the latest process-level configuration."""
    load_env_file()
    auth_provider = os.environ.get("PROSIGHT_AUTH_PROVIDER", "local").strip().lower()
    if auth_provider not in {"local", "supabase"}:
        raise ValueError("PROSIGHT_AUTH_PROVIDER must be local or supabase")
    database_url = os.environ.get("PROSIGHT_DATABASE_URL", "").strip()
    database_backend = os.environ.get("PROSIGHT_DATABASE_BACKEND", "postgres" if database_url else "sqlite").lower()
    if database_backend not in {"sqlite", "postgres"}:
        raise ValueError("PROSIGHT_DATABASE_BACKEND must be sqlite or postgres")
    if database_backend == "postgres" and not database_url:
        raise ValueError("PROSIGHT_DATABASE_URL is required for PostgreSQL")
    public_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    if auth_provider == "supabase" and public_key and not public_key.startswith("sb_publishable_"):
        raise ValueError("SUPABASE_PUBLISHABLE_KEY must be a publishable key (sb_publishable_)")
    return Settings(
        ai_provider=os.environ.get("PROSIGHT_AI_PROVIDER", "auto").lower(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        orchestrator_reasoning=_reasoning_effort("OPENAI_ORCHESTRATOR_REASONING", "none"),
        writer_reasoning=_reasoning_effort("OPENAI_WRITER_REASONING", "low"),
        embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        # Secure-by-default: legacy/demo API clients may explicitly opt out
        # with PROSIGHT_AUTH_REQUIRED=false, but a fresh deployment requires a
        # database-backed session before private API access.
        auth_required=os.environ.get("PROSIGHT_AUTH_REQUIRED", "1").lower() in {"1", "true", "yes"},
        auth_cookie_name=os.environ.get("PROSIGHT_AUTH_COOKIE", "prosight_session"),
        auth_cookie_secure=os.environ.get("PROSIGHT_AUTH_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"},
        auth_session_ttl_seconds=max(900, int(os.environ.get("PROSIGHT_SESSION_TTL_SECONDS", "28800"))),
        database_backend=database_backend,
        database_url=database_url,
        auth_provider=auth_provider,
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_publishable_key=os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
    )
