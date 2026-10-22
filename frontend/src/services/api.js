/**
 * Centralized API client for communicating with the backend FastAPI service.
 * Handles base URL configuration, request headers, JSON serialization,
 * X-Request-ID correlation, structured error responses, and the access-token
 * lifecycle.
 *
 * ## Token model
 *
 * The backend issues two things. A short-lived access JWT comes back in the
 * response body of `/auth/login` and `/auth/refresh`; a long-lived refresh
 * token is set as an HttpOnly cookie that JavaScript cannot read.
 *
 * The access token is held in a module-scoped variable and nowhere else. It is
 * deliberately not written to `localStorage` or `sessionStorage`: a token in
 * web storage survives an XSS injection and a shared machine, which is exactly
 * what a short-lived credential must not do. A page reload therefore starts
 * unauthenticated and re-establishes the session from the refresh cookie.
 */

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

/**
 * Endpoints that must never trigger the refresh flow.
 *
 * `/auth/login` failing means the credentials are wrong, `/auth/refresh`
 * failing is the refresh itself, `/auth/logout` is called while tearing a
 * session down, and the health probes are public. Retrying any of them would
 * either loop or turn an ordinary failure into a storm of requests.
 */
const NO_REFRESH_ENDPOINTS = ['/auth/login', '/auth/refresh', '/auth/logout', '/health', '/ready'];

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

/** The current access token. In memory only; never persisted. */
let accessToken = null;

/** Listeners notified when the session can no longer be renewed. */
const sessionLostListeners = new Set();

/** The in-flight refresh, so concurrent 401s share one request. */
let refreshPromise = null;

/**
 * Store the access token used for subsequent requests.
 *
 * @param {string|null} token The access token, or null to clear it.
 */
export function setAccessToken(token) {
  accessToken = token || null;
}

/**
 * Return the current access token.
 *
 * @returns {string|null} The token, or null when there is no session.
 */
export function getAccessToken() {
  return accessToken;
}

/**
 * Forget the access token.
 */
export function clearAccessToken() {
  accessToken = null;
}

/**
 * Subscribe to notifications that the session can no longer be renewed.
 *
 * The context uses this to drop the user and show the login screen rather
 * than leaving a half-authenticated UI on screen.
 *
 * @param {Function} listener Called with the reason the session was lost.
 * @returns {Function} A function that removes the listener.
 */
export function onSessionLost(listener) {
  sessionLostListeners.add(listener);
  return () => sessionLostListeners.delete(listener);
}

function notifySessionLost(reason) {
  for (const listener of [...sessionLostListeners]) {
    try {
      listener(reason);
    } catch {
      // A broken listener must not stop the others from being told.
    }
  }
}

/**
 * Return whether an endpoint is excluded from the refresh flow.
 *
 * @param {string} endpoint The endpoint path.
 * @returns {boolean} True when the endpoint must not trigger a refresh.
 */
function isRefreshExempt(endpoint) {
  const path = endpoint.split('?')[0];
  return NO_REFRESH_ENDPOINTS.some((exempt) => path === exempt || path.endsWith(exempt));
}

/**
 * Exchange the refresh cookie for a new access token.
 *
 * The refresh token is an HttpOnly cookie, so this is a bare request with
 * credentials and no bearer token. A failure here means the session is gone:
 * the cookie expired, was revoked, or the account was deactivated.
 *
 * @returns {Promise<string|null>} The new access token, or null on failure.
 */
