/**
 * Google OAuth calls for the Employee Insights Gmail connection.
 *
 * The backend owns the OAuth web flow: it issues Google's consent URL,
 * exchanges the authorization code, and stores the encrypted refresh token
 * bound to the caller's organisation. This service only drives the browser
 * through that flow and reads the resulting connection status.
 */

import { apiClient } from './api';

export const googleOAuthService = {
  /**
   * Start the OAuth flow and return Google's consent URL.
   *
   * The caller navigates the browser to the returned URL to grant
   * ``gmail.readonly`` access. After consent, Google redirects to the
   * backend callback, which stores the credential and returns here.
   *
   * @returns {Promise<{authorization_url: string, expires_in_seconds: number}>}
   */
  async authorize() {
    return apiClient.get('/google/oauth/authorize');
  },

  /**
   * Return whether the caller's organisation has a Gmail mailbox connected.
   *
   * @returns {Promise<{connected: boolean, gmail_address: string|null,
   * scopes: string[], connected_at: string|null, token_expires_at: string|null}>}
   */
  async status() {
    return apiClient.get('/google/connection');
  },

  /**
   * Remove the stored Gmail connection for the caller's organisation.
   *
   * @returns {Promise<{success: boolean, message: string}>}
   */
  async disconnect() {
    return apiClient.delete('/google/connection');
  },
};
