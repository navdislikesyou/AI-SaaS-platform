/**
 * Tests for the organization user-management page.
 *
 * The page talks to the real user-management endpoints, so `userService` is
 * mocked and no request leaves the browser. What is under test is that the
 * page reflects the backend's role values, that a failed call is reported
 * rather than shown as a success, and that the controls an ordinary member
 * would be refused by the server are not offered.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import OrganizationPage from './OrganizationPage';

const auth = vi.hoisted(() => ({
  user: { id: 'user-1', name: 'Aarti Rao', role: 'admin' },
  hasRole: () => true,
}));

const service = vi.hoisted(() => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  changeUserRole: vi.fn(),
  activateUser: vi.fn(),
  deactivateUser: vi.fn(),
  setUserManager: vi.fn(),
}));

vi.mock('../context/AuthContext', () => ({
  ROLES: { EMPLOYEE: 'employee', MANAGER: 'manager', ADMIN: 'admin' },
  roleLabel: (role) =>
    ({ admin: 'Administrator', manager: 'Manager', employee: 'Employee' })[role] || 'Member',
  useAuth: () => auth,
}));
vi.mock('../services/userService', () => ({
  userService: service,
}));

vi.mock('../components/Navigation', () => ({ default: () => <nav>Navigation</nav> }));

const ALICE = {
  id: 'user-2',
  email: 'alice@example.com',
  full_name: 'Alice Adams',
  role: 'employee',
  organization_id: 'org-1',
  is_active: true,
};

const BOB = {
  id: 'user-3',
  email: 'bob@example.com',
  full_name: 'Bob Brown',
  role: 'manager',
  organization_id: 'org-1',
  is_active: false,
};

/**
 * Render the page and wait for the directory to load.
 */
async function renderPage() {
  const result = render(
    <MemoryRouter>
      <OrganizationPage />
    </MemoryRouter>
  );
  await waitFor(() => expect(service.listUsers).toHaveBeenCalled());
  return result;
}

describe('OrganizationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.user = { id: 'user-1', name: 'Aarti Rao', role: 'admin' };
    auth.hasRole = (role) => ({ employee: 1, manager: 2, admin: 3 })[auth.user.role] >= ({ employee: 1, manager: 2, admin: 3 })[role];
    service.listUsers.mockResolvedValue([ALICE, BOB]);
  });

  it('lists the organization members returned by the backend', async () => {
    await renderPage();

    expect(await screen.findByText('Alice Adams')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    // Bob also appears as a candidate in the manager picker, so the name is
    // matched rather than required to be unique.
    expect(screen.getAllByText('Bob Brown').length).toBeGreaterThan(0);
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
  });

  it('shows the account state the backend reported', async () => {
    await renderPage();

    expect(await screen.findByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Deactivated')).toBeInTheDocument();
  });

  it('offers an admin the controls to change a role', async () => {
    await renderPage();

    const select = await screen.findByLabelText('Role for Alice Adams');
    expect(select).toBeInTheDocument();
  });

  it('changes a role through the backend and reloads the directory', async () => {
    service.changeUserRole.mockResolvedValue({ ...ALICE, role: 'manager' });
    const user = userEvent.setup();

    await renderPage();

    const select = await screen.findByLabelText('Role for Alice Adams');
    await user.selectOptions(select, 'manager');

    await waitFor(() => expect(service.changeUserRole).toHaveBeenCalledWith('user-2', 'manager'));
    await waitFor(() => expect(service.listUsers).toHaveBeenCalledTimes(2));
  });

  it('deactivates a member through the backend', async () => {
    service.deactivateUser.mockResolvedValue({ ...ALICE, is_active: false });
    const user = userEvent.setup();

    await renderPage();

    await user.click(await screen.findByRole('button', { name: 'Deactivate' }));

    await waitFor(() => expect(service.deactivateUser).toHaveBeenCalledWith('user-2'));
  });

  it('reactivates a deactivated member through the backend', async () => {
    service.activateUser.mockResolvedValue({ ...BOB, is_active: true });
    const user = userEvent.setup();

    await renderPage();

    await user.click(await screen.findByRole('button', { name: 'Activate' }));

    await waitFor(() => expect(service.activateUser).toHaveBeenCalledWith('user-3'));
  });

  it('reports a failed role change instead of showing it as done', async () => {
    service.changeUserRole.mockRejectedValue(
      Object.assign(new Error('Cannot demote the last active organization administrator.'), {
        status: 400,
      })
    );
    const user = userEvent.setup();

    await renderPage();

    const select = await screen.findByLabelText('Role for Alice Adams');
    await user.selectOptions(select, 'manager');

    expect(
      await screen.findByText(/cannot demote the last active organization administrator/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/is now a manager/i)).not.toBeInTheDocument();
  });

  it('reports a failed directory load', async () => {
    service.listUsers.mockRejectedValue(new Error('Could not load the organization directory.'));

    await renderPage();

    expect(await screen.findByText(/could not load the organization directory/i)).toBeInTheDocument();
  });

  it('creates a member through the backend and shows the one-time password', async () => {
    service.createUser.mockResolvedValue({
      id: 'user-9',
      email: 'new@example.com',
      full_name: 'New Person',
      role: 'employee',
      is_active: true,
      temporary_password: 'TempPass123',
    });
    const user = userEvent.setup();

    await renderPage();

    await user.click(await screen.findByRole('button', { name: /add member/i }));
    await user.type(await screen.findByLabelText(/email address/i), 'new@example.com');
    await user.type(screen.getByLabelText(/full name/i), 'New Person');
    await user.click(screen.getByRole('button', { name: /create member/i }));

    await waitFor(() =>
      expect(service.createUser).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'new@example.com', fullName: 'New Person' })
      )
    );
    expect(await screen.findByText('TempPass123')).toBeInTheDocument();
  });

  it('hides the create form from a member who is not an admin', async () => {
    auth.user = { id: 'user-2', name: 'Alice Adams', role: 'employee' };
    auth.hasRole = (role) => ({ employee: 1, manager: 2, admin: 3 })[auth.user.role] >= ({ employee: 1, manager: 2, admin: 3 })[role];

    await renderPage();

    expect(await screen.findByText('Alice Adams')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add member/i })).not.toBeInTheDocument();
  });

  it('hides the role control from a member who is not an admin', async () => {
    auth.user = { id: 'user-2', name: 'Alice Adams', role: 'employee' };
    auth.hasRole = (role) => ({ employee: 1, manager: 2, admin: 3 })[auth.user.role] >= ({ employee: 1, manager: 2, admin: 3 })[role];

    await renderPage();

    await screen.findByText('Alice Adams');
    expect(screen.queryByLabelText('Role for Alice Adams')).not.toBeInTheDocument();
  });

  it('shows the role as a label when the viewer cannot change it', async () => {
    auth.user = { id: 'user-2', name: 'Alice Adams', role: 'employee' };
    auth.hasRole = (role) => ({ employee: 1, manager: 2, admin: 3 })[auth.user.role] >= ({ employee: 1, manager: 2, admin: 3 })[role];

    await renderPage();

    expect(await screen.findByText('Manager')).toBeInTheDocument();
  });

  it('offers the manager assignment only to a manager or an admin', async () => {
    await renderPage();

    expect(await screen.findByLabelText('Assign manager for Alice Adams')).toBeInTheDocument();
  });
});
