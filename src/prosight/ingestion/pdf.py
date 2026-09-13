"""Text-PDF validation, extraction, and citation-preserving chunking."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from pypdf import PdfReader
import tiktoken


DATE_PATTERNS = (
    r"\b(20\d{2}-\d{2}-\d{2})\b",
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})\b",
    r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2})\b",
)


def detect_reporting_date(path: Path) -> str | None:
    """Detect the first credible report date from the first three PDF pages."""
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:3])
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).replace(",", "")
        for format_code in ("%Y-%m-%d", "%d %B %Y", "%B %d %Y"):
            try:
                return datetime.strptime(value, format_code).date().isoformat()
            except ValueError:
                continue
    return None


@lru_cache(maxsize=1)
def _embedding_encoding():
    return tiktoken.get_encoding("cl100k_base")


def _token_chunks(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """Split one page with the embedding model tokenizer and stable overlap."""
    encoding = _embedding_encoding()
    tokens = encoding.encode(text)
    if not tokens:
        return []
    step = max(1, size - overlap)
    return [encoding.decode(tokens[start : start + size]).strip()
            for start in range(0, len(tokens), step)]


def _normalized_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _clean_page_texts(raw_pages: list[str]) -> list[str]:
    """Remove short headers/footers repeated across at least three pages."""
    if len(raw_pages) < 3:
        return [text.strip() for text in raw_pages]
    candidates: Counter[str] = Counter()
    page_lines: list[list[str]] = []
    for text in raw_pages:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        page_lines.append(lines)
        edge_lines = lines[:2] + lines[-2:]
        candidates.update({
            _normalized_line(line) for line in edge_lines
            if 2 <= len(line) <= 160
        })
    repeated = {
        line for line, count in candidates.items()
        if count >= max(3, (len(raw_pages) + 1) // 2)
    }
    return [
        "\n".join(line for line in lines if _normalized_line(line) not in repeated).strip()
        for lines in page_lines
    ]


def _section_title(text: str) -> str:
    """Use a concise leading line as retrieval context without inventing structure."""
    for line in text.splitlines():
        candidate = re.sub(r"\s+", " ", line).strip()
        if 3 <= len(candidate) <= 120:
            return candidate
    return ""


def extract_pdf_chunks(path: Path, document: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract searchable pages and preserve document/page provenance."""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    chunks: list[dict[str, Any]] = []
    pages_with_text = 0
    raw_pages = [(page.extract_text() or "") for page in reader.pages]
    for page_number, text in enumerate(_clean_page_texts(raw_pages), start=1):
        if not text:
            continue
        pages_with_text += 1
        section = _section_title(text)
        for chunk_number, chunk in enumerate(_token_chunks(text), start=1):
            chunks.append(
                {
                    "id": f"{document['id']}:{page_number}:{chunk_number}",
                    "text": chunk,
                    "token_count": len(_embedding_encoding().encode(chunk)),
                    "content_hash": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                    "metadata": {
                        "document_id": document["id"],
                        "project_code": document["project_code"],
                        "filename": document["filename"],
                        "page_number": page_number,
                        "chunk_number": chunk_number,
                        "section": section,
                        "reporting_date": document.get("reporting_date") or "",
                        "effective_date": document.get("effective_date")
                        or date.today().isoformat(),
                        "date_status": document.get("date_status") or "fallback",
                    },
                }
            )
    if not pages_with_text:
        raise ValueError("No searchable text found; scanned PDFs require OCR")
    return chunks
