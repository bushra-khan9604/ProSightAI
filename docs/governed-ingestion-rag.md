# Governed ingestion and semantic retrieval

This is the application-side design for the three-layer database redesign. The
frozen integration contract in `docs/database-redesign-contracts.md` remains the
authority. The existing `prosight` application and vector paths remain available
during comparison and rollback.

## Excel workflow

1. Register an `ingestion.import_batches` attempt and its source file metadata.
   Compute SHA-256 while staging the file. Reject an existing
   `(organization_id, source_kind, checksum_sha256)` or idempotency key before
   profiling.
2. Load only `.xlsx` data with external links disabled. Formula text is retained
   as untrusted source evidence and rejected as an import value. It never affects
   authorization, mapping, approval, or workflow state.
3. Bind one immutable organization mapping profile and one immutable version.
   `mapping_profile_id` identifies the reusable layout family;
   `mapping_version_id` and `version_no` identify its immutable revision. The
   registry key is `(organization_id, mapping_profile_id, version_no)`, so an
   organization can have several layouts at version 1. Both IDs and the version
   number are included in checksums. A suggested
   mapping, including an LLM suggestion, goes through the same exact header,
   field, type, reference, duplicate, and reconciliation checks as a manual
   mapping. Each mapped workbook sheet also has an immutable
   `ingestion.mapping_version_sheets` row. A staged row carries that exact
   per-sheet ID, so a multi-sheet/multi-entity version cannot substitute a
   different target entity at publication time.
4. Normalize deterministically. Dates are ISO dates, money/rates use `Decimal`,
   currency values must be ISO 4217 codes, UUID references must belong to the
   same organization, and business keys must be unique within the batch.
5. Persist raw values, normalized values, sheet/row/column provenance, formula
   presence, mapping checksum, transformation version, and row checksums. The
   review preview retains its exact `import_batch_id`, `source_file_id`, profile
   ID, version ID/number, and deterministic checksums even when zero rows pass.
6. Bind approval to the exact batch, source file, mapping profile/version,
   source, input-profile, validation, and preview checksums, requester, approver,
   and decision. Empty and rejected previews receive the same identity checks. Only an active
   organization owner/admin may approve; the database routine rechecks this.
7. Publish with one call to
   `ingestion.publish_import_batch(batch_id uuid, approval_id uuid,
   idempotency_key text)`. The database routine must acquire its idempotency lock,
   recheck approval and actor authorization, upsert approved business keys, write
   lineage, and transition the batch in one transaction. It returns a row whose
   `status` is `published` or `already_published`. The application has no
   per-record publication fallback.

The concrete application adapter persists each phase in a bounded redesigned
transaction: profile/version/sheet definitions; batch and source file; source
sheets and columns; transformation run; every staged row and cell; validation
issues; and the append-only decision. All values are bound parameters. These
transactions write only `ingestion`; the only construction write path is the
publication RPC. Before inserting an approval, the application independently
recomputes the input/profile checksum from the persisted source checksum,
profile ID, version ID/number, and immutable mapping checksum, then compares it
with both batch and transformation-run state. Database triggers and the private
publisher repeat the authoritative checks.

The authenticated HTTP lifecycle is:

- `POST /api/three-layer/mappings` for an immutable multi-sheet mapping;
- `POST /api/three-layer/imports/prepare` for bounded XLSX staging and validation;
- `POST /api/three-layer/imports/{batch_id}/submit`;
- `POST /api/three-layer/imports/{batch_id}/decision`;
- `POST /api/three-layer/imports/{batch_id}/publish`.

Organization and project access are derived from active membership. The client
may select one organization when the verified user belongs to several, but may
not provide a project allowlist or an actor/approver identity.

The application lifecycle table is copied exactly from the migration trigger:

- `uploaded -> profiling|cancelled`
- `profiling -> mapping|validation_failed|cancelled`
- `mapping -> validating|validation_failed|cancelled`
- `validating -> review_ready|validation_failed|cancelled`
- `review_ready -> awaiting_approval|validating|cancelled`
- `awaiting_approval -> approved|rejected|validating|cancelled`
- `approved -> publishing|cancelled`
- `publishing -> published|publish_failed`
- `publish_failed -> approved|publishing|cancelled`
- `validation_failed -> profiling|mapping|validating|cancelled`

`published`, `rejected`, and `cancelled` are terminal in the application table.

## Structured facts and semantic projections

`prosight.construction_facts.ConstructionFacts` reads authoritative facts from
the `construction` schema with bound organization and allowed-project UUIDs.
Projects, risks, claims, and daily-report structured columns are SQL results.
Amounts and dates are not reconstructed from vector text.

`prosight.rag.semantic.project_entity` accepts only the frozen descriptive
allowlist: project summaries, risks, claims/notices, RFIs, NCRs, daily reports,
meetings/action items, safety incidents, document sections, and handover
observations. Numeric invoice and other tabular facts are rejected as SQL-only.
Its database payload uses `language_code`, `construction_document_id`, an integer
`projection_version`, and `projection_version_id`; approved projections start at
`index_status='pending'`.

