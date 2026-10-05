# AGENTS.md

Guidance for agentic coding agents working in this repository.

## Project

AI Workforce SaaS — a multi-agent platform where specialized agents automate HR,
Marketing, Finance, Legal, Research, and Productivity workflows.

The backend and the AI agents are developed separately. The backend must never
depend on agent internals; agents plug in through adapters.

Current scope:
- **Backend foundation** — `backend/app` (FastAPI, agent abstraction, registry,
  orchestrator). Live.
- **Agents** — Knowledge (RAG document Q&A), Automation (productivity
  requests), Performance Analyzer (data analytics). **Not in this repo.** They
  are connected later through adapters in `backend/app/agents/adapters/`.

## Do Not

- Implement RAG, embeddings, ChromaDB, document parsing, or Llama logic
- Implement Gmail, Google Calendar, email sending, or scheduling
- Add ML (prediction, classification, regression) to the Performance Analyzer
  — it is data analytics only
- Add database, auth, RBAC, or frontend code without being asked
- Import an agent implementation into a router or the orchestrator
- Expose stack traces or internal details in API responses
- Commit `.env`, `.venv/`, model weights, or anything else gitignored

## Repository Layout

```
backend/
  app/
    main.py            app factory, lifespan, CORS, middleware
    api/
      deps.py          shared dependencies (auth seam)
      v1/              router.py, health.py, agents.py
    core/
      config.py        settings; the only module reading env vars
      logging_config.py  logging + request-id correlation
      exceptions.py    AppError hierarchy + handlers
      middleware.py    request id, timing
    schemas/           common.py, agent.py
    agents/
      base.py          AgentAdapter ABC, PlaceholderAgentAdapter
      registry.py      AgentRegistry
      factory.py       default registry from settings
      adapters/        knowledge, automation, performance
    services/
      orchestrator.py  dispatch only
  tests/               mirrors app/; fakes.py, conformance.py
  requirements.txt
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
- Adapters are the only place coupled to real agent code.
- All real-agent coupling stays inside `app/agents/adapters/`.

### Error Handling
- Raise `AppError` subclasses (`core/exceptions.py`); never bare `except:`.
- Map domain errors to status codes in one place only.
  `UnknownAgentError` → 404, `UnknownOperationError` → 404,
  `ValidationFailedError` → 422, `AgentExecutionError` → 502,
  `AgentUnavailableError` → 503, `AgentTimeoutError` → 504.
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

`AgentAdapter` (`app/agents/base.py`) is the seam. `execute()` checks
availability and operation support, then runs `run()` in a thread under
`timeout_seconds`.

To connect a real agent:
1. Override `run()` in the matching adapter to call it, translating payload in
   and result out.
2. Set the agent's `*_AGENT_ENABLED=true` in `.env`.
3. Pass `pytest tests/conformance.py`.
4. Verify through `POST /api/v1/agents/execute`.

Routes and schemas should not need changes. `tests/conformance.py` is the gate.

Real agent code is blocking and synchronous (Llama, ChromaDB, pandas). The
adapter's thread offload exists specifically so those calls do not block the
event loop. Models and vector stores must be initialized once at adapter
construction, never per request.

## Tests

- One file per module, mirroring `app/` under `tests/`.
- Name tests `test_<behavior>` — describe the outcome, not the call.
- Use fakes from `tests/fakes.py`: `EchoAgent`, `UnavailableAgent`,
  `ExplodingAgent`, `SlowAgent`. Never load a real model or hit the network.
- Keep every test runnable on CPU without a GPU.
- Assert on status codes and the standard envelope, not on log text.
- Use `pytest.raises(..., match=...)` for error paths.

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