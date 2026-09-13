# Analyst, Planner, and governed imports

## Release contents

The existing Assistant routes analysis and planning requests to specialists automatically. Ordinary stored-data and document questions retain the database/RAG/Writer workflow. Specialist results pass to the Writer; models cannot approve or activate data. No separate agent pages or selectors are introduced.

Portfolio Import accepts Planning Inputs, Project Controls, Historical Benchmarks, Shared Resource Scenarios, Project Documents, and Mixed Project Files, plus Project Master and the existing three formats. The workflow stages immutable, project-scoped versions, previews changes, and submits them to the existing Admin approval queue. Approving activation supersedes the previous authoritative selection atomically. Legacy projects continue to use their existing records. For managed projects, omitted sections inherit from the parent, and later legacy uploads become proposed changes.

The workbook contract is `src/prosight/controls/workbook_schema.json`. Its sheet names, ordered headers, types, units, and keys correspond to the generated dataset. Supported informational sheets are ReadMe and Dataset Notes. Other unknown sheets fail validation. Source summaries remain observations; calculation services recalculate performance. Importers derive WBS, validate unique scope/activity mappings, and retain source snapshots separately. Historical assignments never populate the current manpower roster.

## Deployment and isolated verification

**No migrations or synthetic records have been applied to the hosted production project. Hosted Supabase verification is still outstanding.** The available connected Supabase project is production; no isolated test project or branch was available. Local PostgreSQL verification below is useful but does not replace Supabase Auth, PostgREST, and Storage integration testing.

1. Provision or supply an isolated Supabase test project or branch. Confirm the target project reference before linking the Supabase CLI. Keep test credentials in local environment configuration, never in source control. Use the application's existing Supabase URL, public key, service key, and JWT configuration for that isolated target.
2. Install the existing Python project dependencies (`pip install -e .`) and frontend locked dependencies. ReportLab is now a runtime dependency for PDF exports. Keep the service key only on the backend. The configured OpenAI model must support Responses structured outputs; deterministic analysis works without a model, while semantic planning reports its unavailability.
3. Apply existing foundation migrations to the isolated target, followed in order by `202609130001_project_controls.sql`, `202609130002_controls_workers.sql`, and `202609130003_controls_batches_exports.sql`. These add versioned records, row-level policies, transactional RPCs, durable job leases, and protected artifact storage. Deploy the backend only after migrations succeed; it starts two bounded worker loops during application lifespan.
4. Create test-only users with Admin, planning, and employee roles and distinct project memberships. Import the five-project pack through the UI in the isolated environment. Select each project, upload its supported files, validate, and review before/after counts. Confirm each PDF's reporting date, then approve it through the existing ingestion flow. Structured activation does not wait for PDF indexing.
5. Verify active-version schedule/manpower/invoice totals replace the corresponding legacy authoritative views. Approve a newer version, reject another, and attempt concurrent stale approvals. Verify only one active version remains and prior versions are retained.
6. Ask for EVM, delay analysis, resource conflicts, cash flow, a future plan, and an analysis plus recovery plan. Review and edit a draft; save its new revision, download both formats, submit, and approve. Disconnect during a run and retrieve the saved result through the Assistant. Restart the backend during a leased run, and test cancellation.
7. Revoke a member's primary and historical project access while jobs run. Check version reads, run retrieval, API downloads, and direct Storage requests. Test actual Supabase RLS policies with user sessions, not service credentials. Confirm reference-answer files are rejected and ordinary retrieval remains project-scoped.
8. Check both themes and narrow screens, PDF ingestion/date approval, and existing legacy imports. Review database security advisors before an explicitly authorized production rollout. Production rollout must not seed demonstration data automatically.

Rollback preserves history: roll back the application deployment and stop its workers if necessary. Do not drop version tables or mass-copy synthetic records into legacy tables. To restore an earlier dataset, stage its content as a new reviewed version based on the current active version and approve it. A deployment predating version-aware reads displays legacy data, so coordinate rollback with users.

## Import and execution boundaries

- At most 30 XLSX/PDF files per batch, 20 MB per file; XLSX decompression limited to 150 MB and 2,000 archive entries, with 100,000 rows, 100 columns, and 16,000 characters per cell. Formula inputs require saved values. PDFs require searchable text and at most 300 pages. ZIP, encrypted files, macros, OCR, and evaluation-reference answers are unsupported.
- Conflicting files are rejected. Identical reuploads resolve to existing content. Rejected or interrupted drafts do not overwrite active versions. An interrupted validation can be retried after its five-minute lock expires. Specialist/export jobs use ten-minute leases, bounded concurrency, three attempts, cancellation, and stale-lease completion protection. User tokens are never stored in jobs.
- Workers reload membership and enforce their pinned primary/historical project scope. Runs pin dataset versions, dates, and document revisions. Removed or changed evidence is reported unavailable. Document coverage is bounded to 400,000 characters and requires explicit coverage validation; no OCR or CAD/BIM interpretation is attempted.
- PDFs populate searchable evidence through existing approval/ingestion, not the structured controls tables. Project document and structured import statuses are independent.
- Full scheduling supports FS relationships, integer working days, weekly calendars, and exceptions. Unsupported relationships and cycles fail. Resource scenarios compare additional crews and resequencing; they are heuristic proposals, not mathematical optimization. Delay evidence distinguishes observed records, suspected causal explanations, and calculated counterfactual schedule effects.
- EV is earned quantity times budget unit value, PV is approved time-phased budget, and AC is accrued cost. CPI/SPI with undefined denominators remain unavailable. Future projects have no execution actuals. Rounded historical quantity records can produce sub-dollar differences from supplied informational EV summaries.
- Cash-flow projections distinguish billings, retention, receipts, costs, and estimated remaining expenditure. Forecasts and payment-lag assumptions are labeled. A proposal's original baseline is preserved when testing active-project recovery; activity savings are separate from completion savings.
- Future plans use approved scope, quantities, productivity, rates, and explicitly labeled commercial assumptions. Document requirements require exact source excerpts. Contradictions block completion. Benchmarks require an explicit historical-comparison request and preserve their historical dates, crew bases, source project, and adjustment limitations; one synthetic history is not statistical prediction.

