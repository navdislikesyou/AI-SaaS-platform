/**
 * Tests for the protected routing and the role-aware navigation.
 *
 * The rule under test is that a protected route waits for the session to be
 * known before it decides anything. A route that redirects while the session
 * is still loading would bounce a signed-in user to the login screen on every
 * reload.
 *
 * The pages are stubbed so the assertions are about routing, not about the
 * content of the agent screens.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { AUTH_STATUS } from './context/AuthContext';

const authState = vi.hoisted(() => ({
  status: 'loading',
  user: null,
  hasRole: () => false,
  isAdmin: () => false,
  isManager: () => false,
}));

vi.mock('./context/AuthContext', () => ({
  AUTH_STATUS: {
    LOADING: 'loading',
    AUTHENTICATED: 'authenticated',
    UNAUTHENTICATED: 'unauthenticated',
  },
  ROLES: { EMPLOYEE: 'employee', MANAGER: 'manager', ADMIN: 'admin' },
  useAuth: () => authState,
}));

vi.mock('./pages/LandingPage', () => ({ default: () => <div>Landing</div> }));
vi.mock('./pages/AuthPage', () => ({ default: () => <div>Sign in</div> }));
vi.mock('./pages/AuthorizationPage', () => ({ default: () => <div>Authorizing</div> }));
vi.mock('./pages/OrchestratorPage', () => ({ default: () => <div>Command center</div> }));
vi.mock('./pages/AgentDirectoryPage', () => ({ default: () => <div>Agents</div> }));
vi.mock('./pages/HiringAIPage', () => ({ default: () => <div>Hiring</div> }));
vi.mock('./pages/ResearchAIPage', () => ({ default: () => <div>Research</div> }));
vi.mock('./pages/KnowledgeAIPage', () => ({ default: () => <div>Knowledge</div> }));
vi.mock('./pages/AutomationAIPage', () => ({ default: () => <div>Automation</div> }));
vi.mock('./pages/PerformanceAIPage', () => ({ default: () => <div>Performance</div> }));
vi.mock('./pages/InsightsAIPage', () => ({ default: () => <div>Insights</div> }));
vi.mock('./pages/SettingsPage', () => ({ default: () => <div>Settings</div> }));
vi.mock('./pages/OrganizationPage', () => ({ default: () => <div>Organization</div> }));

/**
 * Render the application at one route.
 *
 * @param {string} route The route to open.
 */
function renderAt(route) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>
  );
}

describe('protected routes', () => {
  beforeEach(() => {
    authState.status = AUTH_STATUS.LOADING;
    authState.user = null;
    authState.hasRole = () => false;
    authState.isAdmin = () => false;
    authState.isManager = () => false;
  });

  it('waits for the session instead of redirecting while it is unknown', () => {
    renderAt('/orchestrator');

    expect(screen.getByText(/Restoring your session/i)).toBeInTheDocument();
    expect(screen.queryByText('Sign in')).not.toBeInTheDocument();
  });

  it('shows the protected page once the session is authenticated', async () => {
    authState.status = AUTH_STATUS.AUTHENTICATED;
    authState.user = { id: 'user-1', name: 'Aarti Rao', role: 'admin' };

    renderAt('/orchestrator');

    expect(await screen.findByText('Command center')).toBeInTheDocument();
  });

  it('redirects to the login screen when there is no session', async () => {
    authState.status = AUTH_STATUS.UNAUTHENTICATED;

    renderAt('/orchestrator');

    expect(await screen.findByText('Sign in')).toBeInTheDocument();
  });

  it('sends an already-signed-in visitor away from the login screen', async () => {
    authState.status = AUTH_STATUS.AUTHENTICATED;
    authState.user = { id: 'user-1', name: 'Aarti Rao', role: 'admin' };

    renderAt('/login');

    expect(await screen.findByText('Command center')).toBeInTheDocument();
  });

  it('refuses a page that needs a role the user does not have', async () => {
    authState.status = AUTH_STATUS.AUTHENTICATED;
    authState.user = { id: 'user-1', name: 'Aarti Rao', role: 'employee' };
    authState.hasRole = (role) => role === 'employee';

    renderAt('/organization');

    expect(await screen.findByText(/Not available/i)).toBeInTheDocument();
    expect(screen.queryByText('Organization')).not.toBeInTheDocument();
  });

  it('allows a page when the user holds the required role', async () => {
    authState.status = AUTH_STATUS.AUTHENTICATED;
    authState.user = { id: 'user-1', name: 'Aarti Rao', role: 'admin' };
    authState.hasRole = (role) => role === 'admin';

    renderAt('/organization');

    expect(await screen.findByText('Organization')).toBeInTheDocument();
  });

  it('keeps the settings page open for a signed-in employee', async () => {
    authState.status = AUTH_STATUS.AUTHENTICATED;
    authState.user = { id: 'user-1', name: 'Aarti Rao', role: 'employee' };

    renderAt('/settings');

    expect(await screen.findByText('Settings')).toBeInTheDocument();
  });
});
