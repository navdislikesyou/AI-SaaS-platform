# AI Workforce SaaS

A multi-agent AI platform where specialized agents automate HR, Marketing,
Finance, Legal, Research, and Productivity workflows.

Three agents are implemented and live in this repository:

| Agent | Purpose | How it is served |
|---|---|---|
| Knowledge | RAG question answering over uploaded PDF/DOCX/TXT documents | Synchronous — `POST /api/v1/agents/execute` and `/api/v1/knowledge/*` |
| Automation | Interprets productivity requests and drafts actions against an employee directory | Synchronous — `POST /api/v1/agents/execute` and `/api/v1/automation/*` |
| Performance | Data analytics over CSV/XLSX datasets: KPIs, period comparisons, trends, insights, charts | Background jobs — `POST /api/v1/performance/jobs` |

The platform ships a FastAPI backend, a React single-page frontend, JWT
authentication with organization-scoped multi-tenancy and role-based access
control, database persistence through SQLAlchemy and Alembic, and browser
upload APIs for documents, employee directories, and datasets.

## What is implemented

**Backend** (`backend/`)

- FastAPI application with a versioned API under `/api/v1`, request-id
  correlation, structured logging, and a centralized error envelope.
- Authentication: login, refresh, logout, and session lookup. Access tokens are
  short-lived JWTs; refresh tokens are rotated and stored in HttpOnly cookies.
  Passwords are hashed with Argon2.
- Multi-tenancy and RBAC: users belong to an organization, with roles
  `employee`, `manager`, and `admin`. Role dependencies guard management
  routes; the organization page is admin-only.
- User management: create, list, update, activate, deactivate, and reassign
  managers within the authenticated user's organization. A one-time
  `bootstrap_admin.py` CLI creates the first administrator.
- Persistence: SQLAlchemy 2.x models (`Organization`, `User`, `RefreshToken`)
  with Alembic migrations. SQLite works out of the box; PostgreSQL is
  supported through configuration.
- Agent abstraction: adapters, a registry, and an orchestrator. The client
  names the agent and operation; there is no LLM-based routing in v1.
- Upload APIs: Knowledge documents (PDF/DOCX/TXT), Automation employee
  directories (JSON/CSV), and Performance datasets (CSV/XLSX), each with
  streaming size limits, server-generated filenames, and a JSON manifest.
- Performance job API with dataset upload, job submission, polling, and
  artifact download. Jobs run on worker threads inside the API process.
- Activity history endpoint for recent user and agent activity.

**Agents** (`backend/knowledge_agent/`, `backend/automation_agent/`,
`backend/performance_agent/`)

- Knowledge: document loaders, chunking, HuggingFace embeddings, Chroma
  vector store, and Ollama-backed generation.
- Automation: request parsing, employee-directory resolution, and draft
  generation. It drafts only — it sends no email and creates no calendar
  events.
- Performance: pandas-based analytics producing KPIs, comparisons, trends,
  business insights, and matplotlib visualizations. It is data analytics
  only, with no prediction or classification.

**Frontend** (`frontend/`)

- React 19 + Vite single-page application with React Router.
- Login flow with session hydration from the refresh cookie, in-memory access
  tokens, and automatic renewal. Protected routes redirect unauthenticated
  users.
- Role-aware navigation; the organization management page requires the admin
  role.
- Live agent pages for Knowledge, Automation, and Performance: document and
  directory upload, dataset upload, job submission with polling, and artifact
  preview.
- Organization management, settings, landing, and auth screens.
- UI shells for future agent areas (hiring, research, communication,
  insights, orchestrator) that are not backed by a live agent yet.
- Component, hook, service, and page tests with Vitest and Testing Library.

## Architecture

```
Frontend (React SPA)
    │  JWT access token in memory, refresh token in HttpOnly cookie
    ▼
FastAPI  (backend/app — CORS, middleware, auth dependencies, error handlers)
    ├── /api/v1/auth, /api/v1/users          session + RBAC + org membership
    ├── /api/v1/agents, /api/v1/agents/execute   synchronous agent dispatch
    ├── /api/v1/knowledge, /api/v1/automation    upload + list APIs
    ├── /api/v1/performance                 dataset upload + background jobs
    └── /api/v1/activity-history            recent activity
              │
              ▼
        Orchestrator → Registry → Adapters → Agent services
              │
              ▼
        SQLAlchemy 2 + Alembic   (organizations, users, refresh_tokens)
```

