/**
 * Tests for the API client's token lifecycle.
 *
 * The behaviour under test is the part that is easy to get subtly wrong: a
 * 401 must trigger exactly one refresh even when several requests fail at
 * once, a failed request must be retried at most once, the auth endpoints
 * must never trigger a refresh, and a network failure must never be reported
 * as a successful session.
 *
 * `fetch` is stubbed, so nothing leaves the browser.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  apiClient,
  clearAccessToken,
  getAccessToken,
  onSessionLost,
  setAccessToken,
} from './api';

function jsonResponse(body, status = 200, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) =>
        headers[name] || headers[name.toLowerCase()] || (name === 'content-type' ? 'application/json' : null),
    },
    json: async () => body,
  };
}

describe('api client', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    clearAccessToken();
  });

  afterEach(() => {
    clearAccessToken();
  });

  it('sends no authorization header when there is no session', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await apiClient.get('/agents');

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBeUndefined();
  });

  it('attaches the access token when there is one', async () => {
    setAccessToken('token-123');
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await apiClient.get('/agents');

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBe('Bearer token-123');
  });

  it('sends credentials so the refresh cookie travels with the request', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await apiClient.get('/agents');

    const [, options] = fetchMock.mock.calls[0];
    expect(options.credentials).toBe('include');
  });

  it('never writes the access token to web storage', async () => {
    setAccessToken('token-123');

    expect(localStorage.getItem('saas_active_user')).toBeNull();
    expect(sessionStorage.getItem('saas_active_user')).toBeNull();
    expect(getAccessToken()).toBe('token-123');
  });

  it('refreshes once and retries a failed request', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: 'fresh-token' }, 200))
      .mockResolvedValueOnce(jsonResponse({ ok: true }, 200));

    const result = await apiClient.get('/agents');

    expect(result).toEqual({ ok: true });
    expect(getAccessToken()).toBe('fresh-token');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('retries a failed request at most once', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: 'fresh-token' }, 200))
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401));

    await expect(apiClient.get('/agents')).rejects.toBeInstanceOf(ApiError);

    // One original attempt, one refresh, one retry. No second retry.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('collapses concurrent 401 responses into a single refresh request', async () => {
    let releaseRefresh;
    const refreshGate = new Promise((resolve) => {
      releaseRefresh = resolve;
    });

    const attempts = new Map();

    fetchMock.mockImplementation((url) => {
      const target = String(url);

      if (target.includes('/auth/refresh')) {
        return refreshGate.then(() => jsonResponse({ access_token: 'fresh-token' }, 200));
      }

      // The first attempt at each endpoint fails with a 401; the retry after
      // the refresh succeeds.
      const seen = attempts.get(target) || 0;
      attempts.set(target, seen + 1);

      return Promise.resolve(
        seen === 0
          ? jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401)
          : jsonResponse({ ok: true }, 200)
      );
    });

    const first = apiClient.get('/agents');
    const second = apiClient.get('/knowledge/documents');
    const third = apiClient.get('/performance/datasets');

    releaseRefresh();
    const results = await Promise.all([first, second, third]);

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(1);
  });

  it('does not refresh when the login endpoint rejects the credentials', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: 'INVALID_CREDENTIALS' } }, 401));

    await expect(apiClient.postWithParams('/auth/login', { email: 'a@b.c', password: 'x' })).rejects.toBeInstanceOf(
      ApiError
    );

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(0);
  });

  it('does not refresh when the refresh endpoint itself fails', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: 'INVALID_CREDENTIALS' } }, 401));

    await expect(apiClient.post('/auth/refresh')).rejects.toBeInstanceOf(ApiError);

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(1);
  });

  it('does not refresh for the public health probes', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401));

    await expect(apiClient.getHealth()).rejects.toBeInstanceOf(ApiError);

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(0);
  });

  it('renews an expired access token and retries with the new one', async () => {
    // An expired access token is what the backend answers with a 401. The
    // client has to renew it exactly once and replay the request with the
    // new token, not with the expired one.
    setAccessToken('expired-token');

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'HTTP_401' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: 'fresh-token' }, 200))
      .mockResolvedValueOnce(jsonResponse({ ok: true }, 200));

    const result = await apiClient.get('/agents');

    expect(result).toEqual({ ok: true });

    const [, first] = fetchMock.mock.calls[0];
    const [, retry] = fetchMock.mock.calls[2];

    expect(first.headers.Authorization).toBe('Bearer expired-token');
    expect(retry.headers.Authorization).toBe('Bearer fresh-token');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('ends the session when the refresh fails, without retrying forever', async () => {
    const listener = vi.fn();
    const unsubscribe = onSessionLost(listener);

    setAccessToken('expired-token');

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'HTTP_401' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'INVALID_CREDENTIALS' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'HTTP_401' } }, 401));

    await expect(apiClient.get('/agents')).rejects.toBeInstanceOf(ApiError);

    // One attempt and one refresh attempt. The request is not replayed,
    // because the refresh failed, and the refresh is not repeated either, so
    // the client cannot spin on a session that cannot be renewed.
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const refreshCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(1);

    // The session is gone: the token is dropped and the application is told.
    expect(getAccessToken()).toBeNull();
    expect(listener).toHaveBeenCalledWith('refresh_failed');

    unsubscribe();
  });

  it('reports a network failure as a network error rather than a response', async () => {    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    const error = await apiClient.get('/agents').catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.code).toBe('NETWORK_ERROR');
  });

  it('notifies listeners when the session can no longer be renewed', async () => {
    const listener = vi.fn();
    const unsubscribe = onSessionLost(listener);

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'UNAUTHORIZED' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'INVALID_CREDENTIALS' } }, 401));

    await apiClient.get('/agents').catch(() => {});

    expect(listener).toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();

    unsubscribe();
  });

  it('exposes the backend error code and status', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'DATASET_NOT_FOUND', message: 'gone', details: { dataset_id: 'x' } } }, 404)
    );

    const error = await apiClient.get('/performance/datasets').catch((caught) => caught);

    expect(error.status).toBe(404);
    expect(error.code).toBe('DATASET_NOT_FOUND');
    expect(error.message).toBe('gone');
    expect(error.details).toEqual({ dataset_id: 'x' });
  });
});

describe('api client binary responses', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    clearAccessToken();
  });

  afterEach(() => {
    clearAccessToken();
  });

  function blobResponse(blob, status = 200, headers = {}) {
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: {
        get: (name) =>
          headers[name] ||
          headers[name.toLowerCase()] ||
          (name === 'content-type' ? 'image/png' : null),
      },
      blob: async () => blob,
      json: async () => ({}),
    };
  }

  it('attaches the access token to a binary request', async () => {
    setAccessToken('token-123');
    fetchMock.mockResolvedValue(blobResponse(new Blob(['png'])));

    await apiClient.getBlob('/performance/jobs/job-1/artifacts/channel_profit.png');

    const [, options] = fetchMock.mock.calls[0];

    expect(options.headers.Authorization).toBe('Bearer token-123');
  });

  it('returns the body as a blob', async () => {
    const blob = new Blob(['png-bytes'], { type: 'image/png' });

    fetchMock.mockResolvedValue(blobResponse(blob));

    const result = await apiClient.getBlob('/performance/jobs/job-1/artifacts/channel_profit.png');

    expect(result).toBe(blob);
  });

  it('does not ask for JSON when a binary body is expected', async () => {
    fetchMock.mockResolvedValue(blobResponse(new Blob(['png'])));

    await apiClient.getBlob('/performance/jobs/job-1/artifacts/channel_profit.png');

    const [, options] = fetchMock.mock.calls[0];

    expect(options.headers.Accept).not.toBe('application/json');
  });

  it('reports a rejected binary request with the backend error', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'JOB_NOT_FOUND', message: 'Artifact was not found.' } },
        404,
      )
    );

    const error = await apiClient
      .getBlob('/performance/jobs/job-1/artifacts/channel_profit.png')
      .catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.code).toBe('JOB_NOT_FOUND');
    expect(error.message).toBe('Artifact was not found.');
  });
});
