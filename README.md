# ProSight AI

ProSight AI is a manager-style multi-agent application for completed, active,
and future construction projects. It combines governed project data, PDF RAG,
reviewed Excel imports, a React command center, and traceable OpenAI agents.

## What the prototype answers

- Lists projects by lifecycle status.
- Shows contract value, planned/revised dates, delay, and progress variance.
- Finds project managers, engineers, site/client contacts, email, and mobile.
- Reports activities, manpower, equipment, man-hours, and milestones.
- Gives an evidence/source label with every answer.
- Restricts sensitive contact details for `employee` users.
- Routes work through Main Orchestrator, Database Manager, RAG, and Writer agents.
- Indexes project-scoped text PDFs with page citations.
- Validates Excel imports and requires Admin approval before database writes.

## Quick start

Install Python 3.11+ dependencies and initialize the sample database:

```powershell
python -m pip install -e .
python -m prosight.cli init
Copy-Item .env.example .env
# Add OPENAI_API_KEY to .env.
python -m prosight.cli serve
```

### React command center

Node.js 24 LTS or newer is required. After installing Node.js on Windows,
open a new PowerShell window so the updated user `PATH` is loaded.

Install and build the React frontend:

```powershell
cd frontend
npm install
npm run build
cd ..
$env:PYTHONPATH="src"
python -m prosight.cli serve
```

Open `http://127.0.0.1:8000`. The Python server serves the production React
build and exposes the existing agent and repository through `/api`.

For frontend development, run the Python API and `npm run dev` in separate
terminals. Vite proxies `/api` requests to port 8000.

The UI includes a portfolio command center, project explorer, role-aware
multi-agent chat, project selection, light/dark modes, and an Upload Center.

If the package is not installed, set the source directory:

```powershell
$env:PYTHONPATH="src"
python -m prosight.cli init
```

The API listens on `http://127.0.0.1:8000`:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post http://127.0.0.1:8000/query `
  -ContentType application/json `
  -Body '{"query":"List active projects","user_role":"project_manager","project_code":"PRJ-2024-001"}'
```

### Application model configuration

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY to your key.
python -m prosight.cli serve
```

The React AI Assistant and all named LLM agents use `gpt-5.6-luna`. PDF chunks
use `text-embedding-3-small` and persistent local Chroma storage. Secrets are
read from the ignored `.env` file and must never be committed.

Supported provider values are `openai`, `local`, and `auto`. OpenAI is the only
LLM provider. The deterministic `local` mode exists solely for offline tests and
direct database responses; it is not a language model.

### Upload and approval workflow

1. Open **AI Assistant**, select a project, and choose **Upload Center**.
2. Upload a searchable `.pdf` (20 MB maximum) or `.xlsx` (10 MB maximum).
3. PDF jobs extract pages, generate embeddings, and become queryable with page citations.
4. Excel jobs create a validation preview and stop at `awaiting_approval`.
5. Switch the demonstration role to **Admin** to approve or reject the import.

Scanned/encrypted PDFs, macro-enabled workbooks, legacy Excel formats, and
workbooks over 10,000 populated rows are rejected in this version.

### Query-flow logs

ProSight writes privacy-sanitized JSON logs to the server console and
`logs/prosight.log`. Follow the file live from PowerShell:

```powershell
Get-Content .\logs\prosight.log -Wait
```

Configuration:

```powershell
$env:PROSIGHT_LOG_LEVEL="INFO"
$env:PROSIGHT_LOG_DIR="logs"
$env:PROSIGHT_LOG_PREVIEW_CHARS="160"
$env:PROSIGHT_LOG_MAX_BYTES="5242880"
$env:PROSIGHT_LOG_BACKUP_COUNT="5"
```

Every query response includes `request_id` and `duration_ms`, which match the
server log entries and browser console events. Query/response previews redact
email addresses, phone numbers, authorization values, and API keys.

## Repository map

- `docs/architecture.md` — target architecture, security, RAG, and rollout.
- `data/projects.json` — sample construction project dataset.
- `src/prosight/repository.py` — SQLite data layer and access policy.
- `src/prosight/agents/` — Orchestrator, Database Manager, RAG, and Writer agents.
- `src/prosight/ingestion/` — PDF/Excel validation and durable job workflows.
- `src/prosight/rag/` — project-filtered Chroma retrieval and OpenAI embeddings.
- `src/prosight/api.py` — typed FastAPI query, upload, and approval transport.
- `tests/` — repository and agent tests.

### Production module layout

- `frontend/` — React presentation layer and responsive Assistant UI.
- `src/prosight/config.py` — typed environment and `.env` configuration.
- `src/prosight/providers/` — isolated OpenAI provider adapter.
- `src/prosight/tools/` — labeled Project Insights Agent tool registry.
- `src/prosight/agent.py` — provider orchestration and local agent.
- `src/prosight/repository.py` — SQLite data access and role policy.
- `src/prosight/api.py` — JSON HTTP transport.
- `src/prosight/observability.py` — privacy-safe structured logging.
- `data/`, `docs/`, and `tests/` — data, documentation, and verification.

## Test

```powershell
$env:PYTHONPATH="src"
$env:PROSIGHT_AI_PROVIDER="local"
python -m unittest discover -s tests -v
```

The suite forces local mode, so unit tests never call `gpt-5.6-luna`, consume
OpenAI credits, or require network access.

All names, phone numbers, emails, clients, values, and documents in the sample
dataset are fictional.
