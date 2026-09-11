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
    embedding_batch_size: int
    embedding_retry_count: int
    retrieval_candidate_count: int
    retrieval_evidence_count: int
    retrieval_confidence_threshold: float
    data_backend: str
    supabase_url: str
    supabase_publishable_key: str
    supabase_service_role_key: str
    bootstrap_admin_email: str


def _reasoning_effort(name: str, default: ReasoningEffort) -> ReasoningEffort:
    """Return a validated reasoning effort from one environment setting."""
    value = os.environ.get(name, default).strip().lower()
    if value not in REASONING_EFFORTS:
        supported = ", ".join(sorted(REASONING_EFFORTS))
        raise ValueError(f"{name} must be one of: {supported}")
    return value  # type: ignore[return-value]


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read a bounded integer without allowing unsafe runtime values."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """Read a bounded floating-point setting."""
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def get_settings() -> Settings:
    """Load `.env` and return the latest process-level configuration."""
    load_env_file()
    return Settings(
        ai_provider=os.environ.get("PROSIGHT_AI_PROVIDER", "auto").lower(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        orchestrator_reasoning=_reasoning_effort("OPENAI_ORCHESTRATOR_REASONING", "none"),
        writer_reasoning=_reasoning_effort("OPENAI_WRITER_REASONING", "low"),
        embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_batch_size=_bounded_int("RAG_EMBEDDING_BATCH_SIZE", 64, 1, 256),
        embedding_retry_count=_bounded_int("RAG_EMBEDDING_RETRY_COUNT", 5, 1, 10),
        retrieval_candidate_count=_bounded_int("RAG_RETRIEVAL_CANDIDATES", 30, 5, 100),
        retrieval_evidence_count=_bounded_int("RAG_EVIDENCE_COUNT", 8, 1, 20),
        retrieval_confidence_threshold=_bounded_float(
            "RAG_CONFIDENCE_THRESHOLD", 0.25, -1.0, 1.0
        ),
        data_backend=os.environ.get("PROSIGHT_DATA_BACKEND", "auto").lower(),
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_publishable_key=os.environ.get(
            "SUPABASE_PUBLISHABLE_KEY", os.environ.get("SUPABASE_ANON_KEY", "")
        ),
        supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        bootstrap_admin_email=os.environ.get("PROSIGHT_BOOTSTRAP_ADMIN_EMAIL", ""),
    )
