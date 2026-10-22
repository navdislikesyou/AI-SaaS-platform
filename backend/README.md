# Backend — AI SaaS Platform

FastAPI backend foundation for the AI SaaS Platform.

**All three agents are implemented and live in this repository.** Knowledge and
Automation run synchronously through `POST /api/v1/agents/execute`. The
Performance Analyzer is implemented too, but its analysis is CPU-bound and long
running, so it is served through its own background-job API at
`/api/v1/performance/jobs` instead of the generic execution endpoint.

Each agent exposes a thin dict-in, dict-out service that the backend calls. The
API reports each agent's status honestly, including when an agent is enabled but
fails to initialize.

The backend also implements JWT authentication with rotating HttpOnly refresh
cookies, organisation-scoped multi-tenancy, role-based access control
(`employee` / `manager` / `admin`), user management, database persistence
(SQLAlchemy 2.x + Alembic), browser upload APIs for all three agents, and an
activity-history feed.

## Agents

| Agent | Purpose | Status | Capabilities | Served at |
|---|---|---|---|---|
| `knowledge` | RAG question answering over PDF/DOCX/TXT documents | Connected when enabled | `ingest_document`, `query` | `/agents/execute` |
| `automation` | Interprets productivity requests and drafts actions | Connected when enabled | `draft_action` | `/agents/execute` |
| `performance` | Data analytics: KPIs, comparisons, trends, insights | Connected when enabled | `[]` (see below) | `/performance/jobs` |

Capabilities listed above are the ones that actually work through that agent's
endpoint. Anything not listed returns 404 rather than being advertised and then
failing.

`performance` deliberately advertises **no** capabilities in the catalog. It is
implemented and reachable, but not through `/agents/execute`, so offering
operations there would be a promise the endpoint cannot keep. Its description
points at the job API instead.

Automation drafts actions only. It performs no external side effects: no email
is sent, no calendar event is created. There is no Gmail, Google Calendar, or
scheduling integration in this repository.

The Performance Analyzer is modelled strictly as data analytics, with no
predictive or classification behaviour. It runs 9 analyzers over a dataset and
produces KPIs, period comparisons, trends, business insights, and 39
visualizations for the bundled Financials dataset.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env            # set JWT_SECRET_KEY; required in production
alembic upgrade head            # create the schema (organizations, users, refresh_tokens)
python bootstrap_admin.py --email admin@example.com --password 'YourStrongPass1!'
```

`bootstrap_admin.py` is a one-time CLI that creates the first organisation and
administrator. It takes the password as an argument and never stores it in
plain text; only the Argon2 hash is written. Re-running it is safe: it refuses
to create a second administrator for the same organisation.

Auth and database dependencies live in `requirements.txt`, so a plain API
install is enough to run every route in this document. The ML and
document-processing packages the agents need are installed separately from
`requirements-agents.txt` — see below.

### Agent prerequisites

All three agents need extra dependencies. Without them the API still runs; the
agents simply report unavailable.

```bash
# 1. Agent dependencies. This pulls roughly 2 GB of PyTorch and CUDA wheels,
#    which is why it is separate from requirements.txt.
pip install -r requirements.txt -r requirements-agents.txt

# 2. Ollama must be running with the model pulled. Install from
#    https://ollama.com, then:
ollama serve
ollama pull llama3.1:8b
```

The Ollama model tag must match `OLLAMA_MODEL`. Ollama is reached over HTTP; no
model is bundled with the packages.

The Knowledge Agent also downloads the `BAAI/bge-base-en-v1.5` embedding model
from HuggingFace on first use, roughly 440 MB, cached afterwards. This needs
network access once, and a writable HuggingFace cache.

The Performance Analyzer needs no model and no external service — pandas,
numpy, openpyxl, and matplotlib only. It reads a CSV or Excel file from disk.

Then enable the agents in `.env`:

```bash
KNOWLEDGE_AGENT_ENABLED=true
AUTOMATION_AGENT_ENABLED=true
PERFORMANCE_AGENT_ENABLED=true
```

Startup never fails because of an agent. If construction raises — missing
dependency, unreachable Ollama, unreadable Chroma directory — the adapter logs
the traceback and reports unavailable, and that agent's calls return 503.
Check the startup log for `knowledge_adapter_connect_failed` or
`automation_adapter_connect_failed` to see why.

Verify the agent is live:

```bash
curl http://127.0.0.1:8000/api/v1/agents
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

| Purpose | URL |
|---|---|
| API base | `http://127.0.0.1:8000/api/v1` |
| Interactive docs | `http://127.0.0.1:8000/docs` |
| OpenAPI schema | `http://127.0.0.1:8000/openapi.json` |

## Tests

```bash
pytest                                    # all tests
pytest tests/test_agents_api.py           # one file
pytest tests/test_registry.py -k unknown  # one test
pytest tests/conformance.py               # agent contract suite
```

Tests use fake agents (`tests/fakes.py`) and a stub Performance service. No GPU,
network, model download, or real dataset is required. Auth, user management,
tenant isolation, and migrations each have their own suites
(`test_auth_api.py`, `test_users_api.py`, `test_tenant_isolation.py`,
`test_migrations.py`); the auth tests run against a temporary SQLite database,
not a real service. Tests that genuinely need a live agent are opt-in and skip
unless the corresponding `*_AGENT_ENABLED` flag is set; see
`tests/test_agent_integration.py`.

