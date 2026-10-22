/**
 * Tests for the user-management service.
 *
 * The backend takes its parameters in the query string rather than in a JSON
 * body, which is easy to get wrong and would silently send nothing. These
 * tests assert the shape of each request.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { userService } from './userService';

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

describe('userService', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('lists the organization users', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: [{ id: 'user-1' }] }));

    const users = await userService.listUsers();

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/users/');
    expect(users).toEqual([{ id: 'user-1' }]);
  });

  it('creates a user with the parameters the backend expects', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-9' } }, 201));

    await userService.createUser({
      email: 'new@example.com',
      fullName: 'New Person',
      role: 'manager',
      managerId: 'user-1',
    });

    const [url, options] = fetchMock.mock.calls[0];
    const target = String(url);
    expect(target).toContain('/users/?');
    expect(target).toContain('email=new%40example.com');
    expect(target).toContain('full_name=New+Person');
    expect(target).toContain('role=manager');
    expect(target).toContain('manager_id=user-1');
    expect(options.method).toBe('POST');
  });

  it('omits an absent manager rather than sending an empty one', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-9' } }, 201));

    await userService.createUser({ email: 'new@example.com', fullName: 'New Person' });

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).not.toContain('manager_id');
  });

  it('changes a role', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-2', role: 'manager' } }));

    await userService.changeUserRole('user-2', 'manager');

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/users/user-2?');
    expect(String(url)).toContain('new_role=manager');
    expect(options.method).toBe('PATCH');
  });

  it('activates a user', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-2', is_active: true } }));

    await userService.activateUser('user-2');

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/users/user-2/activate');
    expect(options.method).toBe('POST');
  });

  it('deactivates a user', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-2', is_active: false } }));

    await userService.deactivateUser('user-2');

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/users/user-2/deactivate');
    expect(options.method).toBe('POST');
  });

  it('assigns a manager', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-2' } }));

    await userService.setUserManager('user-2', 'user-1');

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/users/user-2/manager?');
    expect(String(url)).toContain('manager_id=user-1');
    expect(options.method).toBe('PATCH');
  });

  it('clears a manager', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: 'user-2' } }));

    await userService.setUserManager('user-2', null);

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/users/user-2/manager');
    expect(String(url)).not.toContain('manager_id');
  });
});
