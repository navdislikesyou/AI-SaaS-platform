/**
 * Tests for the auth service.
 *
 * The backend's real contract is asserted here: the login endpoint takes its
 * credentials as query parameters and returns the access token in the body,
 * while the refresh token stays in an HttpOnly cookie. These tests check that
 * the token is extracted, that a rejected credential is an error rather than a
 * silent success, and that a startup with no cookie leaves the caller signed
 * out.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { authService, toSessionUser } from './authService';
import { getAccessToken, setAccessToken } from './api';

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => (name === 'content-type' ? 'application/json' : null),
    },
    json: async () => body,
  };
}

const PROFILE = {
  id: 'user-1',
  email: 'aarti@example.com',
  full_name: 'Aarti Rao',
  role: 'manager',
  organization_id: 'org-1',
  is_active: true,
  token_version: 3,
  access_token: 'token-abc',
};

describe('authService', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    setAccessToken(null);
  });

  afterEach(() => {
    setAccessToken(null);
  });

  it('sends the credentials to the login endpoint and keeps the access token', async () => {
    fetchMock.mockResolvedValue(jsonResponse(PROFILE));

    const user = await authService.login('aarti@example.com', 'secret');

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/auth/login');
    expect(String(url)).toContain('email=aarti%40example.com');
    expect(String(url)).toContain('password=secret');
    expect(options.credentials).toBe('include');

    expect(getAccessToken()).toBe('token-abc');
    expect(user.id).toBe('user-1');
    expect(user.email).toBe('aarti@example.com');
    expect(user.name).toBe('Aarti Rao');
    expect(user.role).toBe('manager');
    expect(user.organizationId).toBe('org-1');
  });

  it('raises when the backend rejects the credentials', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'INVALID_CREDENTIALS', message: 'Invalid email or password.' } }, 401)
    );

    await expect(authService.login('aarti@example.com', 'wrong')).rejects.toMatchObject({
      status: 401,
      code: 'INVALID_CREDENTIALS',
    });
  });

  it('does not keep a token when the login fails', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: 'INVALID_CREDENTIALS' } }, 401));

    await authService.login('aarti@example.com', 'wrong').catch(() => {});

    expect(getAccessToken()).toBeNull();
  });

  it('reports an unreachable server as a network error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(authService.login('aarti@example.com', 'secret')).rejects.toMatchObject({
      status: 0,
      code: 'NETWORK_ERROR',
    });
  });

  it('reads the current user from the me endpoint', async () => {
    setAccessToken('token-abc');
    fetchMock.mockResolvedValue(jsonResponse({ ...PROFILE, access_token: undefined }));

    const user = await authService.fetchCurrentUser();

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/auth/me');
    expect(options.headers.Authorization).toBe('Bearer token-abc');
    expect(user.email).toBe('aarti@example.com');
  });

  it('treats a 401 from the me endpoint as "not signed in"', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401));

    await expect(authService.fetchCurrentUser()).resolves.toBeNull();
  });

  it('rebuilds the session from the refresh cookie on startup', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ...PROFILE, access_token: 'renewed-token' }, 200))
      .mockResolvedValueOnce(jsonResponse({ ...PROFILE, access_token: undefined }, 200));

    const user = await authService.hydrateSession();

    const [refreshUrl] = fetchMock.mock.calls[0];
    const [meUrl] = fetchMock.mock.calls[1];
    expect(String(refreshUrl)).toContain('/auth/refresh');
    expect(String(meUrl)).toContain('/auth/me');
    expect(getAccessToken()).toBe('renewed-token');
    expect(user.email).toBe('aarti@example.com');
  });

  it('leaves the caller signed out when there is no refresh cookie', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: 'INVALID_CREDENTIALS' } }, 401));

    await expect(authService.hydrateSession()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it('leaves the caller signed out when the server cannot be reached', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(authService.hydrateSession()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it('clears the local session even when the logout call fails', async () => {
    setAccessToken('token-abc');
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(authService.logout()).resolves.toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it('calls the backend logout endpoint', async () => {
    setAccessToken('token-abc');
    fetchMock.mockResolvedValue(jsonResponse({ success: true }, 200));

    await expect(authService.logout()).resolves.toBe(true);

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/auth/logout');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('include');
    expect(getAccessToken()).toBeNull();
  });

  it('maps a backend profile onto the fields the UI renders', () => {
    expect(toSessionUser(PROFILE)).toMatchObject({
      id: 'user-1',
      name: 'Aarti Rao',
      avatar: 'AR',
      role: 'manager',
      organizationId: 'org-1',
    });
  });

  it('returns null for a missing profile', () => {
    expect(toSessionUser(null)).toBeNull();
  });
});