## Lint and format

```bash
ruff check app tests
ruff check app tests --fix
ruff format app tests
mypy app
```

## Architecture

There are two execution paths, because the agents differ in how long they take.

```
Synchronous agents (Knowledge, Automation):

Frontend
   ↓
FastAPI  (app/main.py — CORS, middleware, error handlers, versioning)
   ↓
Routes  (app/api/v1/agents.py — HTTP only, no agent knowledge)
   ↓
Orchestrator  (app/services/orchestrator.py — resolve, dispatch, wrap)
   ↓
Registry  (app/agents/registry.py — name → adapter)
   ↓
Adapters  (app/agents/adapters — integration boundary)
   ↓
Agent services  (knowledge_agent/, automation_agent/ — dict-in, dict-out)
   ↓
Real agents  (knowledge_agent/, automation_agent/ in this repo)

Background-job agent (Performance):

Frontend
   ↓
Routes  (app/api/v1/performance.py — POST /jobs, GET /jobs/{id})
   ↓
JobManager  (app/services/job_manager.py — lifecycle, in-process store)
   ↓
PerformanceService  (performance_agent/service.py — dict-in, dict-out)
   ↓
Analyzers / visualization / insight engines  (in this repo)
```

Layering rules: routers never import agent implementations. The orchestrator
holds no agent logic. Coupling to real agent code lives in exactly two places:
`app/agents/adapters/` for the synchronous agents, and `app/services/job_manager.py`
for Performance.

```
app/
├── main.py              app factory, lifespan, CORS, middleware
├── models.py            SQLAlchemy 2.x models: Organization, User, RefreshToken
├── alembic/             database migrations (alembic upgrade head)
├── bootstrap_admin.py   one-time CLI to create the first administrator
├── api/
│   ├── deps.py          shared dependencies: auth, roles, registry, sessions
│   └── v1/
│       ├── router.py    aggregates v1 routers
│       ├── health.py    /health, /ready
│       ├── auth.py      /auth/login, /auth/refresh, /auth/logout, /auth/me
│       ├── users.py     /users (create, list, roles, activate, managers)
│       ├── agents.py    /agents, /agents/{name}, /agents/execute
│       ├── activity.py  /activity-history
│       ├── knowledge.py /knowledge/documents (multipart upload + list)
│       ├── automation.py /automation/directories (upload, list, detail)
│       └── performance.py  /performance/datasets, /performance/jobs, artifacts
├── core/
│   ├── config.py        pydantic-settings, no os.environ elsewhere
│   ├── database.py      async engine, session factory, lifespan dispose
│   ├── logging_config.py  console/JSON logging + request-id correlation
│   ├── exceptions.py    AppError hierarchy + centralized handlers
│   └── middleware.py    request id, timing log
├── schemas/
│   ├── common.py        APIResponse, ErrorDetail, health, UserPublic
│   ├── agent.py         agent info, execute request/response
│   ├── activity.py      activity record models
│   ├── knowledge.py     uploaded document models
│   ├── automation.py    uploaded employee directory models
│   └── performance.py   job request/response, job status enum
├── agents/
│   ├── base.py          AgentAdapter ABC, concurrency limiting, placeholder base
│   ├── registry.py      AgentRegistry
│   ├── factory.py       builds the default registry from settings
│   └── adapters/        knowledge, automation, performance
└── services/
    ├── orchestrator.py  dispatch only
    ├── activity_store.py  JSON-file activity history (local MVP)
    ├── document_upload.py  validates uploads, writes them under generated names
    ├── document_manifest.py  JSON metadata for uploaded documents
    ├── employee_directory.py  validates employee directories, resolves them
    ├── dataset_upload.py  browser dataset uploads; resolves dataset_id to a path
    └── job_manager.py   in-process background jobs for Performance
```

## API

### Authentication

Every response carries an `X-Request-ID` header and a `request_id` body field.
Most read and write routes accept an optional `Authorization: Bearer <access
token>`; management routes require it. The token model is deliberately split:

- **Access token** — short-lived JWT (default 15 minutes) returned in the
  login/refresh response body. Carry it as `Authorization: Bearer …`. It
  embeds the user id and a `token_version`, so bumping that version revokes
  every outstanding token for the user.
- **Refresh token** — 30-day credential stored in an `HttpOnly` cookie scoped
  to `/api/v1/auth`. Never readable from JavaScript. Each refresh rotates it
  atomically: only one concurrent request can consume a given token, and a
  reused or revoked token is refused with 401.

`POST /auth/refresh` and `POST /auth/logout` additionally require a trusted
`Origin` header (see `TRUSTED_ORIGINS`), so a cross-site page cannot ride the
cookie. In development the cookie is not `Secure`; in production it is.

Role dependencies guard the management API: `require_employee` (any signed-in
user), `require_manager` (manager or admin), `require_admin` (admin only). A
token whose `token_version` no longer matches the user is rejected as
revoked. Agent, upload, and activity routes use an *optional* principal: they
scope data to the caller's organisation when a token is present, and either
serve a restricted unauthenticated view or refuse, depending on the route —
they never widen access because a token was omitted.

Auth routes:

