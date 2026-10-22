import { apiClient } from './api';

/** Field name the backend expects for the uploaded file. */
export const UPLOAD_FIELD = 'file';

/**
 * Formats the backend accepts for an employee directory.
 *
 * This mirrors `SUPPORTED_FORMATS` in
 * `backend/app/services/employee_directory.py` and is only used to filter the
 * file picker and to fail fast. The backend revalidates everything; this list is
 * a convenience, never the security boundary.
 */
export const SUPPORTED_DIRECTORY_EXTENSIONS = ['.json', '.csv'];

/** `accept` attribute value for the file input. */
export const UPLOAD_ACCEPT_ATTRIBUTE = SUPPORTED_DIRECTORY_EXTENSIONS.join(',');

/**
 * Whether a filename has an accepted extension.
 *
 * @param {string} filename
 * @returns {boolean}
 */
export function hasSupportedExtension(filename) {
  if (typeof filename !== 'string') return false;
  const lower = filename.toLowerCase();
  return SUPPORTED_DIRECTORY_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/** Human-readable format list for the file input hint. */
export const SUPPORTED_UPLOAD_LABEL = SUPPORTED_DIRECTORY_EXTENSIONS.join(', ');

export const automationService = {
  /**
   * Upload one employee directory.
   *
   * Resolves with the raw envelope so the caller can read both the directory
   * summary and the record preview the backend returns.
   *
   * @param {File} file
   * @returns {Promise<object>}
   */
  async uploadDirectory(file) {
    const formData = new FormData();
    formData.append(UPLOAD_FIELD, file);

    return apiClient.postForm('/automation/directories', formData);
  },

  /**
   * List uploaded employee directories, newest first.
   *
   * @returns {Promise<Array<object>>}
   */
  async listDirectories() {
    const response = await apiClient.get('/automation/directories');

    return response?.data?.directories || [];
  },

  /**
   * Read the employee records of one uploaded directory.
   *
   * @param {string} directoryId
   * @returns {Promise<{ directory: object, employees: Array<object> }>}
   */
  async getDirectory(directoryId) {
    return apiClient.get(`/automation/directories/${directoryId}`);
  },
};