## Interfaces

Existing endpoints and Assistant SSE status/delta/final events are preserved. New interfaces:

| Interface | Purpose |
|---|---|
| `POST /api/portfolio-import-batches` | Create a project batch |
| `POST /api/portfolio-import-batches/{id}/files` | Add one XLSX or PDF |
| `GET /api/portfolio-import-batches/{id}` | Inspect batch and document statuses |
| `POST /api/portfolio-import-batches/{id}/validate` | Freeze, validate, and stage |
| `POST /api/portfolio-import-batches/{id}/submit` | Request Admin approval |
| `GET /api/projects/{code}/controls-versions` | List accessible versions |
| `GET/PATCH /api/projects/{code}/controls-versions/{id}` | Read a version or create an edited draft revision |
| `POST /api/projects/{code}/controls-versions/{id}/submit` | Submit a planning draft |
| `POST /api/projects/{code}/controls-versions/{id}/exports/{format}` | Queue XLSX/PDF export |
| `GET /api/agent-runs/{id}` | Retrieve progress or completed result |
| `POST /api/agent-runs/{id}/cancel` | Cancel a run |
| `POST /api/agent-runs/{id}/exports/{format}` | Export pinned analysis results |
| `GET /api/artifacts/{id}/download` | Recheck permissions and download |

Assistant responses optionally carry run ID, project code, dataset version, readiness, structured results, draft ID, and artifact references. Draft edits support schedule duration/crew size, budget components, procurement lead times, and active-project recovery reductions/costs through the compact editor. Saving recalculates dependent records; unsaved edits cannot be submitted or exported.

## Verification commands and limits

Run unit and integration fixtures with `PROSIGHT_AI_PROVIDER=local` and `OPENAI_AGENTS_DISABLE_TRACING=1`, then `python -m unittest discover -s tests -v`. Run `npm run build` in `frontend`. Fixture tests use the existing generated pack under `outputs/project-dataset-20260912`; they exercise all five projects without writing to hosted services. Semantic Planner tests use a structured model stub, not a live model.

`scripts/test_controls_sql.mjs` executes migrations and tests activation, typed fixture rows, permissions, leases, and cancellation in isolated PGlite PostgreSQL. It expects `outputs/controls-sql-test/fixtures.json` and PGlite installed under that directory. Set `PGLITE_MODULE` to an alternate module path if needed. This harness intentionally emulates only the required Auth/Storage schema interfaces.

Rebuild the SQL fixture JSON with `python scripts/build_controls_test_fixtures.py`. The helper reads the existing demonstration workbooks and performs no database operations.

`scripts/test_controls_ui.mjs` exercises the actual React app against mocked API routes, with a local Vite server on port 5179. Set `PLAYWRIGHT_MODULE` to the installed Playwright module path if it is not in normal Node resolution. It creates and removes a temporary preview entry, and writes light/dark/narrow screenshots under `outputs/controls-ui-qa`. Mocked UI checks do not establish hosted end-to-end behavior.

Before release acceptance, complete the isolated Supabase checklist above, live-model planning checks, and full browser-to-database workflow verification. Local passing tests alone do not establish deployment readiness.

### Recorded local results — 13 September 2026

- 111 Python tests passed, including all five generated project datasets, independent arithmetic/calendar cases, future planning with a structured model stub, legacy roster replacement, formula rejection, evaluation metadata rejection, and exports.
- All three new migrations executed in isolated PGlite PostgreSQL. Five fixture imports passed typed staging and approval/activation; stale activation, unauthorized access, job lease recovery/cancellation, immutable job scope, and historical-membership revocation checks passed.
- Frontend production build passed. It retains the pre-existing large-bundle warning. Mocked browser checks passed for the existing Portfolio Import dialog in light, dark, and narrow layouts; no page errors were recorded. The temporary preview entry was removed.
- Sample Analyst export produced 33 workbook sheets and 44 searchable PDF pages. Saved workbook values and worksheet notices were checked; representative rendered PDF pages were visually inspected. This is not a claim that every possible user-generated export layout has been inspected.
- No hosted migration, production activation, synthetic upload, or live model execution occurred during these checks.
