"""Plan semantic PDF reindexing. Dry-run/offline is the unconditional default.

The manifest is trusted only as data and no command from it is executed.  This
tool has no upload or delete operation.  Actual Storage reads and semantic writes
must be supplied by a separately authorized runtime integration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prosight.rag.reindex import ReindexDocument, ReindexPlanner
from prosight.rag.semantic import RevisionContext


def load_manifest(path: Path) -> list[ReindexDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Manifest must be a JSON array")
    documents = []
    for item in payload:
        context = RevisionContext(**item["context"])
        checksum = str(item["checksum_sha256"])
        if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
            raise ValueError("Each revision needs a lowercase SHA-256 checksum")
        documents.append(ReindexDocument(context, checksum, item.get("embedding_job_id")))
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a no-upload semantic PDF reindex plan")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--expected-count", type=int, default=47)
    args = parser.parse_args()
    plan = ReindexPlanner().plan(load_manifest(args.manifest))
    if len(plan.documents) != args.expected_count:
        raise ValueError(
            f"Reindex manifest must contain {args.expected_count} unique existing revisions; "
            f"found {len(plan.documents)}"
        )
    print(json.dumps({
        "dry_run": True,
        "documents": len(plan.documents),
        "skipped_duplicate_revisions": list(plan.skipped_duplicates),
        "uploads": 0,
        "deletes": 0,
        "legacy_index_retained": True,
        "next_step": "Run through an authorized StorageReader and semantic sink, compare retrieval, then record explicit cutover acceptance.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