Two execution paths exist because the agents differ in how long they take.
Knowledge and Automation run synchronously through the generic execute
endpoint, offloaded to worker threads so blocking inference never stalls the
event loop. Performance analysis is CPU-bound and long-running, so it runs as
an in-process background job that the client polls.

Routers never import agent implementations. Coupling to real agent code lives
only in `backend/app/agents/adapters/` (Knowledge, Automation) and
`backend/app/services/job_manager.py` (Performance).

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, pydantic-settings,
  SQLAlchemy 2.x, Alembic, PyJWT, argon2-cffi. Tests with pytest; lint and
  types with ruff and mypy.
- **Agents:** PyTorch, sentence-transformers, LangChain, ChromaDB,
  Ollama (Llama 3.1 8B over HTTP), pandas, numpy, openpyxl, matplotlib.
- **Frontend:** React 19, Vite, React Router 7, Recharts, Framer Motion,
  Lucide icons. Tests with Vitest and Testing Library; lint with oxlint.

## Repository layout

```
backend/
  app/                 FastAPI application (api, core, schemas, agents, services)
  alembic/             database migrations
  knowledge_agent/     RAG document Q&A agent
  automation_agent/    productivity drafting agent
  performance_agent/   data analytics agent
  bootstrap_admin.py   one-time first-administrator CLI
  tests/               pytest suite (mirrors app/)
  requirements.txt     API dependencies
  requirements-agents.txt  agent ML/document dependencies (~2 GB)
frontend/
  src/                 React application (pages, components, hooks, services)
```

## Getting started

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env            # then set JWT_SECRET_KEY (required in production)
alembic upgrade head            # create the schema
python bootstrap_admin.py --email admin@example.com --password 'YourStrongPass1!'
uvicorn app.main:app --reload --port 8000
```

The API is at `http://127.0.0.1:8000/api/v1`, with interactive docs at
`http://127.0.0.1:8000/docs`.

### Agents

Agent dependencies are installed separately so a plain API install does not
pull roughly 2 GB of PyTorch wheels:

```bash
pip install -r requirements.txt -r requirements-agents.txt
ollama serve
ollama pull llama3.1:8b
```

Then enable each agent in `.env`:

```bash
KNOWLEDGE_AGENT_ENABLED=true
AUTOMATION_AGENT_ENABLED=true
PERFORMANCE_AGENT_ENABLED=true
```

Startup never fails because of an agent: a failed construction is logged and
that agent reports unavailable (calls return 503). The Performance Analyzer
needs no model or external service. See
[`backend/README.md`](backend/README.md) for the full API reference,
configuration table, and agent-integration details.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server defaults to Vite's port (5173). Both the API's
`CORS_ORIGINS` and `TRUSTED_ORIGINS` must include the frontend origin for
authenticated requests and cookie refresh to work.

## Tests and checks

```bash
# Backend
cd backend
pytest                    # full suite; fakes only, no models or GPU
pytest tests/conformance.py
ruff check app tests
mypy app

# Frontend
cd frontend
npm test                  # vitest run
npm run lint              # oxlint
```

## Known limitations

- **Upload storage is a local MVP.** Uploaded documents, employee
  directories, and datasets live on the API host's disk with JSON manifests.
  They are not shared between instances, have no quota or retention policy,
  and there is no delete endpoint. A deployment needs persistent shared
  storage and a real metadata store.
- **Performance jobs are in-process.** Job state is an in-memory dictionary:
  jobs do not survive a restart, and multi-worker deployments cannot poll
  reliably. There is no Celery, Redis, or database-backed queue.
- **Automation is draft-only.** It never sends email, creates calendar
  events, or otherwise acts on the outside world.
- **Performance is analytics only.** No prediction, classification, or
  regression.
- **SQLite by default.** Fine for development; use PostgreSQL for anything
  shared between processes.

## Further documentation

- [`backend/README.md`](backend/README.md) — API reference, endpoint
  behaviour, configuration, adapter contract, and how to add an agent.
- [`AGENTS.md`](AGENTS.md) — conventions for coding agents working in this
  repository.