async function requestRefreshToken() {
  try {
    const response = await fetch(buildUrl('/auth/refresh'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    const token = data?.access_token || null;

    if (token) {
      setAccessToken(token);
    }

    return token;
  } catch {
    // A network failure is not proof that the session ended, but it is proof
    // that the token could not be renewed, so the caller has to treat the
    // session as unusable rather than assume it is still good.
    return null;
  }
}

/**
 * Refresh the access token, collapsing concurrent calls into one request.
 *
 * Several requests can fail with a 401 at the same time. Each of them would
 * otherwise call `/auth/refresh`, and each rotation invalidates the cookie the
 * others are using, so only the first would succeed. This shares one promise
 * between all of them.
 *
 * @returns {Promise<string|null>} The new access token, or null on failure.
 */
export function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = requestRefreshToken().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/**
 * Build the absolute URL for an endpoint.
 *
 * @param {string} endpoint The endpoint path.
 * @returns {string} The absolute URL.
 */
function buildUrl(endpoint) {
  if (endpoint.startsWith('http')) {
    return endpoint;
  }
  return `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
}

async function request(endpoint, options = {}) {
  const url = buildUrl(endpoint);

  // A binary request reads its body as a Blob instead of JSON. Everything else
  // is shared with a JSON request: the bearer token, the refresh-and-retry, and
  // the structured error. The distinction exists because an `<img src>` cannot
  // carry an Authorization header, so a protected image has to be fetched
  // through this client and rendered from an object URL.
  const { responseType = 'json', ...fetchOptions } = options;
  const wantsBlob = responseType === 'blob';

  // FormData must not carry an explicit Content-Type: the browser has to set
  // it itself so the multipart boundary matches the body it is sending. Setting
  // it to application/json here is the classic cause of "multipart/form-data
  // parsing failed" on the server.
  const isFormData =
    typeof FormData !== 'undefined' && fetchOptions.body instanceof FormData;

  const headers = {
    'Accept': wantsBlob ? '*/*' : 'application/json',
    ...(fetchOptions.body && !isFormData ? { 'Content-Type': 'application/json' } : {}),
    ...fetchOptions.headers,
  };

  // The bearer token is attached only when there is one. The refresh cookie
  // travels with every request, which is what lets the server set a new one
  // during a refresh.
  if (accessToken && !fetchOptions.skipAuth) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  const send = () =>
    fetch(url, {
      ...fetchOptions,
      headers,
      credentials: fetchOptions.credentials || 'include',
    });

  let response;
  let data;

  try {
    response = await send();
  } catch (error) {
    // Network errors or fetch failures. This is never an authentication
    // success, so the caller has to treat it as "unknown" rather than "in".
    throw new ApiError(
      error.message || 'Network request failed. Is the backend server running?',
      0,
      'NETWORK_ERROR',
      null,
      null
    );
  }

  const requestId = response.headers.get('X-Request-ID');
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');

  // A successful binary response is read as a Blob. A failed one is still JSON,
  // so the message the backend sent survives and the caller learns why.
  if (wantsBlob && response.ok) {
    data = await response.blob();
  } else {
    data = isJson ? await response.json() : null;
  }

  // A 401 on a normal endpoint means the access token expired. Renew it once
  // and replay the request. The replay is guarded by `didRetry` so a request
  // that keeps failing cannot loop.
  if (response.status === 401 && !options.didRetry && !isRefreshExempt(endpoint)) {
    const renewed = await refreshAccessToken();

    if (renewed) {
      return request(endpoint, { ...options, didRetry: true });
    }

    clearAccessToken();
    notifySessionLost('refresh_failed');
  }

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

  patch(endpoint, data, options = {}) {
    return request(endpoint, {
      ...options,
      method: 'PATCH',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  },

  delete(endpoint, options = {}) {
    return request(endpoint, { ...options, method: 'DELETE' });
  },

  /**
   * GET a binary resource through the authenticated client.
   *
   * The bearer token lives in this module and is attached here. A plain
   * `<img src>` request cannot carry it, which is why a protected image has to
   * be fetched rather than pointed at. The body is read as a Blob so the
   * caller can render it from an object URL.
   *
   * @param {string} endpoint
   * @param {object} [options]
   * @returns {Promise<Blob>}
   */
  getBlob(endpoint, options = {}) {
    return request(endpoint, { ...options, method: 'GET', responseType: 'blob' });
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

  /**
   * POST with the parameters in the query string rather than a JSON body.
   *
   * The backend's auth and user-management endpoints declare their inputs as
   * query parameters, so this is the shape they accept.
   *
   * @param {string} endpoint
   * @param {object} [params]
   * @param {object} [options]
   * @returns {Promise<object>}
   */
  postWithParams(endpoint, params = {}, options = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        query.append(key, String(value));
      }
    }
    const suffix = query.toString();
    return request(suffix ? `${endpoint}?${suffix}` : endpoint, {
      ...options,
      method: 'POST',
    });
  },

  /**
   * PATCH with the parameters in the query string rather than a JSON body.
   *
   * @param {string} endpoint
   * @param {object} [params]
   * @param {object} [options]
   * @returns {Promise<object>}
   */
  patchWithParams(endpoint, params = {}, options = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        query.append(key, String(value));
      }
    }
    const suffix = query.toString();
    return request(suffix ? `${endpoint}?${suffix}` : endpoint, {
      ...options,
      method: 'PATCH',
    });
  },

  // Helper endpoints
  getHealth() {
    return this.get('/health');
  },

  getReadiness() {
    return this.get('/ready');
  },
};