PDF chunk IDs are UUIDv5 values derived from semantic document identity,
projection/chunking versions, page range, heading path, ordinal, and content
checksum. Each chunk mirrors the normalized citation/provenance fields in typed
columns and metadata. The typed column is `construction_document_id`; metadata
retains `document_id`. Approved chunks are `pending` before embedding. Legacy
PDF revisions set both `source_file_id` and `import_batch_id` to null and rely on
construction document/revision plus Storage provenance. Ingestion-derived
revisions must set both IDs; one-sided lineage is rejected.

Embeddings must use `text-embedding-3-small` and contain exactly 1,536 finite,
non-zero values. `semantic.publish_chunk_embeddings` is the application adapter's
single idempotent indexing call. The database routine must recheck the job and
chunk state, prevent duplicate vectors, and return `succeeded` or
`already_succeeded`; on success, the job is `succeeded` and the document/chunks
are `ready`. The RPC payload is a JSON array of `{chunk, embedding}` objects and
the application call is positional through
`semantic.publish_chunk_embeddings(org_id, job_id, chunks_jsonb,
idempotency_key)`.

Hybrid retrieval queries `semantic.semantic_chunks` and
`semantic.semantic_documents`. Dense, lexical, and final branches all repeat the
typed organization/project, approval, ready, model, dimension, projection, and
chunking filters. Dense ranking uses
`OPERATOR(extensions.<=>)`; the matching database index must use HNSW
`extensions.vector_cosine_ops`.

## Controlled PDF reindex

`tools/reindex_semantic_pdfs.py` accepts a local JSON manifest and only emits a
dry-run plan. It has no upload, delete, embedding, database, or cutover command.
Each manifest entry may carry its already allocated `embedding_job_id`; when it
does, execution passes that ID only to the matching semantic document call.
Duplicate Storage objects and duplicate semantic version namespaces are skipped.
The logical checksum rule is organization-scoped: identical bytes at different
paths are skipped when they claim the same authoritative construction document
revision. Identical bytes remain distinct only when their authoritative revision
IDs differ. Reusing one Storage bucket/path across organizations is rejected.

An authorized runtime can inject a read-only `StorageReader` and a new-semantic
`SemanticChunkSink` into `ReindexExecutor`. Execution downloads each existing
private object, verifies its registered SHA-256, derives stable chunks, and
publishes each semantic document separately through its own idempotent embedding
job/RPC call. A failure can therefore never mix chunks from different semantic
documents or jobs. It never uploads an existing PDF, never deletes legacy
vectors, and never changes the legacy index.

Use `compare_rankings` for the frozen legacy/new query set. Store the comparison
artifact and checksum. Any cutover controller must call
`require_cutover_acceptance` with an explicit acceptance ID, accepting actor, and
comparison checksum. The reindex module itself does not perform cutover.

Example dry run:

```powershell
$env:PYTHONPATH="src"
python tools/reindex_semantic_pdfs.py path\to\revision-manifest.json
```

## Runtime bridge and cutover

`PROSIGHT_SCHEMA_MODE` accepts `legacy`, `compare`, or `redesigned` and defaults
to `legacy`. Legacy mode does not instantiate the new adapters. Compare and
redesigned modes require PostgreSQL and verify the redesigned catalog/RPC/role
contract without querying the legacy schema. Request transactions accept only a
server-verified `uuid.UUID`, then execute `SET LOCAL ROLE authenticated`, bind
transaction-local `request.jwt.claim.sub` and `request.jwt.claims` with
`pg_catalog.set_config`, and pin `search_path` before any application query.
RLS derives tenant/project authority from active membership rows.

The `/api/three-layer/facts` and `/api/three-layer/search` routes are present but
return an inactive-mode error while legacy is selected. When enabled, they derive
the organization and allowed project UUIDs from active authenticated membership;
clients cannot submit project allowlists. Structured requests query only
`construction`. Semantic requests query only `semantic`. Compare mode may invoke
an explicitly supplied legacy comparator and retains rollback. Redesigned mode
never invokes a legacy callback, never uses the legacy local session table
(Supabase verifies the bearer identity), blocks other legacy `/api/*` data
paths, and reports that legacy rollback is unavailable.

Governed publication and indexing are exposed through the same runtime for
trusted workflow/background integrations and call only their single database
RPCs.

Do not select `redesigned` until local migration tests pass, all 47 existing
Storage objects have been checksum-verified and reindexed without upload, the
70-vector legacy index has been retained, retrieval comparison is accepted by an
authorized human, and the configured projection/chunking versions are active.
Use `compare` for the observation period. Roll back by selecting `legacy`; no
legacy table, vector, or PDF deletion is part of this bridge.

## Database handoff

The inspected migrations now contain `ingestion.publish_import_batch(uuid,
uuid, text)`, `semantic.semantic_projection_versions`,
`semantic.semantic_documents`, `semantic.semantic_chunks`, generated
`search_vector` columns, the cosine HNSW index, filtered hybrid search, and
`semantic.publish_chunk_embeddings(uuid, uuid, jsonb, text)`. The application
payload, integer versions, status transitions, and RPC return states match those
objects. Hosted execution remains intentionally unperformed in this workstream.
