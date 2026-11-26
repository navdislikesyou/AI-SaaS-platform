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
- **Agents** — all four are implemented and live in this repository:
  - **Knowledge** — RAG document Q&A. `backend/knowledge_agent/`. Served
    synchronously through `POST /api/v1/agents/execute`.
  - **Automation** — productivity requests, drafting only. `backend/automation_agent/`.
    Served synchronously through the same endpoint.
  - **Performance** — data analytics. `backend/performance_agent/`. Served as
    background jobs through `POST /api/v1/performance/jobs`, not through
    `/agents/execute`.
  - **Employee Insights** — employee feedback sentiment analysis and org-scoped analytics.
    `backend/employee_insights/`. Served synchronously through
    `POST /api/v1/agents/execute` and `/api/v1/employee-insights/*`.

The synchronous agents couple to real agent code in
`backend/app/agents/adapters/`. Performance couples in
`backend/app/services/job_manager.py` instead, because its analysis is
CPU-bound and long running.

## Do Not

- Change the Knowledge Agent's retrieval or generation behaviour without being asked
- Implement Gmail, Google Calendar, email sending, or scheduling inside the
  Automation *Agent* package (`backend/automation_agent/`) — it drafts and must
  stay draft-only. Email sending is performed by the backend through the
  privileged `send_email` operation on the Automation adapter, after strict
  explicit confirmation, and only by manager/admin users
- Add ML (prediction, classification, regression) to the Performance Analyzer
  — it is data analytics only
- Add database, auth, RBAC, or frontend code without being asked
- Introduce Celery, Redis, or a database-backed job queue — the Performance job
  store is intentionally in-process for now
- Import an agent implementation into a router or the orchestrator
- Expose stack traces, raw exception text, or internal filesystem paths in API
  responses
- Commit `.env`, `.venv/`, model weights, or anything else gitignored
- Bypass organization-level tenant isolation or RBAC checks
- Weaken Gmail recipient verification or allow uploaded contacts to bypass
  organization-user verification

## Repository Layout

```
backend/
  app/
    main.py            app factory, lifespan, CORS, middleware
    api/
      deps.py          shared dependencies (auth seam)
      v1/              router.py, health.py, agents.py, performance.py, employee_insights.py
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
      adapters/        knowledge, automation, performance, employee_insights
    services/
      orchestrator.py  dispatch only
      job_manager.py   in-process background jobs for Performance
      dataset_upload.py  browser dataset uploads; resolves dataset_id to a path
  knowledge_agent     RAG agent: loaders, splitter, embeddings, vector store
  automation_agent    Automation agent: parser, employee directory, drafting
  performance_agent   data analytics: dataset, analyzers, visualizations, insights
  employee_insights   employee feedback sentiment analysis and analytics
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
pytest tests/test_tenant_isolation.py    # tenant isolation tests
pytest tests/test_automation_adapter.py  # adapter tests
pytest tests/test_automation_directory_resolution.py  # directory resolution tests

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

## Email Sending

The Automation adapter advertises a privileged `send_email` operation in
addition to `draft_action` and `draft_html`. Drafting never sends. Sending
requires:

- an authenticated manager or administrator (employees get 403);
- a connected organization-scoped Gmail mailbox with the `gmail.send` scope
  (reauthorize through the existing OAuth flow if only `gmail.readonly` is
  granted);
- a strict backend `confirm is True` (truthy strings/numbers do not count);
- a valid recipient list, subject, and HTML body within configured limits;
- an idempotency key, which makes retries after a timeout replay the recorded
  outcome instead of resending.

The backend sender lives in `app/services/gmail_send.py` and reuses the
existing connection, Fernet encryption, refresh, and `invalid_grant` handling.
It claims an `email_sends` row before calling Gmail, so an uncertain outcome
(stuck `sending`/`uncertain`) is never blindly retried. All sends are
audited (sender, organization, recipient, subject, timestamp, outcome) without
the body or any credential. The Automation Agent package stays draft-only.

## Phase 4: Organization-Scoped Employee Directory

### Session Threading

Session propagation is threaded through the complete call chain:

```
API layer (get_async_session()) -> orchestrator.execute() -> adapter.run() -> _call_service() -> AutomationService.execute()
```

- The async SQLAlchemy session is passed from the API route through orchestrator, adapter, and service.
- Organization-scoped queries use the authenticated user's `organization_id`.
- The execute endpoint uses an optional session dependency so DB-independent tests can still run; services/adapters that require org-scoped DB resolution reject missing session safely.

### Organization Isolation

- Organization A never receives Organization B's employees.
- Organization ID is **always derived from the authenticated principal**, never from client-supplied data.
- Client-supplied organization IDs are ignored at every layer.
- All employee queries filter by the authenticated user's `organization_id`.

### Recipient / Attendee Resolution

- Only **active** employees (`is_active=True`) are included.
- Frontend sends employee UUIDs (`employee_ids`); backend resolves email/name from active org `User` records.
- Arbitrary email-only recipients, unknown UUIDs, cross-org UUIDs, and inactive users are rejected.
- Meeting attendees are validated against active org users; attendee email/name/user_id are derived from DB.
- No packaged `employees.json`. No `automation_agent/directory.py` fallback. No AutomationAgent uploaded-directory recipient selection.

### Security Rules (mandatory)

- **Never trust client-supplied organization IDs.** Derive organization context from authenticated principals only.
- **Never expose another organization's data.** All queries scoped to authenticated organization.
- **Exclude inactive employees** where required.
- **Never weaken Gmail recipient verification.** Uploaded contacts cannot bypass organization-user verification.
- **Never send real emails during automated tests.**
- **Do not bypass existing authorization checks.** Manager/admin RBAC enforced on relevant routes.

### Email / Meeting Workflows

- Drafting (`draft_action`, `draft_html`) produces drafts only; no send side effects.
- `send_email` requires manager/admin, strict `confirm is True`, idempotency key, valid org employee UUIDs, and DB-derived recipients.
- AXON meeting records are created/rescheduled/cancelled through meeting APIs. AXON meeting records do **not** automatically imply external Google Calendar synchronization.
- Invitation sending uses existing Gmail infrastructure with confirmation and idempotency; tests mock Gmail operations.

### Legacy / Retained Shared Endpoints

- `/api/v1/automation/directories` upload/list/detail endpoints remain as shared legacy infrastructure pending dependency analysis. They are not used for AutomationAgent recipient selection.

### Example: Employee Directory Flow

```http
GET /api/v1/automation/employees
Authorization: Bearer <jwt-token>
```

Response: 200 with active employees in the authenticated user's organization.

```http
POST /api/v1/agents/execute
{
  "agent": "automation",
  "operation": "send_email",
  "payload": {
    "employee_ids": ["<org-user-uuid>"],
    "subject": "Hello",
    "html_body": "<p>Hello</p>",
    "confirm": true,
    "idempotency_key": "unique-key"
  }
}
```

Backend resolves recipient email/name from the authenticated organization's active User records.


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