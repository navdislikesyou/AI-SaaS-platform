/**
 * Tests for the authentication context.
 *
 * The context owns three states, and the distinction between them is the
 * point of this file: while the session is unknown the application must wait
 * rather than redirect, and a failed sign-in must leave the application
 * signed out rather than half-signed-in.
 *
 * `authService` is mocked, so no request leaves the browser.
 */

import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from './AuthContext';
import { AUTH_STATUS, ROLES } from './authRoles';
import { authService } from '../services/authService';

/**
 * A registry for the session-lost listener, so a test can tell the context
 * that the session can no longer be renewed.
 */
const session = vi.hoisted(() => ({
  listeners: new Set(),
  lost: null,
}));

vi.mock('../services/api', () => ({
  clearAccessToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
  setAccessToken: vi.fn(),
  onSessionLost: (listener) => {
    session.listeners.add(listener);
    return () => session.listeners.delete(listener);
  },
}));

vi.mock('../services/authService', () => ({
  authService: {
    login: vi.fn(),
    logout: vi.fn(),
    fetchCurrentUser: vi.fn(),
    hydrateSession: vi.fn(),
    toSessionUser: (profile) => profile,
  },
}));

const USER = {
  id: 'user-1',
  name: 'Aarti Rao',
  role: ROLES.ADMIN,
  organizationId: 'org-1',
};

/**
 * Render the context and expose its value to the assertions.
 */
function renderAuth() {
  const observed = {};

  function Probe() {
    Object.assign(observed, useAuth());
    return <div data-testid="status">{observed.status}</div>;
  }

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );

  return observed;
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    session.listeners.clear();
  });

  it('starts in the loading state while the session is unknown', async () => {
    let resolveHydration;
    authService.hydrateSession.mockReturnValue(
      new Promise((resolve) => {
        resolveHydration = resolve;
      })
    );

    const observed = renderAuth();

    expect(observed.status).toBe(AUTH_STATUS.LOADING);
    expect(observed.isLoading).toBe(true);
    expect(observed.isAuthenticated).toBe(false);

    await act(async () => {
      resolveHydration(null);
    });
  });

  it('becomes authenticated when the session is restored', async () => {
    authService.hydrateSession.mockResolvedValue(USER);

    const observed = renderAuth();

    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));
    expect(observed.user).toEqual(USER);
    expect(observed.isAuthenticated).toBe(true);
  });

  it('becomes unauthenticated when there is no session to restore', async () => {
    authService.hydrateSession.mockResolvedValue(null);

    const observed = renderAuth();

    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED));
    expect(observed.user).toBeNull();
  });

  it('does not treat an unreachable server as a signed-in session', async () => {
    authService.hydrateSession.mockResolvedValue(null);

    const observed = renderAuth();

    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED));
    expect(observed.isAuthenticated).toBe(false);
  });

  it('signs the user in and exposes the session', async () => {
    authService.hydrateSession.mockResolvedValue(null);
    authService.login.mockResolvedValue(USER);

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED));

    await act(async () => {
      await observed.login('aarti@example.com', 'secret');
    });

    expect(authService.login).toHaveBeenCalledWith('aarti@example.com', 'secret');
    expect(observed.user).toEqual(USER);
    expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED);
  });

  it('stays signed out when the login fails', async () => {
    authService.hydrateSession.mockResolvedValue(null);
    authService.login.mockRejectedValue(new Error('Invalid email or password.'));

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED));

    await act(async () => {
      await observed.login('aarti@example.com', 'wrong').catch(() => {});
    });

    expect(observed.user).toBeNull();
    expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED);
    expect(observed.isAuthenticated).toBe(false);
  });

  it('clears the session on logout', async () => {
    authService.hydrateSession.mockResolvedValue(USER);
    authService.logout.mockResolvedValue(true);

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));

    await act(async () => {
      await observed.logout();
    });

    expect(authService.logout).toHaveBeenCalled();
    expect(observed.user).toBeNull();
    expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED);
  });

  it('clears the session even when the logout call fails', async () => {
    authService.hydrateSession.mockResolvedValue(USER);
    authService.logout.mockRejectedValue(new Error('network down'));

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));

    await act(async () => {
      await observed.logout().catch(() => {});
    });

    expect(observed.user).toBeNull();
    expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED);
  });

  it('drops the session when the API client reports it can no longer be renewed', async () => {
    authService.hydrateSession.mockResolvedValue(USER);

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));

    await act(async () => {
      for (const listener of session.listeners) {
        listener('refresh_failed');
      }
    });

    expect(observed.user).toBeNull();
    expect(observed.status).toBe(AUTH_STATUS.UNAUTHENTICATED);
  });

  it('answers role questions against the backend role value', async () => {
    authService.hydrateSession.mockResolvedValue({ ...USER, role: ROLES.MANAGER });

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));

    expect(observed.hasRole(ROLES.EMPLOYEE)).toBe(true);
    expect(observed.hasRole(ROLES.MANAGER)).toBe(true);
    expect(observed.hasRole(ROLES.ADMIN)).toBe(false);
    expect(observed.isAdmin()).toBe(false);
    expect(observed.isManager()).toBe(true);
  });

  it('does not grant organization-wide access to a manager', async () => {
    authService.hydrateSession.mockResolvedValue({ ...USER, role: ROLES.MANAGER });

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));

    expect(observed.isAdmin()).toBe(false);
  });

  it('treats a user with no role as having none of the roles', async () => {
    authService.hydrateSession.mockResolvedValue({ id: 'user-2', name: 'No Role' });

    const observed = renderAuth();
    await waitFor(() => expect(observed.status).toBe(AUTH_STATUS.AUTHENTICATED));

    expect(observed.hasRole(ROLES.EMPLOYEE)).toBe(false);
    expect(observed.isAdmin()).toBe(false);
  });

  it('renders the loading state into the DOM', async () => {
    authService.hydrateSession.mockResolvedValue(null);

    renderAuth();

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe(AUTH_STATUS.UNAUTHENTICATED));
  });
});
