# Backend — AI SaaS Platform

FastAPI backend foundation for the AI SaaS Platform.

**The three platform agents are not integrated yet.** They are developed
separately and connected later through adapters. This backend runs, serves a
stable API contract, and reports each agent's status honestly.

## Agents

| Agent | Purpose | Status |
|---|---|---|
| `knowledge` | RAG question answering over PDF/DOCX/TXT documents | Registered, not connected |
| `automation` | Interprets productivity requests and drafts actions | Registered, not connected |
| `performance` | Data analytics: KPIs, comparisons, trends, insights | Registered, not connected |

No RAG, ChromaDB, embeddings, Llama, Gmail, Google Calendar, or ML code exists
in this repository. The Performance Analyzer is modelled strictly as data
analytics, with no predictive or classification behaviour.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env            # optional; defaults work without it
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
│   ├── base.py          AgentAdapter ABC + PlaceholderAgentAdapter
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
        "capabilities": ["ingest_document", "list_documents", "delete_document", "query"],
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
      "capabilities": ["ingest_document", "list_documents", "delete_document", "query"]
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
| `*_AGENT_ENABLED` | `false` | Flip to true once an agent is connected |

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

Placeholders extend `PlaceholderAgentAdapter`, advertise their intended
operations, and report `is_available() == False`. They contain no AI logic.
`execute()` runs `run()` in a worker thread under a timeout, so a slow real
agent will not block the event loop once connected.

## Integrating a real agent

1. Inspect the implementation and note its entry point, whether it is blocking,
   and what it returns.
2. Override `run()` in the matching adapter to call it, translating the payload
   and returning a dict.
3. Set the agent's `*_AGENT_ENABLED=true` in `.env`.
4. Run `pytest tests/conformance.py` — the contract every adapter must pass.
5. Verify via `POST /api/v1/agents/execute`.

No route or schema changes are expected. `app/agents/adapters/` is the only
directory that should need edits.

## Not implemented (future phases)

Authentication, authorization, RBAC, and per-user data — `app/api/deps.py` is
the seam; add a dependency there rather than editing each route. Also pending:
database and persistence, agent-specific upload and dataset endpoints, file
storage, streaming responses (SSE), rate limiting, and LLM-based agent routing.

To add an agent: implement `AgentAdapter`, register it in
`app/agents/factory.py`, and add a description in `app/api/v1/agents.py`. No
new endpoints are required.