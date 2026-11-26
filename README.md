# AI Workforce SaaS — AXON

A multi-agent AI platform where specialized agents automate HR, Marketing,
Finance, Legal, Research, and Productivity workflows.

Four agents are implemented and live in this repository:

| Agent | Purpose | How it is served |
|---|---|---|
| **Knowledge** | RAG question answering over uploaded PDF/DOCX/TXT documents | Synchronous — `POST /api/v1/agents/execute` and `/api/v1/knowledge/*` |
| **Automation** | Interprets productivity requests and drafts actions against an employee directory | Synchronous — `POST /api/v1/agents/execute` and `/api/v1/automation/*` |
| **Performance** | Data analytics over CSV/XLSX datasets: KPIs, period comparisons, trends, insights, charts | Background jobs — `POST /api/v1/performance/jobs` |
| **Employee Insights** | Organization-scoped employee feedback sentiment analysis and analytics | Synchronous — `POST /api/v1/agents/execute` and `/api/v1/employee-insights/*` |

## Overview

AXON is a multi-agent AI SaaS platform where specialized agents automate various
business workflows. The backend and the AI agents are developed separately; agents
plug in through adapters that connect to the backend via a unified execution API.

The platform provides:

- **JWT authentication** with organization-scoped multi-tenancy and role-based
  access control
- **User management** within authenticated organizations
- **Employee directory** using the existing SQLAlchemy User model (no new tables,
  columns, or migrations)
- **Employee directory UI** with two-tab interface (Registered Employees + Uploaded
  Directory)
- **Productivity drafting** via the Automation Agent
- **Data analytics** via the Performance Analyzer
- **Document Q&A** via the Knowledge Agent
- **Employee feedback insights** via the Employee Insights Agent

## Architecture

### Backend (`backend/`)

A FastAPI application with the following architecture:

- **API layer** (`backend/app/api/v1/`): Versioned routes under `/api/v1`,
  request-id correlation, structured logging, and a centralized error envelope.
- **Agent abstraction** (`backend/app/agents/`): Adapter pattern connecting the
  backend to concrete agent implementations
  - **AutomationAdapter** (`backend/app/agents/adapters/automation.py`):
    Productivity drafting with organization-scoped employee resolution
  - **KnowledgeAdapter** (`backend/app/agents/adapters/knowledge.py`): Document
    Q&A
  - **PerformanceAdapter** (`backend/app/agents/adapters/performance.py`): Data
    analytics
- **Orchestrator** (`backend/app/services/orchestrator.py`): Dispatches operations
  to the registered agent
- **Service layer** (`backend/app/services/`): Business logic including employee
  directory service, Gmail integration, meeting scheduling, and dataset upload
- **Database models** (`backend/app/models.py`): `Organization`, `User`,
  `RefreshToken` via SQLAlchemy 2.x
- **Authentication** (`backend/app/api/deps.py`): JWT access tokens with HttpOnly
  refresh cookies; organization context derived from authenticated principal
- **Core utilities** (`backend/app/core/`): Config, exceptions, logging, middleware

**Key model relationships:**

- **Organization** (`id`, `name`, `slug`, `is_active`): Tenant container; each
  user belongs to one organization
- **User** (`id`, `email`, `full_name`, `role`, `is_active`, `organization_id`):
  Employee accounts; role is one of `employee`, `manager`, `admin`
- **RefreshToken** (`id`, `user_id`, `hashed_token`): Rotating refresh tokens for
  session management

**Agent execution flow:**

```
POST /api/v1/agents/execute
  │
  ├───→ user_context_for(user) → dict with user_id, organization_id, role
  │
  ├───→ orchestrator.execute(agent_name, operation, payload, user_context, session)
  │       │                                       │
  │       └─→ adapter.resolve(agent_name) → AgentAdapter
  │                               │
  │                               └─→ adapter.execute(operation, payload, user_context, session)
  │                                           │
  │                                           └─→ AutomationAgentAdapter.run()
  │                                                   │
  │                                                   └─→ _call_service(service, operation, payload, employees, user_context, session)
  │                                                             │
  │                                                             └─→ AutomationService.execute(instruction, employees, user_context, session)
  │                                                                   │
  │                                                                   └─→ AutomationAgent.execute(instruction, roster)
  │                                                                       │
  │                                                                       └─→ parse_instruction + find_emails
```

