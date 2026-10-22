/**
 * Tests for the role-aware navigation.
 *
 * The navigation reflects the backend's role values. An organization admin
 * sees the user directory; a manager and an employee do not, because the
 * backend would refuse those requests anyway.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import Navigation from './Navigation';

const authState = vi.hoisted(() => ({
  user: null,
  isAdmin: false,
  logout: vi.fn(),
}));

vi.mock('../context/AuthContext', () => ({
  ROLES: { EMPLOYEE: 'employee', MANAGER: 'manager', ADMIN: 'admin' },
  roleLabel: (role) =>
    ({ admin: 'Administrator', manager: 'Manager', employee: 'Employee' })[role] || 'Member',
  useAuth: () => authState,
}));

vi.mock('../hooks/useSystemHealth', () => ({
  useSystemHealth: () => ({ isOnline: true, health: { version: '0.1.0' } }),
}));

/**
 * Render the navigation with one signed-in user.
 *
 * @param {object|null} user The signed-in user.
 * @param {boolean} isAdmin Whether the user is an organization admin.
 */
function renderNav(user, isAdmin) {
  authState.user = user;
  authState.isAdmin = isAdmin;

  return render(
    <MemoryRouter>
      <Navigation />
    </MemoryRouter>
  );
}

describe('Navigation', () => {
  beforeEach(() => {
    authState.user = null;
    authState.isAdmin = false;
    authState.logout = vi.fn();
  });

  it('shows the user directory to an organization admin', () => {
    renderNav({ id: 'user-1', name: 'Aarti Rao', role: 'admin', avatar: 'AR' }, true);

    expect(screen.getByText('Team Directory')).toBeInTheDocument();
  });

  it('hides the user directory from a manager', () => {
    renderNav({ id: 'user-2', name: 'Omkar Shenwai', role: 'manager', avatar: 'OS' }, false);

    expect(screen.queryByText('Team Directory')).not.toBeInTheDocument();
    expect(screen.getByText('Activity History')).toBeInTheDocument();
  });

  it('hides the user directory from an employee', () => {
    renderNav({ id: 'user-3', name: 'Priya Patel', role: 'employee', avatar: 'PP' }, false);

    expect(screen.queryByText('Team Directory')).not.toBeInTheDocument();
  });

  it('shows the signed-in user and their role', () => {
    renderNav({ id: 'user-1', name: 'Aarti Rao', role: 'admin', avatar: 'AR' }, true);

    expect(screen.getByText('Aarti Rao')).toBeInTheDocument();
    expect(screen.getByText('Administrator')).toBeInTheDocument();
  });

  it('shows the role as a readable label rather than the raw value', () => {
    renderNav({ id: 'user-2', name: 'Omkar Shenwai', role: 'manager', avatar: 'OS' }, false);

    expect(screen.getByText('Manager')).toBeInTheDocument();
    expect(screen.queryByText('manager')).not.toBeInTheDocument();
  });

  it('shows the organization the user belongs to', () => {
    renderNav({ id: 'user-1', name: 'Aarti Rao', role: 'admin', organizationId: 'org-42' }, true);

    expect(screen.getByText('org-42')).toBeInTheDocument();
  });

  it('signs the user out through the auth context', async () => {
    renderNav({ id: 'user-1', name: 'Aarti Rao', role: 'admin' }, true);

    const button = screen.getByTitle('Sign Out');
    button.click();

    await waitFor(() => expect(authState.logout).toHaveBeenCalled());
  });
});
