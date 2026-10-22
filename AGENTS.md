# AGENTS.md

Guidance for agentic coding agents working in this repository.

## Project

AI Workforce SaaS — a multi-agent platform where specialized agents automate HR,
Marketing, Finance, Legal, Research, and Productivity workflows.

The backend and the AI agents are developed separately. The backend must never
depend on agent internals; agents plug in through adapters.

Current scope:
- **Backend** — `backend/app` (FastAPI, agent abstraction, registry, orchestrator,
  Performance job API). Live.
- **Agents** — all three are implemented and live in this repository:
  - **Knowledge** — RAG document Q&A. `backend/knowledge_agent/`. Served
    synchronously through `POST /api/v1/agents/execute`.
  - **Automation** — productivity requests, drafting only. `backend/automation_agent/`.
    Served synchronously through the same endpoint.
  - **Performance** — data analytics. `backend/performance_agent/`. Served as
    background jobs through `POST /api/v1/performance/jobs`, not through
    `/agents/execute`.

The synchronous agents couple to real agent code in
`backend/app/agents/adapters/`. Performance couples in
`backend/app/services/job_manager.py` instead, because its analysis is
CPU-bound and long running.

## Do Not

- Change the Knowledge Agent's retrieval or generation behaviour without being asked
- Implement Gmail, Google Calendar, email sending, or scheduling — the
  Automation Agent drafts and must stay draft-only
- Add ML (prediction, classification, regression) to the Performance Analyzer
  — it is data analytics only
- Add database, auth, RBAC, or frontend code without being asked
- Introduce Celery, Redis, or a database-backed job queue — the Performance job
  store is intentionally in-process for now
- Import an agent implementation into a router or the orchestrator
- Expose stack traces, raw exception text, or internal filesystem paths in API
  responses
- Commit `.env`, `.venv/`, model weights, or anything else gitignored

## Repository Layout

```
backend/
  app/
    main.py            app factory, lifespan, CORS, middleware
    api/
      deps.py          shared dependencies (auth seam)
      v1/              router.py, health.py, agents.py, performance.py
    core/
      config.py        settings; the only module reading env vars
      logging_config.py  logging + request-id correlation
      exceptions.py    AppError hierarchy + handlers
      middleware.py    request id, timing
    schemas/           common.py, agent.py, performance.py
    agents/
      base.py          AgentAdapter ABC, concurrency limiting, placeholder base
      registry.py      AgentRegistry
      factory.py       default registry from settings
      adapters/        knowledge, automation, performance
    services/
      orchestrator.py  dispatch only
      job_manager.py   in-process background jobs for Performance
      dataset_upload.py  browser dataset uploads; resolves dataset_id to a path
  knowledge_agent/     RAG agent: loaders, splitter, embeddings, vector store
  automation_agent/    Automation agent: parser, employee directory, drafting
  performance_agent/   data analytics: dataset, analyzers, visualizations, insights
  tests/               mirrors app/; fakes.py, conformance.py
  requirements.txt
  requirements-agents.txt  agent dependencies, installed separately
  pyproject.toml       ruff, mypy, pytest config
  .env.example
  README.md
```

## Commands

```bash
cd backend
.venv\Scripts\activate

# Run the API
uvicorn app.main:app --reload --port 8000

# Tests
pytest                              # all
pytest tests/test_agents_api.py     # one file
pytest tests/test_registry.py -k unknown   # one test by keyword
pytest tests/conformance.py         # agent contract suite

# Lint, format, types
ruff check app tests
ruff check app tests --fix
ruff format app tests
mypy app
```

`pytest`, `ruff`, and `mypy` are pinned in `requirements.txt`.

## Code Style

### Formatting
- 4-space indent, UTF-8, LF line endings, 100 char lines.
- `ruff format` owns layout. Do not hand-align.
- Two blank lines between top-level definitions, one between methods.

### Imports
- Absolute imports rooted at `backend` (`from app.services.orchestrator import Orchestrator`).
- Order: stdlib, third-party, local; alphabetized within groups.
- No wildcards. Prefer `import torch` over `from torch import nn` in hot paths.
- Note `core/logging_config.py` is deliberately not named `logging.py`, which
  would shadow the stdlib module.

### Types
- Annotate every signature, including `-> None`.
- `from __future__ import annotations` at the top of every module.
- Builtin generics (`list[str]`, `dict[str, Any]`) over `typing.List`.
- `X | None`, not `Optional[X]`.
- `mypy app` must pass with no errors.
- Pydantic `BaseModel` for anything crossing the API boundary. Never return raw
  dicts from routers.

### Naming
- `snake_case` modules, functions, variables, dict keys.
- `PascalCase` classes and Pydantic models.
- `SCREAMING_SNAKE_CASE` module constants.
- `_leading_underscore` for private helpers.
- Routers are named `router` and export `router = APIRouter()`.
- Adapter classes end in `AgentAdapter`.

### Docstrings
- Every module, class, and public function. One-line summary in imperative
  mood, blank line, then `Args` / `Returns` / `Raises`.

  ```python
  def resolve(self, agent_name: str) -> AgentAdapter:
      """Resolve an agent name to its adapter.

      Args:
          agent_name: The agent identifier requested by the client.

      Returns:
          The registered adapter.

      Raises:
          UnknownAgentError: If the name is not registered.
      """
  ```

### Layering
- Routers own HTTP: status codes, auth dependencies, request/response shapes.
  They never import an agent implementation or an adapter's internals.
- The orchestrator resolves and dispatches. It contains no agent logic and
  chooses no LLM-based routing in v1 — the client names the agent.
- Adapters are the only place coupled to real agent code for the synchronous
  agents. Performance couples in `app/services/job_manager.py` instead.