### Frontend (`frontend/`)

A React + Vite application providing the user interface:

- **Authentication**: JWT token management, organization context
- **Pages**:
  - **AutomationAIPage** (`frontend/src/pages/AutomationAIPage.jsx`): Two-tab
    employee directory and draft interface
  - **Other pages** as defined in the route configuration
- **Custom hooks**:
  - `useEmployeeDirectory.js`: Fetches registered employees from the backend
  - `useDirectoryUpload.js`: Handles uploaded directory management
- **Agent execution** via `POST /api/v1/agents/execute`
- **Dark AXON design system** throughout

**Key frontend features (Phase 4):**

- **Two-tab UI** in `AutomationAIPage.jsx`:
  - **Tab 1 — Registered Employees**: Fetches active employees from the
    authenticated organization via `GET /api/v1/automation/employees`
  - **Tab 2 — Uploaded Directory**: Manages uploaded employee directories
- **Employee selection** with multi-selection, search, and role filtering
- **Source-aware recipient summary** with labels (`Registered Employee` /
  `Uploaded Contact`)
- **Selection persistence** when switching tabs
- **Loading, error, and empty states** on both tabs
- **Dark AXON design** preserved throughout

### API Endpoints

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| `GET` | `/api/v1/agents/execute` | Execute agent operation | JWT required |
| `GET` | `/api/v1/automation/employees` | List active employees in organization | Manager/Admin required |
| `POST` | `/api/v1/agents/execute` | Execute agent operation (alternate) | JWT required |
| `POST` | `/api/v1/performance/jobs` | Submit performance analysis job | Varies by operation |
| `GET` | `/api/v1/knowledge/*` | Knowledge agent operations | JWT required |
| `GET` | `/api/v1/health` | Health check | Public |

### Authentication

- **Access tokens**: Short-lived JWTs passed via `Authorization: Bearer <token>`
  header
- **Refresh tokens**: HttpOnly cookies, rotated on use
- **Organization context**: Derived from the authenticated principal's
  `organization_id`; **client-supplied organization IDs are never trusted**
- **RBAC**: Roles `employee` (`employee`), `manager`, `admin`; management routes
  require manager or admin role

### Organization and Tenant Isolation

- Each user belongs to exactly one organization
- All queries filter by the authenticated user's `organization_id`
- Client-supplied organization information is explicitly ignored
- An user without an organization context receives appropriate empty/limited
  results
- Cross-organization access is prevented at the database and API level

### Gmail Integration

- **Google OAuth** workflow with scoped token management
- **Gmail connection** status and OAuth scope verification
- **Email drafting** via the Automation Agent (draft-only, no sending)
- **Email sending** performed by the backend through the privileged `send_email`
  operation, **after strict explicit confirmation** by manager/admin users
- **Recipient verification**: Uploaded contacts **cannot bypass** organization-user
  verification
- **OAuth token management**: Refresh, encryption, and invalid grant handling in
  `backend/app/services/gmail_send.py`
- **No real emails sent during testing or automation drafting**

### Agent Descriptions

| Agent | Purpose | Capabilities | Served at |
|---|---|---|---|
| **Knowledge** | RAG document Q&A | `ingest_document`, `query` | `/api/v1/agents/execute` |
| **Automation** | Productivity drafting | `draft_action`, `draft_html`, `send_email` | `/api/v1/agents/execute` |
| **Performance** | Data analytics | Job submission via `/api/v1/performance/jobs` | `/api/v1/performance/jobs` |
| **Employee Insights** | Employee feedback sentiment/analytics | `extract_feedback`, `employee_summary`, `sync_gmail` | `/api/v1/agents/execute`, `/api/v1/employee-insights/*` |

The Automation Agent **drafts only** — it does not send email, create calendar
events, or perform any external side effects. Email sending requires explicit
manager/admin confirmation through the backend `send_email` operation.

### Technology Stack

**Backend**

