/**
 * Session states and role values, shared by the auth context and the
 * components that read them.
 *
 * These live apart from the provider so that a component can import the role
 * names without pulling the provider in, and so that the provider file only
 * exports components.
 */

/**
 * The three states the application can be in.
 *
 * `loading` is the state during startup, before the session is known. It is
 * distinct from `unauthenticated` because a protected route must wait rather
 * than redirect: redirecting before the session is known would bounce a
 * signed-in user to the login screen on every reload.
 */
export const AUTH_STATUS = {
  LOADING: 'loading',
  AUTHENTICATED: 'authenticated',
  UNAUTHENTICATED: 'unauthenticated',
};

/**
 * The roles the backend recognises, in ascending order of privilege.
 *
 * These are the backend's own role strings, not display labels. The UI shows
 * a prettified version of the same value, but every authorization decision is
 * made against the raw value.
 */
export const ROLES = {
  EMPLOYEE: 'employee',
  MANAGER: 'manager',
  ADMIN: 'admin',
};

/**
 * Rank each role so a check can ask "at least this privileged".
 */
export const ROLE_RANK = {
  [ROLES.EMPLOYEE]: 1,
  [ROLES.MANAGER]: 2,
  [ROLES.ADMIN]: 3,
};

/**
 * Present a backend role as a readable label.
 *
 * The backend's role values are what every authorization decision is made
 * against. Only the display is prettified.
 *
 * @param {string} role The backend role value.
 * @returns {string} The label to show.
 */
export function roleLabel(role) {
  switch (role) {
    case ROLES.ADMIN:
      return 'Administrator';
    case ROLES.MANAGER:
      return 'Manager';
    case ROLES.EMPLOYEE:
      return 'Employee';
    default:
      return 'Member';
  }
}
