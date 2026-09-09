# Agent foundation: step 1

This update strengthens the existing SQLite/Chroma implementation. It does not
implement tenant isolation, migrate databases, or change hosted agent scheduling.

## Changed behavior

- RAG candidates require explicit approved metadata and selected-project scope.
- The application supplies an allowlist from database documents that are approved
  and fully indexed. Visibility is checked again after retrieval. Orphaned vectors,
  pending documents and partial indexes are excluded from application responses.
- Relevance sorts before effective date. Exact-phrase scoring preserves word order.
- Chroma filters lexical candidates by case-insensitive whole terms and returns at
  most 200 for scoring. This bounds transfer and Python work; it is not BM25 and can
  miss relevant matches beyond that cap. Benchmark a ranked keyword backend next.
- The database agent rejects unknown roles and ambiguous/partial project scopes.
- Project invoice pivots aggregate only the selected project in SQL.
- Non-admin manpower evidence omits billing_rate, cost_rate and cost_value, matching
  the dashboard policy. Only admins/managers may submit agent mutation previews.
- Writer instructions treat documents as evidence and respect historical periods;
  this prompt guidance is not a security boundary or an evaluated accuracy guarantee.

## Compatibility and verification

Chroma 1.5.9 or newer is required for the tested regex retrieval path. Update the
project dependencies before running the application. No existing database or
uploaded documents are migrated by this change. Legacy vector chunks without
approval metadata are intentionally hidden. Restore their searchability only
through a controlled rebuild from verified approved originals; never bulk-label
unknown chunks as approved.

Regression coverage is in tests/test_evidence_boundaries.py and tests/test_ingestion.py.
Tests use temporary databases and deterministic embeddings. Live answer quality,
large-corpus recall and latency still need measurement with representative PDFs.

The local prosight_env interpreter was inaccessible during this update. Verification
uses bundled Python 3.12 with temporary dependencies under ignored tmp/agent-test-deps.
This is a test environment, not a repair of the user's normal application environment.

## Accounts and access

No new account is required for this local step. Live embeddings and answers still
require the existing configured OpenAI API access; tests do not require that access.

Before the managed database/storage step, choose one retrieval architecture:

- Recommended initial setup: a Supabase project for PostgreSQL, Auth, private Storage
  and pgvector. Tenant memberships and permission policies must still be implemented.
- Alternative: PostgreSQL/object storage plus a Weaviate Cloud cluster for retrieval.
  Weaviate replaces Chroma; it does not replace the application database or file store.

Set credentials through the local environment or deployment secret manager. Do not
put secrets into source control or conversation messages. No hosted resources have
been created and no production deployment has been performed.

## Next steps

1. Define authenticated tenant/project membership and enforce it across all read,
   write, RAG, conversation, notification and cache paths. Current project scope is
   not a substitute for access authorization.
2. Migrate authoritative data/storage and introduce durable ingestion events,
   workers, retries, immutable document versions and deletion reconciliation.
3. Evaluate parsing/OCR, hybrid ranking, reranking, historical/latest revision queries,
   and explicit live-path database/RAG concurrency against a fixed evaluation set.

## Verification result

Final full-suite run: 84 tests, 80 passed, 4 errors. All 38 tests in the affected
agent, ingestion, writer and new evidence-boundary modules passed. The four
remaining errors are in existing portfolio import parsing tests, which fail with
`Manpower requires Admin mapping for missing fields: Allocation` before the updated
agent/pivot code is reached. Portfolio parser code was not changed in this step.

The existing API fixtures were run with PROSIGHT_AUTH_REQUIRED=false in the test
process because they submit role parameters without logging in. A separate check
with PROSIGHT_AUTH_REQUIRED=true confirmed unauthenticated requests specifying
role=admin still receive HTTP 401. Application authentication settings were not
changed. Full results are in ignored tmp/agent-suite-final.txt.