| Route | Auth | Behaviour |
|---|---|---|
| `POST /api/v1/auth/login` | none | Query params `email`, `password` (not a JSON body). On success returns the user profile plus `access_token` and sets the refresh cookie. Wrong email and wrong password are indistinguishable (`401 INVALID_CREDENTIALS`) so login is not an account-enumeration oracle. |
| `POST /api/v1/auth/refresh` | refresh cookie + trusted `Origin` | Rotates the refresh token and returns a new profile with a fresh `access_token`. Concurrent refreshes: one wins atomically, the loser gets 401 and must retry. |
| `POST /api/v1/auth/logout` | refresh cookie + trusted `Origin` | Revokes the refresh token and clears the cookie. |
| `GET /api/v1/auth/me` | Bearer access token | Returns the authenticated user's profile. |

The first administrator is created out-of-band with `bootstrap_admin.py`;
there is no public self-service registration. Admins create further users
through `POST /api/v1/users/`.

### `GET /api/v1/health`

Liveness. No auth, no dependencies checked.

```json
{
  "status": "ok",
  "app_name": "AI SaaS Platform API",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

### `GET /api/v1/ready`

Readiness of backend components only. Unconnected agents do **not** fail this
check, since the container is healthy even without agents. Returns 503 when a
backend component is missing.

```json
{
  "status": "ready",
  "checks": [
    { "name": "registry", "ready": true, "detail": "3 agents registered" },
    { "name": "agents", "ready": true, "detail": "0 of 3 agents connected" }
  ],
  "timestamp": "2026-01-01T00:00:00Z"
}
```

### `GET /api/v1/agents`

Catalog. The frontend can build its agent list from this alone. Note that
`performance` appears here with `capabilities: []`: it is listed so the client
knows the agent exists, but its operations live at `/performance/jobs`.

The example below is a **mixed configuration**: `KNOWLEDGE_AGENT_ENABLED=true`
and `AUTOMATION_AGENT_ENABLED=true`, with `PERFORMANCE_AGENT_ENABLED=false`.
That is why `available_count` is 2 rather than 3. Availability is per agent and
follows each flag independently:

| Flags | `available_count` | `performance` status |
|---|---|---|
all three false | 0 | `not_connected` |
Performance flag false, others true | 2 | `not_connected` |
all three true | 3 | `ready` |

```json
{
  "success": true,
  "data": {
    "agents": [
      {
        "name": "knowledge",
        "display_name": "Knowledge",
        "available": true,
        "capabilities": ["ingest_document", "query"],
        "status": "ready",
        "description": "Retrieval-augmented question answering ..."
      },
      {
        "name": "performance",
        "display_name": "Performance",
        "available": false,
        "capabilities": [],
        "status": "not_connected",
        "description": "Data analytics over datasets ... Served as background jobs at POST /api/v1/performance/jobs, not through this endpoint."
      }
    ],
    "total": 3,
    "available_count": 2
  },
  "message": "3 agents registered.",
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

### `GET /api/v1/agents/{agent_name}`

One agent's metadata. Unknown name → 404.

### `POST /api/v1/agents/execute`

Generic execution for the synchronous agents. The client names the agent and
operation explicitly; v1 does no LLM-based routing. Operations:

| Agent | Operations |
|---|---|
| `knowledge` | `ingest_document`, `query` |
| `automation` | `draft_action` |

`performance` is not served here. Its operations run as jobs — see below.

Request:

```json
{
  "agent": "knowledge",
  "operation": "query",
  "payload": { "question": "What is this document about?" },
  "metadata": null
}
```

Success (agent connected):

```json
{
  "success": true,
  "data": {
    "agent": "knowledge",
    "operation": "query",
    "data": { },
    "request_id": "5aa72667b1294e639f658fdd00d7a5cd",
    "duration_ms": 12.4,
    "timestamp": "2026-01-01T00:00:00Z"
  },
  "message": "Operation 'query' completed on 'knowledge'.",
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

Agent not connected, or an operation its endpoint does not serve → **503**:

```json
{
  "success": false,
  "error": {
    "code": "AGENT_UNAVAILABLE",
    "message": "Agent 'knowledge' is registered but its implementation is not connected yet.",
    "details": {
      "agent": "knowledge",
      "status": "not_implemented",
      "capabilities": ["ingest_document", "query"]
    }
  },
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

Any request naming `performance` returns this, because the generic endpoint
cannot run it. Use `/api/v1/performance/jobs` instead.

Missing payload keys return **422**, not 502. Operation-specific input rules
live in each adapter's `run()`, since `payload` is an arbitrary JSON object at
the API boundary:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Operation 'query' requires: question.",
    "details": {
      "agent": "knowledge",
      "operation": "query",
      "missing": ["question"]
    }
  },
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

### `POST /api/v1/users/`

Create a user in the authenticated admin's organisation. Admin role required.
Query params: `email`, `full_name`, optional `role` (default `employee`) and
`manager_id`. The password is generated server-side; the response includes
`temporary_password` exactly once so it can be delivered to the new user. Only
the Argon2 hash is stored. A duplicate email is **409**; a `manager_id` outside
the organisation is **409**.

### `GET /api/v1/users/`

List active users in the caller's organisation. Any authenticated user
(employee or higher). Employees see colleagues; managers and admins see their
team.

### `PATCH /api/v1/users/{user_id}?new_role=…`

Change a user's role. Admin only. The last active administrator in an
organisation cannot be demoted — the guard counts the target as well, so an
admin cannot demote themselves into a leaderless organisation. A role change
bumps the target's `token_version`, revoking their outstanding tokens.

### `POST /api/v1/users/{user_id}/activate` and `/deactivate`

Re-enable or disable an account. Admin only, same organisation. Deactivation
bumps `token_version`, so the user's existing access and refresh tokens stop
working immediately.

### `PATCH /api/v1/users/{user_id}/manager?manager_id=…`

Assign or clear a user's manager. Manager or admin. The manager must belong to
the same organisation. Omit `manager_id` (or send `null`) to remove it.

All user routes are organisation-scoped: a user in another organisation is
reported as **404** or refused with **409** depending on the route, never
mutated, and never confirmed to exist.

### `POST /api/v1/knowledge/documents`

Upload a document and index it into the Knowledge vector store. `multipart/form-data`
with a single `file` field. Accepts **PDF, DOCX, TXT**.

Returns **201 Created** only after the document has been extracted, chunked,
embedded, and added to Chroma:

```json
{
  "success": true,
  "data": {
    "document": {
      "document_id": "9f2c1d0b4a7e4c1f9b3d5e7a8c0d2f41",
      "filename": "Employee Handbook.pdf",
      "extension": ".pdf",
      "size_bytes": 1843200,
      "status": "indexed",
      "chunk_count": 142,
      "uploaded_at": "2026-10-13T14:22:01+05:30"
    },
    "message": "'Employee Handbook.pdf' indexed as 142 chunks."
  },
  "message": null,
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

No filesystem path appears in the response. The stored filename is internal and
is never returned.

Validation happens in three layers, because each catches a different lie:

| Check | Rejects with |
|---|---|
| Extension allowlist (`.pdf`, `.docx`, `.txt`) | 422 `VALIDATION_ERROR` |
| Size limit, enforced while streaming | 422 with `details.max_bytes` |
| Content signature and structure | 422 `VALIDATION_ERROR` |
| Zero bytes, or text with no content | 422 `VALIDATION_ERROR` |

The stored filename is generated server-side as `<uuid4>_<sanitized stem><ext>`
and opened with `O_EXCL`, so a client cannot choose where a file lands, cannot
traverse out of the upload directory, and cannot overwrite an earlier upload.

If ingestion fails, the stored file is deleted and the document is recorded in
the manifest with `"status": "failed"` rather than `"indexed"`. A failed upload
is never reported as a success, and never appears as a selectable document.

Status codes: 201 indexed, 422 rejected or produced no indexable text, 502 agent
failed, 503 Knowledge Agent not connected, 504 indexing timed out.

### `GET /api/v1/knowledge/documents`

List documents this instance has ingested, newest first. An empty manifest
returns an empty list rather than an error.

### Upload storage is a local MVP

Uploaded files live in `KNOWLEDGE_UPLOAD_DIR` on the machine running the API,
and metadata lives in a JSON manifest beside them. Both are gitignored. This is
a deliberate development choice, **not** deployment-ready storage:

- Files are not shared between instances, so a multi-worker or multi-host
  deployment will index a document on one instance and not find it on another.
- Storage is bounded only by disk. There is no quota, no retention policy, and
  no cleanup job.
- The manifest is a single JSON file, so concurrent writes across processes are
  not safe.

A deployment needs persistent shared storage (object storage or a volume) and a
real metadata store. Only `app/services/document_upload.py` and
`app/services/document_manifest.py` need to change; the router and the agent
pipeline do not, because the agent only ever sees a path.

There is **no delete operation**. A document can be uploaded and listed, but
nothing removes it from disk or from Chroma. Do not describe a document as
deleted or removed unless that endpoint is implemented.

### `POST /api/v1/automation/directories`

Upload an employee directory and validate every record. `multipart/form-data`
with a single `file` field. Accepts **JSON** and **CSV**.

Returns **201 Created** only after every record passed validation, and includes a
preview of the first 20 employees so the upload can be confirmed before use:

```json
{
  "success": true,
  "data": {
    "directory": {
      "directory_id": "9f2c1d0b4a7e4c1f9b3d5e7a8c0d2f41",
      "filename": "engineering_roster.csv",
      "format": "csv",
      "employee_count": 42,
      "size_bytes": 1843,
      "status": "ready",
      "uploaded_at": "2026-10-16T14:22:01+05:30"
    },
    "preview": [{ "name": "Aarti Rao", "email": "aarti.rao@example.com" }],
    "message": "'engineering_roster.csv' accepted with 42 employee(s)."
  },
  "message": null,
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

**Formats.** JSON must be an array of objects. CSV needs a header row; column
names are matched case-insensitively and a UTF-8 BOM is stripped, so a sheet
exported from a spreadsheet is accepted as-is. Only `name` and `email` are read.
**Any other column is discarded when the file is parsed**, so an uploaded roster
cannot introduce a field that some later layer might echo back to a browser.

XLSX is deliberately **not** supported. Reading it needs a dependency that is
not part of an API-only install, and adding one would make the Automation
adapter unavailable on deployments that never upload a spreadsheet.

Validation happens in four layers, because each catches a different problem:

| Check | Rejects with |
|---|---|
| Extension allowlist (`.json`, `.csv`), before any byte is read | 422 `VALIDATION_ERROR` |
| Size limit, enforced while streaming, and NUL bytes in the content | 422 with `details.max_bytes` |
| Structure: JSON array of objects, CSV header with both columns | 422 `VALIDATION_ERROR` |
| Per record: `name` and `email` present and non-blank, plausible email, no duplicate name, no duplicate email | 422 with `details.row` and `details.field` |
| Empty directory, or more than `AUTOMATION_MAX_DIRECTORY_EMPLOYEES` | 422 `VALIDATION_ERROR` |

Duplicate names are rejected rather than resolved: attendee matching falls back
to a first name, so two people sharing one name would silently resolve every
mention to the first record found.

Error `details` carry the row index and field name, never the offending value and
never a filesystem path. The stored filename is generated server-side as
`<uuid4>_<sanitized stem><ext>` and opened with `O_EXCL`, so a client cannot
choose where a file lands, cannot traverse out of the upload directory, and
cannot overwrite an earlier upload. A file that fails validation is removed
before the error is returned.

Status codes: 201 accepted, 422 rejected, 503/504 not applicable (no agent runs).

### `GET /api/v1/automation/directories`

List directories this instance has accepted, newest first. An empty manifest
returns an empty list rather than an error.

### `GET /api/v1/automation/directories/{directory_id}`

Return the directory summary and its full employee records, with an
`employees_truncated` flag. An unknown id and an id whose stored file is gone
are reported identically as **404 `DIRECTORY_NOT_FOUND`**, so the response never
confirms whether a given identifier ever existed. A stored file that no longer
parses returns **422**; it is never quietly ignored.

### Drafting against a selected directory

`POST /api/v1/agents/execute` for the Automation Agent accepts one **optional**
payload key alongside `instruction`:

```json
{
  "agent": "automation",
  "operation": "draft_action",
  "payload": {
    "instruction": "Schedule a sprint planning on 5 March with Aarti",
    "directory_id": "9f2c1d0b4a7e4c1f9b3d5e7a8c0d2f41"
  }
}
```

Omit `directory_id` (or send `null` or a blank string) and the packaged
`automation_agent/data/employees.json` is used exactly as before. The default
directory is **never** replaced or overwritten by an upload.

An unknown or unusable `directory_id` returns an error. It deliberately does
**not** fall back to the default directory: a silent fall-back would produce a
draft addressed to the wrong people while reporting success.

The result gains a `directory` block naming the roster that was used, so a
caller can tell which directory produced the recipients:

```json
"directory": { "directory_id": "9f2c1d0b…", "source": "uploaded", "employee_count": 42 }
```

`source` is `default` when no directory was selected. Recipients are reduced to
`name` and `email` at the adapter boundary, so no other field from an uploaded
roster can reach a client.

**Parser limitations.** A directory changes *which employees* a request can
resolve, nothing else. The parser still extracts a fixed set of fields — title,
date, time, venue, attendees — by regex. There is **no department, role, or team
parsing**, because the employee schema has never had those fields and the parser
has no code path for them. Attendee matching is a case-insensitive substring
match of the full name, then of the first name only; a bare surname resolves to
nobody, which is deliberate.

**Draft-only.** A directory changes recipients, never behaviour. The agent still
drafts and never sends mail or schedules a meeting.

### Employee directory storage is a local MVP

Uploaded directories live in `AUTOMATION_UPLOAD_DIR` on the machine running the
API, and metadata lives in a JSON manifest beside them. Both are gitignored. This
inherits every limitation of the Knowledge upload storage described above:
files are not shared between instances, storage is bounded only by disk, and the
single-file manifest is unsafe for concurrent cross-process writes. A deployment
needs persistent shared storage and a real metadata store.

There is **no delete operation** for an employee directory, for the same reason
there is none for a document.

### `POST /api/v1/performance/datasets`

Upload a dataset from a browser. Returns **201 Created** with the id that
identifies it. That id is what a job request refers to; the stored path is never
returned.

Accepted extensions are `.csv` and `.xlsx`. `.xls` is **not** accepted: the
loader routes it to the `xlrd` engine, which is not a dependency, so it would be
accepted here only to fail later as an opaque job error. It is refused up front
with a message that names the formats that do work.

The file is streamed to disk with the size limit enforced **during** the write,
so an oversized upload is abandoned rather than buffered, and a rejected upload
leaves no file behind. After the write the file is read back through a **bounded**
preview — header plus five rows — which proves the parser can open it and yields
its real column names without loading the whole dataset. An XLSX must also be a ZIP
container, so a CSV renamed `.xlsx` is caught before the parser sees it.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/performance/datasets \
  -F 'file=@Financials.csv'
```

```json
{
  "success": true,
  "data": {
    "dataset": {
      "dataset_id": "6a1f2c8e9d0b4c7f8a1b2c3d4e5f6071",
      "filename": "Financials.csv",
      "format": "csv",
      "size_bytes": 20480,
      "status": "ready",
      "column_names": ["date", "sales", "profit"],
      "column_count": 3,
      "is_sample": false,
      "available": true,
      "uploaded_at": "2026-01-01T00:00:00Z"
    },
    "message": "'Financials.csv' is ready to analyse."
  },
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

`column_names` are **normalized** — trimmed, lowercased, spaces turned into
underscores — because that is what the analyzers look for, so what the client is
told matches what a later job will actually use.

Rejected with 422 `VALIDATION_ERROR`: an unsupported extension, a file over
`PERFORMANCE_MAX_UPLOAD_BYTES`, an empty file, a mislabelled container, a CSV that
is not UTF-8, a header row that names no column, a file that holds a header but no
data rows, or a file the parser cannot open. Messages never contain a filesystem
path or a traceback.

### `GET /api/v1/performance/datasets`

List the datasets a job may run against: the packaged sample first, then this
instance's uploads, newest first. Also reports the server's own size limit and
accepted formats so a client does not have to hardcode them.

```json
{
  "datasets": [
    {
      "dataset_id": "sample",
      "filename": "Financials_standardized.csv",
      "format": "csv",
      "is_sample": true,
      "available": true
    }
  ],
  "total": 1,
  "max_upload_bytes": 26214400,
  "supported_extensions": [".csv", ".xlsx"]
}
```

### `POST /api/v1/performance/jobs`

Submit a Performance Analyzer job. Returns **202 Accepted** immediately; the
analysis runs on a worker thread while the client polls. Supported operations:
`load_dataset`, `compute_kpis`, `compare_periods`, `analyze`, `visualize`.

A job names its dataset in one of two ways, and exactly one must be present.

**`dataset_id` — preferred.** An id from the upload route, or the reserved value
`sample` for the packaged dataset. The server resolves the id to a path it
controls, so no client-supplied string is ever used as a filesystem path. An
unknown id, a tampered id, or an id whose file was deleted fails the request with
404 `DATASET_NOT_FOUND` **before a job is created**. There is no fallback: if the
dataset cannot be resolved, no job runs, because silently analysing a different
file than the one selected would report success for the wrong data.

```json
{
  "operation": "analyze",
  "dataset_id": "6a1f2c8e9d0b4c7f8a1b2c3d4e5f6071"
}
```

**`file_path` — the pre-existing server-side workflow.** A path on the **server**,
not an upload, retained for callers that index a file already on disk. Relative
paths resolve from `backend/`. Supplying both references is rejected rather than
resolved.

```json
{
  "operation": "analyze",
  "file_path": "performance_agent/data/Financials_standardized.csv"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "job_id": "b1c4b7451429488dac207595220b6e36",
    "status": "queued",
    "operation": "analyze",
    "created_at": "2026-01-01T00:00:00Z"
  },
  "message": "Performance job created.",
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

Operation behaviour:

| Operation | Returns |
|---|---|
| `load_dataset` | Dataset metadata: row count, column count, column names. Never the dataset itself. |
| `compute_kpis` | Headline KPI blocks: totals, margins, target achievement. |
| `compare_periods` | Period comparison across consecutive years on overlapping months. |
| `analyze` | All 9 analyzers plus business insights. No charts written. |
| `visualize` | Chart metadata. Renders 39 PNGs for the bundled dataset. |

Note on `load_dataset`: the service reports the path it read, and the job runner
reduces that to a bare filename before it reaches a client. An uploaded dataset
lives under the upload directory, so returning the path as given would disclose
the server's directory layout.

### `GET /api/v1/performance/jobs/{job_id}`

Poll a job. Unknown id → 404 `JOB_NOT_FOUND`.

Lifecycle: `queued` → `running` → `completed` or `failed`.

```json
{
  "success": true,
  "data": {
    "job_id": "b1c4b7451429488dac207595220b6e36",
    "status": "completed",
    "operation": "analyze",
    "created_at": "2026-01-01T00:00:00Z",
    "started_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:00:08Z",
    "result": { },
    "error": null
  },
  "message": "Performance job 'completed'.",
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

A failed job carries a sanitized `error` instead of a `result`:

```json
{
  "job_id": "b1c4b7451429488dac207595220b6e36",
  "status": "failed",
  "result": null,
  "error": "Input file not found: <path>"
}
```

Filesystem paths are redacted from error text before it reaches a client. The
unmodified text is logged server-side.

### Performance visualizations

Charts are written per job:

```
performance_agent/results/visualizations/jobs/<job_id>/visualizations/
```

The API returns metadata only — `name`, `filename`, `size_bytes`. It never
exposes an absolute filesystem path.

### `GET /api/v1/performance/jobs/{job_id}/artifacts/{filename}`

Stream one PNG a `visualize` job generated. The filename must be one the job
itself reported in its `visualizations` result, and the resolved path must sit
inside that job's visualization directory. Ownership is enforced: a chart
belonging to a job in another organisation is not downloadable, and an
unauthenticated caller owns nothing. Unknown job, foreign job, and unknown
artifact are all **404 `JOB_NOT_FOUND`**, so the response never distinguishes
"this chart does not exist" from "you may not see it". No
`Content-Disposition` filename is set, so the server path is never echoed.

### Performance dataset storage is a local MVP

Uploaded datasets are stored under `PERFORMANCE_UPLOAD_DIR`, separate from
`performance_agent/data/`, so an upload can never overwrite a packaged sample.
Stored names are generated (`<uuid>_<safe-stem><ext>`), written with an exclusive
create, and the original filename is kept only as display metadata. The manifest is
a single JSON file, as with the other uploads.

This inherits every limitation of the upload storage described above, and it is
worth stating plainly: uploaded datasets are **not shared between instances**, they
do **not survive** replacing the container or the checkout because nothing backs
the directory, and there is **no delete route**, so the directory grows until an
operator removes files by hand. A deployment needs persistent shared storage and a
real metadata store. Nothing else about the pipeline changes when that happens,
because the job runner only ever receives a path.

The sample dataset is the exception: it lives in the agent package and is resolved
from configuration, so it is always available and always the same file.

### Performance job limitations

Job state is held in memory in the API process. There is no database, Redis, or
Celery behind it. Two consequences:

- Jobs do not survive a process restart.
- Multi-worker deployments are not supported for polling. A client that polls a
  job can reach a worker that never saw it, and receive 404.

Treat the job API as single-process only until it is moved behind persistent
storage.

### `GET /api/v1/activity-history`

Recent agent activity, newest first, capped at `MAX_RECORDS` (500). Each
record is a lightweight metadata event — *that* an operation ran and how it
ended — never the agent's output: no answers, no drafted bodies, no chart
data, no filesystem paths. Query param `limit` (1–500, default 100).

Records are written by the agent execution paths themselves, not through this
router, so a client cannot fabricate history. When a token is present the
result is scoped to that user's organisation. An unauthenticated caller
receives an empty list, never the global record. The store is a JSON file on
disk (a local MVP, process-local lock, atomic write) — same single-instance
caveats as the upload manifests.

### Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Login failed; never distinguishes unknown email from wrong password |
| 401 | `HTTP_401` | Missing, expired, or revoked access token (from the auth dependency) |
| 403 | `FORBIDDEN` | Authenticated, but the role or scope is insufficient |
| 404 | `AGENT_NOT_FOUND` | No agent registered under that name |
| 404 | `OPERATION_NOT_FOUND` | Agent does not advertise that operation |
| 404 | `JOB_NOT_FOUND` | No Performance job with that id (also foreign/unknown artifact) |
| 404 | `DIRECTORY_NOT_FOUND` | Unknown, deleted-file, or foreign employee directory |
| 404 | `DATASET_NOT_FOUND` | Unknown, tampered, or no-longer-present dataset id |
| 409 | `HTTP_409` | Conflict: duplicate email, cross-organisation manager, last-admin demotion |
| 422 | `VALIDATION_ERROR` | Malformed body or failed schema validation |
| 500 | `INTERNAL_ERROR` | Unexpected server fault (details never exposed) |
| 502 | `AGENT_EXECUTION_FAILED` | Connected agent raised |
| 503 | `AGENT_UNAVAILABLE` | Agent registered but not executable here |
| 504 | `AGENT_TIMEOUT` | Agent exceeded its timeout |

Every response carries an `X-Request-ID` header, and every body includes
`request_id`. Send your own `X-Request-ID` to trace a request end to end.

## Configuration

All settings live in `app/core/config.py`; no other module reads the
environment. See `.env.example`. Notable keys:

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `test` / `staging` / `production` |
| `DEBUG` | `false` | Verbose mode; must be false in production |
| `API_V1_PREFIX` | `/api/v1` | Versioned API mount point |
| `CORS_ORIGINS` | localhost:3000, :5173 | Allowed browser origins |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `console` | `LOG_FORMAT=json` for shipping |
| `*_AGENT_ENABLED` | `false` | Set true to attempt constructing that agent at startup |
| `KNOWLEDGE_CHROMA_PATH` | `knowledge_agent/data/chroma_db` | Vector store directory; relative paths resolve from `backend/` |
| `KNOWLEDGE_UPLOAD_DIR` | `uploads/knowledge` | Where uploaded documents are stored; local disk, see below |
| `KNOWLEDGE_UPLOAD_MANIFEST_PATH` | `uploads/knowledge/documents.json` | Document metadata manifest |
| `KNOWLEDGE_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Upload size limit, enforced while streaming |
| `AUTOMATION_UPLOAD_DIR` | `uploads/automation` | Where uploaded employee directories are stored; local disk, see below |
| `AUTOMATION_UPLOAD_MANIFEST_PATH` | `uploads/automation/directories.json` | Employee directory metadata manifest |
| `AUTOMATION_MAX_UPLOAD_BYTES` | `2097152` (2 MB) | Employee directory upload limit, enforced while streaming |
| `AUTOMATION_MAX_DIRECTORY_EMPLOYEES` | `5000` | Largest accepted employee count in one directory |
| `PERFORMANCE_UPLOAD_DIR` | `uploads/performance` | Where uploaded datasets are stored; local disk, see below |
| `PERFORMANCE_UPLOAD_MANIFEST_PATH` | `uploads/performance/datasets.json` | Dataset metadata manifest |
| `PERFORMANCE_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Dataset upload limit, enforced while streaming |
| `PERFORMANCE_SAMPLE_DATASET_PATH` | `performance_agent/data/Financials_standardized.csv` | Dataset exposed to browsers as `sample`; resolved server-side |
| `KNOWLEDGE_EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | HuggingFace embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model tag used for generation |
| `KNOWLEDGE_AGENT_TIMEOUT_SECONDS` | `300` | Per-operation budget; exceeding it returns 504 |
| `AUTOMATION_AGENT_TIMEOUT_SECONDS` | `180` | Per-operation budget; exceeding it returns 504 |
| `PERFORMANCE_AGENT_TIMEOUT_SECONDS` | `600` | Currently **not enforced** — see below |
| `AGENT_MAX_CONCURRENCY` | `4` | Agent operations running at once, across all agents |
| `DATABASE_URL` | `sqlite:///./app.db` | SQLAlchemy URL; `sqlite:///` and `postgresql://` both accepted (async drivers) |
| `JWT_SECRET_KEY` | *(empty)* | HS256 signing key for access tokens; **required in production** — startup refuses without it |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token lifetime; enforced on every request |
| `TRUSTED_ORIGINS` | localhost:3000, :5173 | Origins allowed to call `/auth/refresh` and `/auth/logout` (cookie CSRF check) |
| `SAMESITE` | `lax` | Refresh-cookie `SameSite` scope; `none` requires HTTPS |

Enabling an agent makes the API *attempt* construction, not guarantee it. A
failure degrades that agent to unavailable rather than blocking startup, so
`is_available()` reports real state rather than the flag.

Inference is CPU-bound, so the timeout defaults are generous and
`AGENT_MAX_CONCURRENCY` is deliberately low. A timed-out agent thread cannot be
killed from outside, so it keeps its concurrency slot until it actually
finishes; raising the limit buys no extra throughput on a small machine and
only adds context switching. Performance jobs are bounded by the same
`AGENT_MAX_CONCURRENCY`.

`PERFORMANCE_AGENT_ENABLED` controls only the agent's catalog entry. The
Performance job API does not consult it: jobs run whether or not the catalog
lists the agent as available.

`PERFORMANCE_AGENT_TIMEOUT_SECONDS` is declared but **currently not enforced**.
Nothing in the job runner reads it, and a job has no execution time limit: it
runs until it completes or fails. There is therefore no 504 for a Performance
job. The Knowledge and Automation timeouts above are enforced by the adapter
base class and do return 504. Treat the Performance setting as reserved until a
limit is added.

Startup fails fast if `ENVIRONMENT=production` with `DEBUG=true`, a wildcard
CORS origin, or an empty `JWT_SECRET_KEY`.

## Logging

Human-readable by default, JSON with `LOG_FORMAT=json`. Every record carries the
request id. Logged: startup, per-request method/path/status/duration, agent
registration, agent selection, agent execution outcome, and failures with full
tracebacks server-side. Credentials and request bodies are not logged.

## How the adapters work

`AgentAdapter` (`app/agents/base.py`) defines the integration seam:

```python
name            # stable identifier
capabilities()  # advertised operations
is_available()  # is a real implementation connected?
execute(op, payload)   # async; runs the agent off the event loop
run(op, payload)       # override this — call the real agent here
```

`execute()` runs `run()` in a worker thread under a timeout, so a slow agent
will not block the event loop. Two details matter when connecting a real agent:

**Availability is observed, not configured.** Knowledge and Automation attempt
construction in `__init__` and set `is_available()` from the outcome. A failure
is logged and degrades to unavailable. `is_available()` deliberately performs
no network probe: the agent catalog calls it for every agent on every request,
so a liveness check there would add latency to every call. A dead Ollama server
surfaces as a 502 on execute instead.

**Concurrency is bounded across agents.** A worker thread cannot be cancelled
mid-inference, so each call holds a slot from a shared
`CapacityLimiter` (`AGENT_MAX_CONCURRENCY`) that is released by the thread
itself, not by the caller. A timed-out call therefore keeps its slot until its
thread genuinely finishes, which converts unbounded background CPU burn into a
bounded queue. The limiter is per event loop, since one belongs to the loop
that created it.

`PerformanceAgentAdapter` is not an execution path. It advertises no
capabilities, reports `is_available() == False`, and its description points at
the job API. It keeps the agent visible in the catalog without implying it can
be run through `/agents/execute`.

## Adding an agent

Knowledge and Automation follow these steps and are the reference.

1. Inspect the implementation and note its entry point, whether it is blocking,
   and what it returns.
2. Add a service class with a dict-in, dict-out interface. Keep `main.py` as a
   dev script; services never print or read the terminal.
3. Override `run()` in the matching adapter to validate the payload, then call
   the service and return its dict. Raise `ValidationFailedError` for missing
   required keys so bad input returns 422 rather than 502.
4. Attempt service construction in the adapter's `__init__` inside a try block,
   including the import. Agent dependencies are optional, so an `ImportError`
   must degrade to unavailable rather than crash startup.
5. Set the agent's `*_AGENT_ENABLED=true` in `.env`.
6. Trim `ADVERTISED_CAPABILITIES` to the operations that actually exist.
   Declaring an operation that 404s at runtime is worse than not declaring it.
7. Run `pytest tests/conformance.py` — the contract every adapter must pass.
8. Verify via `POST /api/v1/agents/execute`.

No route or schema changes are expected. `app/agents/adapters/` is the only
backend directory that should need edits.

Performance took a different route because it is slow enough that blocking a
request on it is the wrong shape: a service class, then a `JobManager` and a
job router, with no adapter `run()` override at all. An agent that takes seconds
rather than milliseconds should follow that pattern instead.

## Not implemented (future phases)

Authentication, RBAC, user management, and database persistence are
implemented (see above). Still pending:

- A durable or shared file store for the three upload directories and the
  activity-history JSON file (all local MVPs today)
- Document, directory, and dataset deletion endpoints
- A persistent job store so Performance jobs survive restarts and work across
  multiple workers (no Celery, Redis, or database-backed queue yet)
- Streaming responses (SSE) for long agent operations
- Rate limiting
- LLM-based agent routing

To add a synchronous agent: implement `AgentAdapter`, register it in
`app/agents/factory.py`, and add a description in `app/api/v1/agents.py`. No
new endpoints are required.