- All real-agent coupling stays inside `app/agents/adapters/` or
  `app/services/job_manager.py`.

### Error Handling
- Raise `AppError` subclasses (`core/exceptions.py`); never bare `except:`.
- Map domain errors to status codes in one place only.
  `UnknownAgentError` → 404, `UnknownOperationError` → 404,
  `JobNotFoundError` → 404, `DatasetNotFoundError` → 404,
  `DirectoryNotFoundError` → 404, `ValidationFailedError` → 422,
  `AgentExecutionError` → 502, `AgentUnavailableError` → 503,
  `AgentTimeoutError` → 504.
- Log full tracebacks server-side; never return them. Error bodies carry only
  `code`, `message`, `details`, and `request_id`.
- Adapters must not log or echo credentials.

### Logging
- Use `logging.getLogger(__name__)`. No `print()` in library code.
- Never log passwords, API keys, tokens, or request bodies.
- `LOG_FORMAT=json` for shipping; every record includes the request id.

### Async and API
- `async def` endpoints. Agents run in a worker thread via
  `anyio.to_thread.run_sync` so blocking inference never stalls the loop.
- Set `response_model` on every route.
- New dependencies go in `api/deps.py`. Auth is added there, not per route.
- Status codes: 200 read, 202 accepted, 400 bad input, 404 missing,
  409 conflict, 422 validation, 502 agent failure, 503 unavailable, 504 timeout.

## Agent Integration

`AgentAdapter` (`app/agents/base.py`) is the seam for the synchronous agents.
`execute()` checks availability and operation support, then runs `run()` in a
thread under `timeout_seconds`.

Knowledge and Automation follow this path. To connect a similar agent:
1. Override `run()` in the matching adapter to call the agent's service,
   translating payload in and result out.
2. Attempt service construction in the adapter's `__init__` inside a try block,
   including the import, so a missing optional dependency degrades to
   unavailable rather than crashing startup.
3. Raise `ValidationFailedError` for missing or blank payload keys, so bad
   input returns 422 instead of 502.
4. Trim `ADVERTISED_CAPABILITIES` to what actually exists.
5. Set the agent's `*_AGENT_ENABLED=true` in `.env`.
6. Pass `pytest tests/conformance.py`.
7. Verify through `POST /api/v1/agents/execute`.

Routes and schemas should not need changes. `tests/conformance.py` is the gate.

Real agent code is blocking and synchronous (Llama, ChromaDB, pandas). The
adapter's thread offload exists specifically so those calls do not block the
event loop. Models and vector stores must be initialized once at adapter
construction, never per request.

A worker thread cannot be cancelled mid-inference, so `base.py` holds a
concurrency slot that the thread releases when it genuinely finishes, not when
the caller times out. Do not reintroduce `abandon_on_cancel=True` without that
slot: repeated timeouts would otherwise pile up unbounded background CPU burn.

## Performance Jobs

Performance is not an execution path. It is a background job API, because
analysis over a real dataset takes seconds and holding a request open for it is
the wrong shape.

`POST /api/v1/performance/jobs` validates the request and returns 202.
`JobManager` (`app/services/job_manager.py`) owns the lifecycle
(`queued → running → completed | failed`) and calls `PerformanceService` on a
worker thread via `anyio.to_thread.run_sync`, spawned with
`asyncio.create_task` so the response returns immediately.

A job names its dataset by `dataset_id` — an uploaded dataset from
`POST /api/v1/performance/datasets`, or the reserved id `sample` for the packaged
one — which the router resolves to a path the server owns *before* the job
exists. An unresolvable id is 404 `DATASET_NOT_FOUND` and no job is created; there
is no fallback, because analysing a different file than the one selected would
report success for the wrong data. `file_path` remains for the pre-existing
server-side workflow, and the two are mutually exclusive on a request. Do not
resolve a client-supplied string against the filesystem.

The store is an in-process dictionary. There is no Celery, Redis, or database
behind it. Do not describe any of those as implemented. Consequences: jobs do
not survive a restart, and multi-worker deployments cannot serve job polling,
because a poll can reach a worker that never saw the job.

Keep pandas out of routers. The router validates and delegates; the job manager
maps operation to a `PerformanceService` method; the service calls the
analyzers. There is no second implementation of what an operation means.

Redact filesystem paths from any error text returned to a client. Analyzer and
loader exceptions carry raw `str(error)`, which can contain server paths.
Sanitize at the API boundary and keep the full text in server logs.

## Tests

- One file per module, mirroring `app/` under `tests/`.
- Name tests `test_<behavior>` — describe the outcome, not the call.
- Use fakes from `tests/fakes.py`: `EchoAgent`, `UnavailableAgent`,
  `ExplodingAgent`, `SlowAgent`. Never load a real model or hit the network.
- Keep every test runnable on CPU without a GPU.
- Assert on status codes and the standard envelope, not on log text.
- Use `pytest.raises(..., match=...)` for error paths.

Agent-integration tests stay opt-in behind the enable flags
(`tests/test_agent_integration.py`) so CI never loads a model. Performance job
tests stub the service, so they neither run pandas nor render the 39 charts.

## Git

- Branch per feature: `feat/agent-registry`, `fix/request-id-correlation`.
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
  `chore:`, `perf:`.
- Never commit `.env`, `.venv/`, `*.pt`, `*.safetensors`, `*.bin`, `*.gguf`,
  `backend/uploads/`, or `backend/outputs/`.
- Do not commit changes the user did not ask for.

## Existing Rules Files

No `.cursor/rules/`, `.cursorrules`, or `.github/copilot-instructions.md`
exists yet. If you add one, mirror its rules here so both stay in sync.