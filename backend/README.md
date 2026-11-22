# Backend — AI SaaS Platform

FastAPI backend foundation for the AI SaaS Platform.

**All four agents are implemented and live in this repository.** Knowledge, Automation, and Employee Insights run synchronously through `POST /api/v1/agents/execute` (Employee Insights also exposes `/api/v1/employee-insights/*`). The
Performance Analyzer is implemented too, but its analysis is CPU-bound and long
running, so it is served through its own background-job API at
`/api/v1/performance/jobs` instead of the generic execution endpoint.

Each agent exposes a thin dict-in, dict-out service that the backend calls. The
API reports each agent's status honestly, including when an agent is enabled but
fails to initialize.

The backend also implements JWT authentication with rotating HttpOnly refresh
cookies, organisation-scoped multi-tenancy, role-based access control
(`employee` / `manager` / `admin`), user management, database persistence
(SQLAlchemy 2.x + Alembic), browser upload APIs for the agents, an
employee directory service with organization-scoped resolution, and an
activity-history feed.

## Agents

| Agent | Purpose | Status | Capabilities | Served at |
|---|---|---|---|---|
| `knowledge` | RAG question answering over PDF/DOCX/TXT documents | Connected when enabled | `ingest_document`, `query` | `/agents/execute` |
| `automation` | Interprets productivity requests and drafts actions | Connected when enabled | `draft_action`, `draft_html`, `send_email` | `/agents/execute` |
| `performance` | Data analytics: KPIs, comparisons, trends, insights | Connected when enabled | `[]` (see below) | `/performance/jobs` |
| `employee_insights` | Employee feedback sentiment analysis and analytics | Connected when enabled | `extract_feedback`, `employee_summary`, `sync_gmail` | `/agents/execute`, `/employee-insights/*` |

Capabilities listed above are the ones that actually work through that agent's
endpoint. Anything not listed returns 404 rather than being advertised and then
failing.

`performance` deliberately advertises **no** capabilities in the catalog. It is
implemented and reachable, but not through `/agents/execute`, so offering
operations there would be a promise the endpoint cannot keep. Its description
points at the job API instead.

Automation drafts actions only. It performs no external side effects: no email
is sent, no calendar event is created. There is no Gmail, Google Calendar, or
scheduling integration in this repository. The Automation Agent supports
organization-scoped employee directory resolution and source-aware recipient
selection, but email sending requires explicit manager/admin confirmation through
the backend `send_email` operation.

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
administrator. It takes the password as an argument and never stores it in plain
text; only the Argon2 hash is written. Re-running it is safe: it refuses to
create a second administrator for the same organisation.

Auth and database dependencies live in `requirements.txt`, so a plain API
install is enough to run every route in this document. The ML and
document-processing packages the agents need are installed separately from
`requirements-agents.txt` — see below.

### Agent prerequisites

All four agents need extra dependencies. Without them the API still runs; the
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
the traceback and reports unavailable, and that agent's calls return 503. Check
the startup log for `knowledge_adapter_connect_failed` or
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

The **Automation directory resolution tests** (`test_automation_directory_resolution.py`) verify
organization-scoped roster resolution, inactive employee exclusion, and the
strict packaged-directory fallback behavior.

The **Tenant isolation tests** (`test_tenant_isolation.py`) verify that
Organization A never receives Organization B's employees.

## Lint and format

```bash
ruff check app tests
ruff check app tests --fix
ruff format app tests
mypy app
```

## Architecture

There are two execution paths, because the agents differ in how long they take.

