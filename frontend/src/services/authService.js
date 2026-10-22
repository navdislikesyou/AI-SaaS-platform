/**
 * Authentication calls against the backend.
 *
 * The backend issues an access JWT in the response body and keeps the refresh
 * token in an HttpOnly cookie. The refresh token never reaches this file: it
 * is read by the browser and sent back automatically.
 */

import { apiClient, clearAccessToken, refreshAccessToken, setAccessToken } from './api';

/**
 * Turn a backend user profile into the shape the UI renders.
 *
 * The backend uses `full_name` and a lowercase role from a fixed set. The
 * display fields are derived here so that no component has to guess how to
 * present them, and so the initials in the avatar are always consistent.
 *
 * @param {object|null} profile The backend user profile.
 * @returns {object|null} The user for the UI, or null when there is none.
 */
export function toSessionUser(profile) {
  if (!profile) {
    return null;
  }

  const fullName = profile.full_name || profile.email || 'User';
  const initials = fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');

  return {
    id: profile.id,
    email: profile.email,
    name: fullName,
    fullName,
    role: profile.role,
    organizationId: profile.organization_id || null,
    isActive: profile.is_active !== false,
    tokenVersion: profile.token_version,
    avatar: initials || 'US',
  };
}

/**
 * Authenticate with an email and password.
 *
 * A failed attempt raises the backend's error, so the caller can tell a wrong
 * password from an unreachable server. There is no demo fallback: if the
 * backend does not answer, the login failed.
 *
 * @param {string} email The user's email address.
 * @param {string} password The user's password.
 * @returns {Promise<object>} The signed-in user.
 */
export async function login(email, password) {
  const profile = await apiClient.postWithParams(
    '/auth/login',
    { email, password },
    { skipAuth: true }
  );

  setAccessToken(profile?.access_token || null);

  return toSessionUser(profile);
}

/**
 * Read the current session from the backend.
 *
 * Called after the access token has been established. The backend answers 401
 * when the token is not valid, which is not an error condition here; it
 * simply means the user is not signed in.
 *
 * @returns {Promise<object|null>} The signed-in user, or null when there is
 *   no session.
 */
export async function fetchCurrentUser() {
  try {
    const profile = await apiClient.get('/auth/me');
    return toSessionUser(profile);
  } catch (error) {
    if (error?.status === 401) {
      clearAccessToken();
      return null;
    }
    throw error;
  }
}

/**
 * Re-establish a session on page load.
 *
 * The access token lives in memory only, so a page load starts with none of
 * it. The refresh cookie is the one credential that survives a reload, so the
 * session is rebuilt from it: `/auth/refresh` exchanges the cookie for a fresh
 * access token, and `/auth/me` then confirms who the caller is.
 *
 * A missing, expired, or revoked cookie means there is no session, which is
 * an ordinary outcome rather than a failure. A server that cannot be reached
 * is also treated as "not signed in": an unreachable backend must never be
 * reported as a working session.
 *
 * @returns {Promise<object|null>} The signed-in user, or null when there is
 *   no session.
 */
export async function hydrateSession() {
  let renewed = null;

  try {
    renewed = await refreshAccessToken();
  } catch {
    renewed = null;
  }

  if (!renewed) {
    clearAccessToken();
    return null;
  }

  try {
    return await fetchCurrentUser();
  } catch {
    clearAccessToken();
    return null;
  }
}

/**
 * Revoke the refresh token and end the session on the server.
 *
 * The local session is cleared even when the call fails, because the user
 * asked to sign out and leaving them signed in on a network error would be
 * surprising.
 *
 * @returns {Promise<boolean>} True when the server acknowledged the logout.
 */
export async function logout() {
  try {
    await apiClient.post('/auth/logout', undefined, { skipAuth: true });
    return true;
  } catch {
    return false;
  } finally {
    clearAccessToken();
  }
}

export const authService = {
  login,
  logout,
  fetchCurrentUser,
  hydrateSession,
  toSessionUser,
};
