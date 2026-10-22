/**
 * Organization user management calls.
 *
 * The backend accepts its parameters in the query string, so every call here
 * uses the query-parameter helpers rather than a JSON body. The backend
 * decides what is permitted: listing and role changes need the admin role,
 * and assigning a manager needs the manager or admin role. The UI only ever
 * hides controls the caller would be refused anyway.
 */

import { apiClient } from './api';

/**
 * List the users in the caller's organization.
 *
 * @returns {Promise<object[]>} The organization users.
 */
export async function listUsers() {
  const response = await apiClient.get('/users/');
  return response?.data || [];
}

/**
 * Create a user in the caller's organization.
 *
 * The backend sets the initial password and returns the created profile; no
 * password is chosen or transmitted from the browser.
 *
 * @param {object} input The new user's details.
 * @param {string} input.email The user's email address.
 * @param {string} input.fullName The user's full name.
 * @param {string} [input.role] The initial role.
 * @param {string} [input.managerId] The user's manager.
 * @returns {Promise<object>} The created user.
 */
export async function createUser({ email, fullName, role, managerId }) {
  const response = await apiClient.postWithParams('/users/', {
    email,
    full_name: fullName,
    role,
    manager_id: managerId,
  });
  return response?.data || null;
}

/**
 * Change a user's role.
 *
 * @param {string} userId The user to change.
 * @param {string} newRole The new role.
 * @returns {Promise<object>} The updated user.
 */
export async function changeUserRole(userId, newRole) {
  const response = await apiClient.patchWithParams(`/users/${userId}`, { new_role: newRole });
  return response?.data || null;
}

/**
 * Activate a user.
 *
 * @param {string} userId The user to activate.
 * @returns {Promise<object>} The updated user.
 */
export async function activateUser(userId) {
  const response = await apiClient.post(`/users/${userId}/activate`);
  return response?.data || null;
}

/**
 * Deactivate a user.
 *
 * @param {string} userId The user to deactivate.
 * @returns {Promise<object>} The updated user.
 */
export async function deactivateUser(userId) {
  const response = await apiClient.post(`/users/${userId}/deactivate`);
  return response?.data || null;
}

/**
 * Assign or clear a user's manager.
 *
 * @param {string} userId The user to update.
 * @param {string|null} managerId The new manager, or null to clear it.
 * @returns {Promise<object>} The updated user.
 */
export async function setUserManager(userId, managerId) {
  const response = await apiClient.patchWithParams(`/users/${userId}/manager`, {
    manager_id: managerId,
  });
  return response?.data || null;
}

export const userService = {
  listUsers,
  createUser,
  changeUserRole,
  activateUser,
  deactivateUser,
  setUserManager,
};