```text
Synchronous agents (Knowledge, Automation, Employee Insights):

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
│       ├── activity.py  /activity-history
│       ├── knowledge.py /knowledge/documents (multipart upload + list)
│       ├── automation.py /automation/directories (upload, list, detail)
│       ├── agents.py    /agents, /agents/{name}, /agents/execute
│       ├── performance.py  /performance/datasets, /performance/jobs, artifacts
│       └── activity.py  /activity-history
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

The first administrator is created out-of-band with `bootstrap_admin.py`; there is
no public self-service registration. Admins create further users through
`POST /api/v1/users/`.

### API Endpoints (selected)

#### `GET /api/v1/health`

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

#### `GET /api/v1/ready`

Readiness of backend components only. Unconnected agents do **not** fail this
check, since the container is healthy even without agents. Returns 503 when a
backend component is missing.

```json
{
  "status": "ready",
  "checks": [
    { "name": "registry", "ready": true, "detail": "4 agents registered" },
    { "name": "agents", "ready": true, "detail": "0 of 4 agents connected" }
  ],
  "timestamp": "2026-01-01T00:00:00Z"
}
```

#### `GET /api/v1/agents`

Catalog. The frontend can build its agent list from this alone. Note that
`performance` appears here with `capabilities: []`: it is listed so the client
knows the agent exists, but its operations live at `/performance/jobs`.

| Flags | `available_count` | `performance` status |
|---|---|---|
| all three false | 0 | `not_connected` |
| Performance flag false, others true | 2 | `not_connected` |
| all three true | 3 | `ready` |

#### `GET /api/v1/agents/{agent_name}`

One agent's metadata. Unknown name → 404.

#### `POST /api/v1/agents/execute`

Generic execution for the synchronous agents. The client names the agent and
operation explicitly; v1 does no LLM-based routing. Operations:

| Agent | Operations |
|---|---|
| `knowledge` | `ingest_document`, `query` |
| `automation` | `draft_action` |

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

Missing payload keys return **422**, not 502. Operation-specific input rules
live in each adapter's `run()`, since `payload` is an arbitrary JSON object at
the API boundary.

#### `POST /api/v1/automation/directories`

Upload an employee directory and validate every record. `multipart/form-data`
with a single `file` field. Accepts **JSON** and **CSV**.

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

Validation happens in four layers:

| Check | Rejects with |
|---|---|
| Extension allowlist (`.json`, `.csv`), before any byte is read | 422 `VALIDATION_ERROR` |
| Size limit, enforced while streaming, and NUL bytes in the content | 422 with `details.max_bytes` |
| Structure: JSON array of objects, CSV header with both columns | 422 `VALIDATION_ERROR` |
| Per record: `name` and `email` present and non-blank, plausible email, no duplicate name, no duplicate email | 422 with `details.row` and `details.field` |

Duplicate names are rejected rather than resolved: attendee matching falls back
to a first name, so two people sharing one name would silently resolve every
mention to the first record found.

Error `details` carry the row index and field name, never the offending value and
never a filesystem path.

Status codes: 201 accepted, 422 rejected, 503/504 not applicable (no agent runs).

#### `GET /api/v1/automation/directories`

List directories this instance has accepted, newest first. An empty manifest
returns an empty list rather than an error.

#### `GET /api/v1/automation/directories/{directory_id}`

Return the directory summary and its full employee records, with an
`employees_truncated` flag. An unknown id and an id whose stored file is gone
are reported identically as **404 `DIRECTORY_NOT_FOUND`**, so the response never
confirms whether a given identifier ever existed.

#### `POST /api/v1/agents/execute` for Automation Agent

Accepts one **optional** payload key alongside `instruction`:

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

#### Employee Directory API

#### `GET /api/v1/automation/employees`

List active employees in the authenticated organization. Requires manager or admin role.

```http
GET /api/v1/automation/employees
Authorization: Bearer <jwt-token>
```

Returns active employees filtered by the authenticated user's organization.

### Employee Directory API (Phase 4, updated)

> Phase 4 final: AutomationAgent recipient selection uses authenticated organization active `User` records by UUID. No packaged `employees.json` fallback. No AutomationAgent uploaded-directory recipient selection. `/automation/directories` remains shared legacy infrastructure pending dependency analysis.

| Endpoint | Method | Auth | RBAC | Description |
|---|---|---|---|---|
| `/api/v1/automation/employees` | `GET` | JWT required | Manager/Admin | List active users in the authenticated user's organization. Organization ID is derived from the authenticated principal; client-supplied IDs are ignored. |

Response: 200 with list of active users, 403 if role insufficient, 401 if no token.

### Configuration

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
| `KNOWLEDGE_CHROMA_PATH` | `knowledge_agent/data/chroma_db` | Vector store directory |
| `KNOWLEDGE_UPLOAD_DIR` | `uploads/knowledge` | Where uploaded documents are stored |
| `KNOWLEDGE_UPLOAD_MANIFEST_PATH` | `uploads/knowledge/documents.json` | Document metadata manifest |
| `KNOWLEDGE_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Upload size limit |
| `AUTOMATION_UPLOAD_DIR` | `uploads/automation` | Where uploaded employee directories are stored |
| `AUTOMATION_UPLOAD_MANIFEST_PATH` | `uploads/automation/directories.json` | Employee directory metadata manifest |
| `AUTOMATION_MAX_UPLOAD_BYTES` | `2097152` (2 MB) | Employee directory upload limit |
| `AUTOMATION_MAX_DIRECTORY_EMPLOYEES` | `5000` | Largest accepted employee count in one directory |
| `PERFORMANCE_UPLOAD_DIR` | `uploads/performance` | Where uploaded datasets are stored |
| `PERFORMANCE_UPLOAD_MANIFEST_PATH` | `uploads/performance/datasets.json` | Dataset metadata manifest |
| `PERFORMANCE_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Dataset upload limit |
| `PERFORMANCE_SAMPLE_DATASET_PATH` | `performance_agent/data/Financials_standardized.csv` | Dataset exposed to browsers as `sample` |
| `KNOWLEDGE_EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | HuggingFace embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model tag used for generation |
| `KNOWLEDGE_AGENT_TIMEOUT_SECONDS` | `300` | Per-operation budget; exceeding it returns 504 |
| `AUTOMATION_AGENT_TIMEOUT_SECONDS` | `180` | Per-operation budget; exceeding it returns 504 |
| `PERFORMANCE_AGENT_TIMEOUT_SECONDS` | `600` | Currently **not enforced** |
| `AGENT_MAX_CONCURRENCY` | `4` | Agent operations running at once, across all agents |
| `DATABASE_URL` | `sqlite:///./app.db` | SQLAlchemy URL; `sqlite:///` and `postgresql://` both accepted |
| `JWT_SECRET_KEY` | *(empty)* | HS256 signing key for access tokens; **required in production** |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token lifetime |
| `TRUSTED_ORIGINS` | localhost:3000, :5173 | Origins allowed to call `/auth/refresh` and `/auth/logout` |
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

### How the adapters work

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

### Adding an agent

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

### Employee Directory Service (Phase 4, updated)

The backend provides an organization-scoped employee directory service:

- **`list_active_users_by_organization()`** in `backend/app/services/employee_directory.py`
  - Uses the existing SQLAlchemy User model; no new tables, columns, or migrations
  - Filters users by `organization_id` derived from the authenticated principal
  - Returns only active (`is_active=True`) users
  - Strict fallback: when `organization_id` is present but no database session
    is available, returns an empty roster (not the packaged fallback directory)
  - When no `organization_id` is present, returns the packaged default directory

- **Organization isolation**: User queries always filter by the authenticated
  user's `organization_id`. Client-supplied organization IDs are never trusted.

- **RBAC**: `GET /api/v1/automation/employees` requires manager or admin role.

- **Session propagation**: Session is threaded through the complete call chain
  (API → orchestrator → adapter → service). When the session is available,
  organization-scoped queries use it. When absent with org context, strict
  empty roster is returned.

### Not implemented (future phases)

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