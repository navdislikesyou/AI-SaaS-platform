# AXON PHASE 4 — EMPLOYEE DIRECTORY ARCHITECTURE INSPECTION REPORT

## 1. Existing Directory Implementation

### 1.1 Packaged Directory (`backend/automation_agent/directory.py`)

The packaged directory is a read-only module that queries `data/employees.json`, a static JSON file shipped with the agent package.

**Key features:**
- `PackagedDirectory` class with methods:
  - `get_all_employees()` - returns active employees (defaults `active=True`)
  - `get_by_id(employee_id)` - look up by employee identifier
  - `search_employees(query)` - search by name, email, or employee_id (case-insensitive)
  - `get_by_role(role)` - filter by role (case-insensitive)
  - `get_by_department(department)` - filter by department (case-insensitive)
  - `get_roles()` - enumerate distinct roles (excludes "Unassigned")
  - `get_departments()` - enumerate distinct departments (excludes "Unassigned")
  - `get_selected_employees(employee_ids)` - resolve list of IDs to employees

**Packaged data** (`backend/automation_agent/data/employees.json`):
- 4 employees: Navneet Verma, Mohammed Ashhar Khan, Pulkita Verma, Omkar Shenwai
- All have `role: "Unassigned"` and `department: "Unassigned"`
- All have `active: true`
- Each has `employee_id`, `name`, `email`

**Limitations:**
- No organization scoping - shared across all organizations
- No `role` or `department` data useful for filtering (all "Unassigned")
- No way to mark employees as inactive
- File-based, not queryable via API

### 1.2 Uploaded Directories (`app/api/v1/automation.py`)

- `POST /automation/directories` - upload CSV/JSON files with employee records
- Each record validated to have `name` and `email` fields
- Stamped with uploader's `organization_id` and `owner_id`
- Scoped to uploader's organization for listing/detail lookups
- Separate from packaged directory - never reaches `PackagedDirectory` module

### 1.3 Automation Agent Integration

**`automation_agent/automation_agent.py`**:
- `__init__()` loads `employees.json` if no `employees_file` provided
- `parse_instruction(instruction, employees)` - receives employee roster; matches names in instruction text
- `find_emails(attendees, employees)` - resolves attendee names to employee records
- `_roster(employees)` - returns `self.employees` (packaged) or passed list
- `execute(instruction, employees, user_context)` - full workflow: parse → resolve recipients → generate draft

**`automation_agent/service.py`**:
- `AutomationService.__init__()` loads agent with packaged directory
- `execute(instruction, employees, user_context)` - passes roster through
- `execute_html()` - same recipient lookup with HTML template rendering

### 1.4 User Model (`app/models.py`)

The existing `User` model already contains:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `email` | String(191) | Unique, normalized email |
| `full_name` | String(191) | User's full name |
| `role` | String(20) | EMPLOYEE/MANAGER/ADMIN, default EMPLOYEE |
| `is_active` | Boolean | Default True |
| `organization_id` | UUID | ForeignKey to organizations (nullable) |
| `manager_id` | UUID | Self-referential FK to User (nullable) |
| `created_at` / `updated_at` | DateTime | UTC timestamps |

**Indexes**: `ix_users_email` (unique), `ix_users_organization_id`

### 1.5 Current Integration Points

| Component | Uses Directory | Notes |
|---|---|---|
| Automation Agent drafting | ✅ Packaged directory (default) | Can override with uploaded directory |
| Gmail sending (`gmail_send.py`) | ✅ Verified org users only | Production: directory addresses rejected |
| Meeting creation | ✅ Attendee resolution from directory | Attendees stored separately |
| Meeting invitations | ✅ Resolved via `find_emails()` | Draft-only, never sent automatically |
| Automated meeting reminders | ✅ Uses resolved attendee emails | From meeting record, not directory |
| Employee Insights Gmail | ✅ Verified org users | Separate from automation directory |

## 2. Architectural Problems Identified

### Problem 1: No Organization Scoping on Packaged Directory
- **Severity**: HIGH
- **Impact**: Packaged `employees.json` is shared across all organizations; employee data from one org visible to others
- **Evidence**: `employees.json` has no `organization_id` field; `PackagedDirectory` has no org filtering

### Problem 2: Packaged Employees Have No Meaningful Role/Department
- **Severity**: MEDIUM
- **Impact**: `role: "Unassigned"` and `department: "Unassigned"` for all 4 entries; `get_by_role()` and `get_by_department()` effectively return all active employees
- **Evidence**: All packaged entries have these as placeholder values

### Problem 3: No Inactive Employee Status
- **Severity**: LOW
- **Impact**: All packaged entries have `active: True`; no way to mark employees as inactive without editing the JSON file
- **Evidence**: `get_all_employees()` filters on `employee.get("active", True)` - default is True

### Problem 4: Inconsistent Recipient Resolution
- **Severity**: HIGH
- **Gmail sending** requires verified org users
- **Automation drafting** uses packaged directory (no org scoping)
- **Inconsistency**: Same application, different recipient resolution paths

### Problem 5: No API for Org User Listing
- **Severity**: MEDIUM
- **Impact**: No way to list active users in an organization for recipient selection in frontend
- **Evidence**: No endpoint exists to list org users; frontend must use packaged directory or uploaded directory

### Problem 5: Uploaded Directories vs Packaged Directory Inconsistency
- **Severity**: MEDIUM
- **Uploaded directories**: org-scoped, validated, stored server-side
- **Packaged directory**: global, no validation, static file
- **Impact**: Different behavior for same operation (recipient resolution)

## 3. Recommended Phase 4 Architecture

