/**
 * Centralized API client for communicating with the backend FastAPI service.
 * Handles base URL configuration, request headers, JSON serialization,
 * X-Request-ID correlation, and structured error responses.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export class ApiError extends Error {
  constructor(message, status = 500, code = 'INTERNAL_ERROR', details = null, requestId = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

async function request(endpoint, options = {}) {
  const url = endpoint.startsWith('http')
    ? endpoint
    : `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  // FormData must not carry an explicit Content-Type: the browser has to set
  // it itself so the multipart boundary matches the body it is sending. Setting
  // it to application/json here is the classic cause of "multipart/form-data
  // parsing failed" on the server.
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

  const headers = {
    'Accept': 'application/json',
    ...(options.body && !isFormData ? { 'Content-Type': 'application/json' } : {}),
    ...options.headers,
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const requestId = response.headers.get('X-Request-ID');
    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');
    const data = isJson ? await response.json() : null;

    if (!response.ok) {
      const errorCode = data?.error?.code || data?.code || `HTTP_${response.status}`;
      const errorMessage =
        data?.error?.message ||
        data?.message ||
        data?.detail ||
        `Request failed with status ${response.status}`;
      const errorDetails = data?.error?.details || data?.details || null;

      throw new ApiError(
        errorMessage,
        response.status,
        errorCode,
        errorDetails,
        requestId || data?.request_id
      );
    }

    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    // Network errors or fetch failures
    throw new ApiError(
      error.message || 'Network request failed. Is the backend server running?',
      0,
      'NETWORK_ERROR',
      null,
      null
    );
  }
}

export const apiClient = {
  get(endpoint, options = {}) {
    return request(endpoint, { ...options, method: 'GET' });
  },

  post(endpoint, data, options = {}) {
    return request(endpoint, {
      ...options,
      method: 'POST',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  },

  put(endpoint, data, options = {}) {
    return request(endpoint, {
      ...options,
      method: 'PUT',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  },

  delete(endpoint, options = {}) {
    return request(endpoint, { ...options, method: 'DELETE' });
  },

  /**
   * POST a multipart/form-data body.
   *
   * The body is passed through untouched so the browser can generate the
   * multipart boundary. Never JSON-stringify a FormData here.
   *
   * @param {string} endpoint
   * @param {FormData} formData
   * @param {object} [options]
   * @returns {Promise<object>}
   */
  postForm(endpoint, formData, options = {}) {
    return request(endpoint, { ...options, method: 'POST', body: formData });
  },

  // Helper endpoints
  getHealth() {
    return this.get('/health');
  },

  getReadiness() {
    return this.get('/ready');
  },
};
