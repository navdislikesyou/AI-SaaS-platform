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
cp .env.example .env            # optional; defaults work without it
```

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
network, model download, or real dataset is required. Tests that genuinely need
a live agent are opt-in and skip unless the corresponding `*_AGENT_ENABLED` flag
is set; see `tests/test_agent_integration.py`.

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
├── api/
│   ├── deps.py          shared dependencies (auth seam lives here)
│   └── v1/
│       ├── router.py    aggregates v1 routers
│       ├── health.py    /health, /ready
│       ├── agents.py    /agents, /agents/{name}, /agents/execute
│       ├── knowledge.py /knowledge/documents (multipart upload + list)
│       └── performance.py  /performance/jobs, /performance/jobs/{job_id}
├── core/
│   ├── config.py        pydantic-settings, no os.environ elsewhere
│   ├── logging_config.py  console/JSON logging + request-id correlation
│   ├── exceptions.py    AppError hierarchy + centralized handlers
│   └── middleware.py    request id, timing log
├── schemas/
│   ├── common.py        APIResponse, ErrorDetail, health, readiness
│   ├── agent.py         agent info, execute request/response
│   ├── knowledge.py     uploaded document models
│   └── performance.py   job request/response, job status enum
├── agents/
│   ├── base.py          AgentAdapter ABC, concurrency limiting, placeholder base
│   ├── registry.py      AgentRegistry
│   ├── factory.py       builds the default registry from settings
│   └── adapters/        knowledge, automation, performance
└── services/
    ├── orchestrator.py  dispatch only
    ├── document_upload.py  validates uploads, writes them under generated names
    ├── document_manifest.py  JSON metadata for uploaded documents
    └── job_manager.py   in-process background jobs for Performance
```

## API

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

### `POST /api/v1/performance/jobs`

Submit a Performance Analyzer job. Returns **202 Accepted** immediately; the
analysis runs on a worker thread while the client polls. Supported operations:
`load_dataset`, `compute_kpis`, `compare_periods`, `analyze`, `visualize`.

`file_path` is a path on the **server**, not an upload. Supported extensions are
`.csv`, `.xlsx`, and `.xls`. Relative paths resolve from `backend/`.

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
exposes an absolute filesystem path. There is no endpoint that serves the chart
files yet.

### Performance job limitations

Job state is held in memory in the API process. There is no database, Redis, or
Celery behind it. Two consequences:

- Jobs do not survive a process restart.
- Multi-worker deployments are not supported for polling. A client that polls a
  job can reach a worker that never saw it, and receive 404.

Treat the job API as single-process only until it is moved behind persistent
storage.

### Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 404 | `AGENT_NOT_FOUND` | No agent registered under that name |
| 404 | `OPERATION_NOT_FOUND` | Agent does not advertise that operation |
| 404 | `JOB_NOT_FOUND` | No Performance job with that id |
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
| `KNOWLEDGE_EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | HuggingFace embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model tag used for generation |
| `KNOWLEDGE_AGENT_TIMEOUT_SECONDS` | `300` | Per-operation budget; exceeding it returns 504 |
| `AUTOMATION_AGENT_TIMEOUT_SECONDS` | `180` | Per-operation budget; exceeding it returns 504 |
| `PERFORMANCE_AGENT_TIMEOUT_SECONDS` | `600` | Currently **not enforced** — see below |
| `AGENT_MAX_CONCURRENCY` | `4` | Agent operations running at once, across all agents |

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

Startup fails fast if `ENVIRONMENT=production` with `DEBUG=true` or a wildcard
CORS origin.

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

Authentication, authorization, RBAC, and per-user data — `app/api/deps.py` is
the seam; add a dependency there rather than editing each route. Also pending:
database and persistence, Performance dataset upload endpoints, a durable or
shared file store for Knowledge uploads (see below), document deletion, an
endpoint that serves Performance visualization files, streaming responses (SSE),
rate limiting, and LLM-based agent routing.

To add a synchronous agent: implement `AgentAdapter`, register it in
`app/agents/factory.py`, and add a description in `app/api/v1/agents.py`. No
new endpoints are required.