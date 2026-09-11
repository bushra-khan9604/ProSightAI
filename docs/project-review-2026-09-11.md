# ProSight AI — project review

Review date: 11 September 2026

## Assessment

ProSight AI is a substantial construction-project intelligence prototype. It combines structured portfolio data, a React interface, document retrieval, reviewed project imports, notifications, and an AI assistant. Its modular backend and deterministic calculations provide a useful foundation. It needs security and data-integrity work before use with confidential production data.

This review examined the local source, documentation, tests, and frontend build. It includes two isolated defect reproductions. It did not exercise a live model, perform a browser usability review, audit dependency vulnerabilities, or test production load. No application source was changed.

## Product and architecture

| Layer | Current implementation |
|---|---|
| Interface | React 19, Vite 8, Recharts, Lucide; dashboard, project explorer, assistant, uploads, approvals, notifications, and theme selection |
| Transport | FastAPI; validated request models, REST endpoints, and server-sent assistant execution states |
| Agent workflow | Main Orchestrator, database and RAG tools, Writer agent; deterministic local fallback |
| Structured storage | SQLite; project JSON payloads plus workflow, schedule, manpower, invoice, notification, and audit tables |
| Documents | Local files, pypdf extraction, OpenAI embeddings, persistent Chroma retrieval filtered by project |
| Imports | openpyxl parsing, canonical templates, optional AI column mapping, project change previews, direct portfolio upserts |
| Operations | Environment configuration, request IDs, duration measurements, rotating JSON logs, in-process ingestion workers |

The normal assistant path is React → FastAPI → Orchestrator → database/RAG evidence → Writer → response. PDF processing extracts and indexes page-level evidence; detected reporting dates can require confirmation. Project Excel changes use an approval workflow, while portfolio imports and project edits have direct-write paths.

## Strengths

- Delay and progress variance are calculated in Python rather than delegated to the model.
- Database tools expose selected operations rather than accepting model-generated SQL.
- Typed evidence contracts separate orchestration, retrieval, and response generation.
- Project filters and page citations are implemented in vector retrieval.
- Approval decisions group database changes, job state, audit records, and notifications in a transaction.
- Query logging includes request correlation and explicit redaction of common contact and credential patterns.
- Tests cover calculations, representative queries, imports, approval permissions, notifications, formatting, and project enrichment.

## Prioritized findings

### 1. High: client-supplied roles provide no authenticated access control

The API accepts roles through query parameters, form fields, and JSON. A caller can supply `admin`; the role allowlist only checks whether the string is recognized. Repository project lookup does not enforce user membership, and notifications are addressed to roles rather than individual users.

This is consistent with a demonstration role selector, but it is a production blocker. Add authenticated identity, derive roles on the server, and apply project membership checks to every data and document operation. Audit records should identify a person, not just a role.

Evidence: `src/prosight/api.py:37`, `src/prosight/api.py:741`, `src/prosight/repository.py:1190`.

### 2. High: duplicate upload deletes the existing stored file — reproduced

The upload destination is derived from checksum and filename. `submit()` copies the file before registering it. When the database rejects the duplicate checksum, exception cleanup unlinks that same destination, deleting the original upload while leaving its existing metadata.

An isolated temporary-directory reproduction confirmed: original present before duplicate, duplicate rejected, original absent afterward, original database record retained.

Use unique staging paths and ownership-aware cleanup. Check/register duplicates without overwriting an existing artifact, then publish the new file safely. Add a regression test that verifies original bytes survive duplicate submission.

Evidence: `src/prosight/ingestion/manager.py:67`, `src/prosight/repository.py:335`.

### 3. High: Excel validation is weaker than form validation — reproduced

Canonical workbook parsing checks lifecycle status and converts numeric fields, but does not apply the form's date, nonnegative contract-value, or 0–100 progress constraints. A temporary workbook containing invalid dates, a negative contract value, and progress of 200% was accepted into a change preview. The approved import path writes the project payload without the form's validation model.

Use a shared domain validator for forms, canonical workbooks, mapped workbooks, and approved writes. Validate project codes and the relationship between workbook projects and the selected upload project as well. Invalid dates can later break project decoration and listing.

Evidence: `src/prosight/ingestion/excel.py:92`, `src/prosight/api.py:60`, `src/prosight/repository.py:1117`.

### 4. High: partially indexed failed PDFs can remain searchable — source finding

