# Backend — AI SaaS Platform

FastAPI backend foundation for the AI SaaS Platform.

**Knowledge and Automation are connected behind their adapters. Performance is
deferred.** The Knowledge and Automation agents live in this repository under
`knowledge_agent/` and `automation_agent/`, each exposing a thin dict-in,
dict-out service that the adapter calls. This backend runs, serves a stable
API contract, and reports each agent's status honestly — including when an
agent is enabled but fails to initialize.

## Agents

| Agent | Purpose | Status | Capabilities |
|---|---|---|---|
| `knowledge` | RAG question answering over PDF/DOCX/TXT documents | Connected when enabled | `ingest_document`, `query` |
| `automation` | Interprets productivity requests and drafts actions | Connected when enabled | `draft_action` |
| `performance` | Data analytics: KPIs, comparisons, trends, insights | Deferred, not connected | — |

Capabilities listed above are the ones that actually work. Each is backed by a
service method; anything not listed returns 404 rather than being advertised
and then failing.

Agent code exists in this repository for Knowledge and Automation. There is no
Gmail, Google Calendar, or scheduling integration, and no ML code: the
Performance Analyzer is modelled strictly as data analytics, with no predictive
or classification behaviour, and is not implemented at all.

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

The Knowledge and Automation agents need extra dependencies and a local Ollama
server. Without them the API still runs; the agents simply report unavailable.

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

Then enable the agent in `.env`:

```bash
KNOWLEDGE_AGENT_ENABLED=true
AUTOMATION_AGENT_ENABLED=true
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
pytest                                    # all 41 tests
pytest tests/test_agents_api.py           # one file
pytest tests/test_registry.py -k unknown  # one test
pytest tests/conformance.py               # agent contract suite
```

Tests use fake agents (`tests/fakes.py`). No GPU, network, or real agent is
required.

## Lint and format

```bash
ruff check app tests
ruff check app tests --fix
ruff format app tests
mypy app
```

## Architecture

```
Frontend
   ↓
FastAPI  (app/main.py — CORS, middleware, error handlers, versioning)
   ↓
Routes  (app/api/v1 — HTTP only, no agent knowledge)
   ↓
Orchestrator  (app/services/orchestrator.py — resolve, dispatch, wrap)
   ↓
Registry  (app/agents/registry.py — name → adapter)
   ↓
Adapters  (app/agents/adapters — integration boundary)
   ↓
Real agents (FUTURE — not in this repo)
```

Layering rule: routers never import agent implementations. The orchestrator
holds no agent logic. All real-agent coupling lives in one directory,
`app/agents/adapters/`.

```
app/
├── main.py              app factory, lifespan, CORS, middleware
├── api/
│   ├── deps.py          shared dependencies (auth seam lives here)
│   └── v1/
│       ├── router.py    aggregates v1 routers
│       ├── health.py    /health, /ready
│       └── agents.py    /agents, /agents/{name}, /agents/execute
├── core/
│   ├── config.py        pydantic-settings, no os.environ elsewhere
│   ├── logging_config.py  console/JSON logging + request-id correlation
│   ├── exceptions.py    AppError hierarchy + centralized handlers
│   └── middleware.py    request id, timing log
├── schemas/
│   ├── common.py        APIResponse, ErrorDetail, health, readiness
│   └── agent.py         agent info, execute request/response
├── agents/
│   ├── base.py          AgentAdapter ABC, concurrency limiting, placeholder base
│   ├── registry.py      AgentRegistry
│   ├── factory.py       builds the default registry from settings
│   └── adapters/        knowledge, automation, performance
└── services/
    └── orchestrator.py  dispatch only
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

Catalog. The frontend can build its agent list from this alone.

```json
{
  "success": true,
  "data": {
    "agents": [
      {
        "name": "knowledge",
        "display_name": "Knowledge",
        "available": false,
        "capabilities": ["ingest_document", "query"],
        "status": "not_connected",
        "description": "Retrieval-augmented question answering ..."
      }
    ],
    "total": 3,
    "available_count": 0
  },
  "message": "3 agents registered.",
  "request_id": "5aa72667b1294e639f658fdd00d7a5cd"
}
```

### `GET /api/v1/agents/{agent_name}`

One agent's metadata. Unknown name → 404.

### `POST /api/v1/agents/execute`

Generic execution. The client names the agent and operation explicitly; v1
does no LLM-based routing.

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

Agent not connected (current state for all three agents) → **503**:

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

### Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 404 | `AGENT_NOT_FOUND` | No agent registered under that name |
| 404 | `OPERATION_NOT_FOUND` | Agent does not advertise that operation |
| 422 | `VALIDATION_ERROR` | Malformed body or failed schema validation |
| 500 | `INTERNAL_ERROR` | Unexpected server fault (details never exposed) |
| 502 | `AGENT_EXECUTION_FAILED` | Connected agent raised |
| 503 | `AGENT_UNAVAILABLE` | Agent registered, implementation missing |
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
| `KNOWLEDGE_EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | HuggingFace embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model tag used for generation |
| `KNOWLEDGE_AGENT_TIMEOUT_SECONDS` | `300` | Per-operation budget; exceeding it returns 504 |
| `AUTOMATION_AGENT_TIMEOUT_SECONDS` | `180` | Per-operation budget; exceeding it returns 504 |
| `PERFORMANCE_AGENT_TIMEOUT_SECONDS` | `600` | Unused until Performance is connected |
| `AGENT_MAX_CONCURRENCY` | `4` | Agent operations running at once, across all agents |

Enabling an agent makes the API *attempt* construction, not guarantee it. A
failure degrades that agent to unavailable rather than blocking startup, so
`is_available()` reports real state rather than the flag.

Inference is CPU-bound, so the timeout defaults are generous and
`AGENT_MAX_CONCURRENCY` is deliberately low. A timed-out agent thread cannot be
killed from outside, so it keeps its concurrency slot until it actually
finishes; raising the limit buys no extra throughput on a small machine and
only adds context switching.

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

`PerformanceAgentAdapter` still extends `PlaceholderAgentAdapter`: it
advertises its intended operations and reports `is_available() == False`,
containing no AI logic.

## Integrating a real agent

Knowledge and Automation already follow these steps. They are the reference for
connecting the Performance Analyzer.

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

## Not implemented (future phases)

Authentication, authorization, RBAC, and per-user data — `app/api/deps.py` is
the seam; add a dependency there rather than editing each route. Also pending:
database and persistence, agent-specific upload and dataset endpoints, file
storage, streaming responses (SSE), rate limiting, and LLM-based agent routing.

To add an agent: implement `AgentAdapter`, register it in
`app/agents/factory.py`, and add a description in `app/api/v1/agents.py`. No
new endpoints are required.