/**
 * Knowledge Agent document service.
 *
 * Two calls, both multipart- or JSON-shaped:
 *   - POST /knowledge/documents  upload a document and index it
 *   - GET  /knowledge/documents  list the documents this instance has indexed
 *
 * The backend response is the only source of truth for what was indexed. This
 * module never invents a document record, because a document that failed to
 * index must not appear in the selector as if it had succeeded.
 */

import { apiClient } from './api';

/** Field name the backend expects for the uploaded file. */
export const UPLOAD_FIELD = 'file';

/**
 * Extensions the backend accepts.
 *
 * This mirrors `SUPPORTED_EXTENSIONS` in
 * `backend/app/services/document_upload.py` and is only used to filter the file
 * picker and to fail fast. The backend revalidates everything; this list is a
 * convenience, never the security boundary.
 */
export const SUPPORTED_UPLOAD_EXTENSIONS = ['.pdf', '.docx', '.txt'];

/**
 * `accept` attribute value for the file input.
 */
export const UPLOAD_ACCEPT_ATTRIBUTE = SUPPORTED_UPLOAD_EXTENSIONS.join(',');

/**
 * Report whether a filename has an extension the backend accepts.
 *
 * @param {string} filename
 * @returns {boolean}
 */
export function hasSupportedExtension(filename) {
  if (typeof filename !== 'string') return false;

  const lower = filename.toLowerCase();
  return SUPPORTED_UPLOAD_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/**
 * Human-readable list of accepted formats, for UI copy.
 */
export const SUPPORTED_UPLOAD_LABEL = SUPPORTED_UPLOAD_EXTENSIONS.join(', ');

export const knowledgeService = {
  /**
   * Upload a document and have the backend index it.
   *
   * The request blocks until extraction, chunking, embedding, and Chroma
   * indexing have all finished. That is the backend's synchronous behaviour and
   * it is what lets the UI report success honestly: there is no "queued" state
   * to confuse with "done".
   *
   * @param {File} file
   * @returns {Promise<object>} The standard envelope from the backend.
   */
  async uploadDocument(file) {
    const formData = new FormData();
    formData.append(UPLOAD_FIELD, file);

    return apiClient.postForm('/knowledge/documents', formData);
  },

  /**
   * List documents already indexed by this backend instance.
   *
   * @returns {Promise<Array<object>>} Documents, newest first.
   */
  async listDocuments() {
    const response = await apiClient.get('/knowledge/documents');

    return response?.data?.documents || [];
  },
};