Chroma writes chunks in batches. If a later batch fails, the job and document are marked failed without removing already written vectors. Retrieval filters only by project code, so those partial results can still be returned despite the failed document status.

Stage indexing before publication, or remove partial vectors on failure and restrict retrieval to published documents. Test a failure after one successful batch.

Evidence: `src/prosight/rag/store.py:74`, `src/prosight/ingestion/manager.py:151`.

### 5. Medium: approval guarantees differ across write paths

The README broadly describes Admin-approved Excel writes, but portfolio imports immediately call `apply_portfolio_import()`, and project PATCH requests write immediately for all three application roles. This may be intentional, but the product's governance contract is unclear.

Decide which mutations require review, enforce that policy consistently, and document any direct-write exceptions.

Evidence: `src/prosight/api.py:253`, `src/prosight/api.py:599`, `README.md`.

### 6. Medium: upload and worker resource limits are incomplete

Upload handlers copy the entire request file before applying size checks; the new-project import-preview path has no explicit byte limit. Workbook parsing loads the workbook before checking row counts. Two worker threads limit concurrent execution, but the executor's pending queue is not bounded. Shutdown closes the vector store without waiting for active workers.

Apply byte limits while receiving files, constrain decompressed workbook size, bound pending jobs, and coordinate worker shutdown. Durable retry and queue infrastructure would be appropriate before operating multiple server processes.

Evidence: `src/prosight/api.py:213`, `src/prosight/api.py:459`, `src/prosight/ingestion/excel.py:68`, `src/prosight/ingestion/manager.py:207`.

### 7. Medium: evidence and execution claims need stronger verification

The hosted flow relies on instructions to call Writer last, but the returned route always appends `writer` whether or not that tool actually ran. PDF citations are extracted from generated prose rather than checked against retrieved evidence. RAG uses a relative similarity cutoff, so even weak matches can qualify. Local fallback ignores conversation history.

Record actual specialist execution, validate citation IDs against retrieved evidence, add an evaluated no-answer threshold, and cover follow-up questions in fallback tests. Live answer quality remains unverified in this review.

Evidence: `src/prosight/agents/orchestrator.py:90`, `src/prosight/agents/orchestrator.py:205`, `src/prosight/rag/store.py:90`.

### 8. Medium: maintainability and documentation lag the implementation

Most interface features share a roughly 940-line `App.jsx`, including a legacy assistant component. The repository module exceeds 1,200 lines. There are two frontend lockfiles, broad Python dependency ranges without a lockfile, and no tracked CI configuration found. The README describes an employee role that the current API deliberately rejects; the architecture document still mentions a zero-dependency HTTP server despite FastAPI usage.

Split frontend features and repository responsibilities, choose one frontend package manager, establish reproducible backend dependencies and CI, and distinguish implemented behavior from target architecture in the documentation.

## Verification results

| Check | Result |
|---|---|
| Frontend production build | Passed with installed Vite; output directed to a temporary directory |
| Bundle size | Main JavaScript: 660.03 KB minified, 191.12 KB gzip; Vite emitted a size warning |
| Backend unittest discovery | 47 entries reported: 40 passed and 7 errors; four errors were failed test-module imports |
| Backend blockers | Available Python runtime lacks `fastapi`, `chromadb`, and `agents`; these are environment/dependency errors, not demonstrated assertion failures |
| Duplicate-upload reproduction | Confirmed deletion of existing file with metadata retained |
| Invalid Excel reproduction | Confirmed invalid values accepted into preview |
| Paid API calls | Disabled for verification using local provider mode and an empty API key |

The source contains 70 test methods, but missing dependencies prevented full discovery and execution. The suite therefore cannot be reported as passing. Tests should be rerun in a complete isolated environment; no dependency installation was performed for this analysis.

## Recommended sequence

1. Repair duplicate-upload preservation and shared import validation; add focused regression coverage.
2. Make document indexing publication atomic and verify failure cleanup.
3. Establish authenticated identity, project authorization, and a consistent approval policy before confidential-data deployment.
4. Complete the dependency environment and automate backend tests plus frontend builds in CI.
5. Add browser workflow tests and evidence-quality evaluations, then address queue limits, shutdown, frontend splitting, and documentation.

Existing modifications to the frontend lockfile and Python egg-info files were present before the review and were left intact.