### Core Principle
**The existing AXON User model should be the source of truth for registered employees.** The `users` table already has all required fields (email, name, role, active status, organization_id).

### Recommended Implementation

#### 3.1 Organization-Scoped User Query Service
Add a service function to list active users in an organization:

```python
# app/services/user_service.py
async def list_active_users_by_organization(organization_id: str) -> list[dict[str, Any]]:
    """Return active users in an organization, suitable for recipient selection."""
    async with get_session() as session:
        result = await session.execute(
            select(User)
            .where(User.organization_id == organization_id, User.is_active == True)
            .order_by(User.full_name)
        )
        users = result.scalars().all()
        return [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "active": user.is_active,
            }
            for user in users
        ]
```

#### 3.2 Updated `PackagedDirectory` with Org Fallback
Modify `PackagedDirectory` to prefer org users when available, fall back to packaged data:

```python
# In directory.py, update get_all_employees to also check org users
def get_all_employees(self) -> list[dict[str, Any]]:
    # First, try to get from org users (new)
    # Fall back to packaged employees
    ...
```

#### 3.3 New API Endpoint
```
GET /api/v1/automation/employees
```
- Returns active users in the caller's organization
- Includes: id, email, full_name, role
- Auth: Manager/Admin required

#### 3.4 Frontend Recipient Selection
- Default to org users when available
- Show packaged directory as fallback/alternative
- Include role/department filters from org users

#### 3.5 Backward Compatibility
- Packaged directory still works unchanged
- Uploaded directories still work
- All existing APIs unchanged
- New endpoint opt-in

## 4. Database Changes

**NOT REQUIRED** - The existing User model already provides:

| Required Field | Source |
|---|---|
| `id` | `users` table PK |
| `email` | `users.email` |
| `full_name` | `users.full_name` |
| `role` | `users.role` (EMPLOYEE/MANAGER/ADMIN) |
| `is_active` | `users.is_active` |
| `organization_id` | `users.organization_id` (FK) |

No new tables, columns, or migrations needed.

## 5. Security and Backward-Compatibility Considerations

| Consideration | Approach |
|---|---|
| **Cross-org data leakage** | Fixed: all queries filter by `organization_id` from authenticated principal |
| **Existing packaged directory** | Unchanged - still works as fallback |
| **Uploaded directories** | Unchanged - org-scoped via API |
| **Inactivated users** | New: `is_active=False` prevents selection in draft resolution |
| **Gmail sending** | Unchanged - still verifies org users via OAuth |
| **Meeting history** | Unchanged - inactivation doesn't remove historical attendee records |
| **API contract** | No breaking changes; new endpoint optional |
| **Frontend impact** | Opt-in: new recipient source, packaged directory remains |

## 6. Testing Strategy

| Test Type | Scope |
|---|---|
| **Unit tests** | - `PackagedDirectory.get_by_role()` with mock data<br>- `list_active_users_by_organization()` with various orgs<br>- Filtering by role/department |
| **Integration tests** | - `GET /automation/employees` endpoint<br>- Recipient resolution with org users<br>- Cross-org isolation (403) |
| **End-to-end** | - Draft action with org users<br>- Draft action with packaged directory<br>- Draft action with uploaded directory<br>- Inactivated user handling |
| **Regression** | - All existing pytest suites pass<br>- No change to Gmail sending tests<br>- No change to existing meeting API tests |

### Test Scenarios

1. **Org users listed correctly**: `GET /automation/employees` returns only users in caller's org
2. **Cross-org access denied**: User from org A cannot list org B's users (403)
3. **Inactivated users excluded**: Users with `is_active=False` not in active list
4. **Role filtering works**: `get_by_role()` filters by actual org roles (EMPLOYEE/MANAGER/ADMIN)
5. **Packaged directory fallback**: When no org context, packaged directory still works
6. **Gmail sending unchanged**: Unchanged verification of org users

## 7. Implementation Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Organizations with no users** | Empty list returned; drafting falls back to packaged directory |
| **Role name collisions** | Use existing `UserRole` enum (EMPLOYEE/MANAGER/ADMIN) |
| **Migrating existing data** | Not needed - User model already has all fields |
| **Frontend duplication** | New endpoint complements, doesn't replace, packaged directory |
| **Gmail sending regression** | Unchanged code path; existing tests pass |

## 8. Final Recommendations

### Immediate Actions (Stage 1)
1. Add `list_active_users_by_organization()` service function
2. Add `GET /api/v1/automation/employees` API endpoint
3. Update `PackagedDirectory` to document its limitations (no org scoping)
4. Add unit tests for new service function

### Medium-Term Actions (Stage 2)
1. Update AutomationAgent to prefer org users over packaged directory
2. Update frontend recipient selection to use org users as default
3. Add role/department filtering in frontend

### Long-Term Actions (Stage 3)
1. Retire packaged `employees.json` after all orgs migrate to User model
2. Add department field to User model if needed (currently not - role suffices)
3. Add activity logging for directory resolution changes

### Non-Goals (Explicitly Out of Scope)
- ❌ Do not modify `.env` or OAuth secrets
- ❌ Do not change Phase 1, 2, or 3 behavior
- ❌ Do not introduce Celery, Redis, or new databases
- ❌ Do not delete packaged `employees.json`
- ❌ Do not rewrite existing directory upload API
- ❌ Do not change Gmail sending verification

---
**Overall Assessment**: The Phase 4 architecture is low-risk and high-value. The existing User model provides everything needed; the main work is adding organization scoping and a new API endpoint. No database migrations or new dependencies required. Backward compatibility is fully maintained.