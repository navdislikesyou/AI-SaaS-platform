# AXON Frontend — React + Vite

This is the frontend for the AXON AI SaaS Platform, a React + Vite application
providing the user interface for the multi-agent platform.

## Overview

AXON frontend provides the UI for:

- **Agent execution** — interact with Knowledge, Automation, Performance, and Employee Insights agents
- **Employee directory** — view and select employees from the registered directory or uploaded directories
- **Productivity drafting** — the Automation Agent drafts actions against an employee directory
- **Data analytics** — Performance Analyzer results and visualizations
- **Document Q&A** — the Knowledge Agent for RAG over uploaded documents

The platform ships a React + Vite single-page frontend that communicates with the
FastAPI backend via `fetch` with JWT authentication.

## Technology Stack

- **Framework**: React 18 + Vite
- **Build tool**: Vite
- **UI library**: Lucide-react icons
- **Styling**: Custom CSS with AXON design system variables (dark mode compatible)
- **API communication**: `fetch` with `Authorization: Bearer <jwt-token>` header
- **State management**: React `useState`, `useEffect`, `useCallback`
- **Routing**: React Router (version-aware)
- **Custom hooks**:
  - `useEmployeeDirectory.js` — fetches active employees, manages selection
  - `useDirectoryUpload.js` — handles uploaded directory management
  - `useAuth.js` — JWT token management and organization context

## Project Structure

```
frontend/
├── src/
│   ├── pages/           # Page components
│   │   ├── AutomationAIPage.jsx   # Two-tab employee directory + draft UI (Phase 4)
│   │   ├── InsightsAIPage.jsx     # Performance insights view
│   │   └── KnowledgeAIPage.jsx    # Document Q&A interface
│   ├── hooks/           # Custom React hooks
│   │   ├── useEmployeeDirectory.js
│   │   ├── useDirectoryUpload.js
│   │   └── useAuth.js
│   ├── components/      # Reusable UI components
│   │   ├── Atoms/       # Buttons, inputs, labels
│   │   ├── Molecules/   # Search boxes, summary badges
│   │   └── Organisms/   # Page layouts, directory tabs
│   ├── api/             # API client functions
│   │   └── apiClient.js   # fetch wrapper with auth header
│   ├── styles/          # AXON design system variables
│   └── App.jsx          # Root component with routing
├── index.html           # HTML template
├── package.json         # Dependencies and scripts
├── vite.config.js       # Vite configuration
└── oxlint.config.js     # Oxlint configuration
```

## Key Frontend Features (Phase 4)

### AutomationAIPage.jsx — Two-Tab Employee Directory

The `AutomationAIPage` component provides a two-tab interface for employee
directory selection:

| Tab | Description |
|---|---|
| **Registered Employees** | Fetches active employees from the authenticated organization via `GET /api/v1/automation/employees`. Shows employee name, email, and role. Supports search and role filtering. |
| **Uploaded Directory** | Manages uploaded employee directories. Lists previously uploaded directories with preview and status. |

**Features common to both tabs:**

- **Multi-selection**: Click employees to add them to the recipient list; Ctrl+click for multi-select
- **Search**: Filter employees by name in real-time
- **Role filtering**: Filter by employee role (employee/manager/admin)
- **Source-aware recipient summary**: Each recipient displays with a source label
  - `Registered Employee` — from the organization's active user roster
  - `Uploaded Contact` — from an uploaded directory
- **Selection persistence**: When switching tabs, the current selection is preserved
- **Loading states**: Skeleton loaders while data fetches
- **Error states**: Graceful error handling with retry
- **Empty states**: Friendly message when no employees/directories are available

**Individual removal**: Each selected recipient can be removed individually from the list.

### API Communication

All API calls go through `frontend/src/api/apiClient.js`, which adds the JWT
authentication header:

```javascript
// Example API client wrapper
const apiClient = {
  setToken: (token) => { /* store token in localStorage */ },
  get: async (endpoint) => {
    const response = await fetch(`/api${endpoint}`, {
      headers: { Authorization: `Bearer ${getToken()}` }
    });
    return response.json();
  },
  post: async (endpoint, body) => {
    const response = await fetch(`/api${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`
      },
      body: JSON.stringify(body)
    });
    return response.json();
  }
};
```

Authentication flow:

1. User logs in via `POST /api/v1/auth/login`
2. Access token returned in response body; refresh cookie set HttpOnly
3. Token stored in frontend `localStorage` and sent as `Authorization: Bearer <token>` on API calls
4. Token expiry handled automatically; refresh via `POST /api/v1/auth/refresh`

### Custom Hooks

#### `useEmployeeDirectory.js`

Fetches active employees from the backend and manages selection state.

```javascript
const { employees, loading, error, search, filterRole, selectEmployee, deselectEmployee } = useEmployeeDirectory({
  initialSelection: []
});
```

Key behaviors:

- Fetches from `GET /api/v1/automation/employees`
- Filters by authenticated organization
- Applies active-only filter
- Provides `selectEmployee(name, email, role)` and `deselectEmployee(name)` functions
- Provides `setSearchQuery(text)` and `setFilterRole(role)` for filtering

#### `useDirectoryUpload.js`

Manages uploaded employee directories.

```javascript
const { directories, uploadDirectory, removeDirectory } = useDirectoryUpload();
```

Key behaviors:

- Lists directories from `GET /api/v1/automation/directories`
- Provides `uploadDirectory(file)` function for new uploads
- Provides `removeDirectory(directoryId)` to remove a directory

## Routes

| Route | Path | Description |
|---|---|---|
| `/` | `/` | Home/dashboard (agent selection) |
| `/automation` | `/automation` | Automation interface with employee directory (AutomationAIPage) |
| `/insights` | `/insights` | Performance insights view |
| `/knowledge` | `/knowledge` | Knowledge Agent document Q&A |
| `/auth/login` | `/auth/login` | Login page |
| `/auth/refresh` | `/auth/refresh` | Token refresh (handled via cookie) |

## Development

```bash
cd frontend
npm install          # install dependencies
npm run dev          # development server with HMR
npm run build        # production build
```

## API Client Architecture

The frontend communicates with the backend through a thin API client layer.
All endpoints are relative to `/api` which proxies to the backend at
`http://127.0.0.1:8000`.

Key principles:

- **Authentication**: JWT token via `Authorization: Bearer` header
- **Error handling**: Check `response.ok`; handle 401 (redirect to login), 403, 404, 422
- **Loading**: Show spinner/skeleton while awaiting responses
- **Empty states**: Render friendly message when data is empty
- **No real emails sent**: Draft-only behavior is enforced; the Automation Agent
  never sends email from the frontend

## Styling Conventions

- Use AXON design system CSS variables defined in `frontend/src/styles/`
- Dark mode compatible: all colors have light and dark variants
- Consistent spacing: 4px base unit (matching the backend code style convention)
- Form elements: uniform input height, focus ring using `outline: 2px solid var(--axon-focus)`
- Buttons: primary (axon-primary), secondary, ghost
- Respect `prefers-reduced-motion` for animations

## Known Limitations

- Frontend two-tab UI is fully implemented and verified; session propagation is
  optional on the backend; when no session is available with org context, the
  service returns an empty roster (strict control, not packaged fallback)
- No real email sending from the frontend; Automation Agent drafts only
- Backend session threading verified end-to-end through the complete call chain
- Uploaded directories are local MVPs; not shared between instances

## Contributing

See `AGENTS.md` for agent development guidelines. All new features should
preserve existing tenant isolation, RBAC, and authentication behavior. The
frontend should not implement email sending, calendar events, or any external
side effects.