- **Language**: Python 3.12
- **Web framework**: FastAPI
- **ORM**: SQLAlchemy 2.x with DeclarativeBase
- **Migrations**: Alembic
- **Authentication**: JWT (access tokens + refresh cookies); Argon2 password hashing
- **Agent abstraction**: Custom adapter pattern with registry and orchestrator
- **Async support**: `anyio.to_thread.run_sync` for blocking agent operations
- **Gmail integration**: `backend/app/services/gmail_send.py` with token management
- **Key dependencies**: FastAPI, SQLAlchemy, Alembic, Argon2, google-auth,
  python-dotenv

**Frontend**

- **Framework**: React 18 + Vite
- **Build tool**: Vite
- **UI library**: Lucide-react icons
- **Styling**: Custom CSS with AXON design system variables
- **API communication**: `fetch` with JWT auth header
- **Custom hooks**: `useEmployeeDirectory.js`, `useDirectoryUpload.js`
- **State management**: React `useState`, `useEffect`
- **Key dependencies**: react, vite, lucide-react

### API Reference

**Agent Execution**

```http
POST /api/v1/agents/execute
Content-Type: application/json

{
  "agent": "automation",
  "operation": "draft_action",
  "payload": {
    "instruction": "Schedule a client meeting on 12 April at 3 PM in Room B"
  },
  "user_context": {
    "user_id": "user-123",
    "organization_id": "org-456",
    "role": "manager"
  }
}
```

**List Employees**

```http
GET /api/v1/automation/employees
Authorization: Bearer <jwt-token>
```

Returns active employees in the authenticated user's organization.

### Development

**Backend setup:**

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
text; only the Argon2 hash is written. Re-running is idempotent.

**Frontend setup:**

```bash
cd frontend
npm install
npm run dev              # development server
npm run build            # production build
```

**Testing:**

```bash
cd backend
.venv\Scripts\python.exe -m pytest                           # all tests
.venv\Scripts\python.exe -m pytest tests/test_agents_api.py   # agent API tests
.venv\Scripts\python.exe -m pytest tests/conformance.py       # agent contract tests
.venv\Scripts\python.exe -m mypy backend/app                 # type check
.venv\Scripts\python.exe -m ruff check backend/app backend/tests  # lint
.venv\Scripts\python.exe -m ruff format --check backend/app backend/tests  # format check
cd frontend; npm run build                                   # frontend build
```

### Implementation Status (Phase 4)

**Fully implemented and verified:**

- **Backend employee directory**: `list_active_users_by_organization()` service
  function using existing SQLAlchemy User model; no new tables, columns, or
  migrations
- **Backend API endpoint**: `GET /api/v1/automation/employees` with Manager/Admin
  RBAC, organization scoping (org_id derived from authenticated principal)
- **Frontend two-tab UI**: Registered Employees + Uploaded Directory tabs in
  `AutomationAIPage.jsx` with employee lists, multi-selection, search, role
  filtering, selection persistence, source labels, and summary
- **AutomationAgent service-level integration**: Organization-scoped roster
  resolution when `user_context.organization_id` is present and session is
  available; strict fallback control (empty roster when org context present but
  no session; packaged directory fallback when no org context)
- **Tenant isolation**: Organization A never receives Organization B's employees;
  org_id derived from authenticated principal; client-supplied IDs ignored
- **Gmail verification**: Unchanged; uploaded contacts cannot bypass
  organization-user verification
- **All existing Phase 1-3 behavior**: Preserved

**Pending follow-up:**

- Full session threading from API through to AutomationService (session parameter
  optional; graceful fallback when absent)
- AutomationAgent adapter integration for organization-scoped roster preference

### Known Limitations

- Session propagation through the full call chain is optional; when not available,
  the service falls back to the packaged directory gracefully
- Performance Analyzer runs 9 analyzers over the bundled Financials dataset only;
  custom datasets supported through upload API
- Automation Agent drafts only — no email sending, no calendar events
- No Gmail or Google Calendar integration beyond drafting
- No ML/prediction/classification in the Performance Analyzer
- Session parameter optional; when not provided and org context exists, empty
  roster returned (strict control, not packaged fallback)

### Contributing

See `AGENTS.md` for agent development guidelines, and the existing codebase for
architectural conventions. All new features should preserve existing tenant
isolation, RBAC, and authentication behavior.