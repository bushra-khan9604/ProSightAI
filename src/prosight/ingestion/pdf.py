"""Text-PDF validation, extraction, and citation-preserving chunking."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader


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


def _word_chunks(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """Split text approximately by tokens using words as a deterministic proxy."""
    words = re.findall(r"\S+", text)
    if not words:
        return []
    step = max(1, size - overlap)
    return [" ".join(words[start : start + size]) for start in range(0, len(words), step)]


def extract_pdf_chunks(path: Path, document: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract searchable pages and preserve document/page provenance."""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    chunks: list[dict[str, Any]] = []
    pages_with_text = 0
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        pages_with_text += 1
        for chunk_number, chunk in enumerate(_word_chunks(text), start=1):
            chunks.append(
                {
                    "id": f"{document['id']}:{page_number}:{chunk_number}",
                    "text": chunk,
                    "metadata": {
                        "document_id": document["id"],
                        "project_code": document["project_code"],
                        "filename": document["filename"],
                        "page_number": page_number,
                        "chunk_number": chunk_number,
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
