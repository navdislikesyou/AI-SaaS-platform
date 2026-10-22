import React, { useCallback, useEffect, useState } from 'react';
import Navigation from '../components/Navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import { ROLES, roleLabel } from '../context/authRoles';
import { userService } from '../services/userService';

/**
 * The roles the backend accepts, in the order they are offered.
 *
 * These are the backend's own role values. The label is only for display.
 */
const ROLE_OPTIONS = [
  { value: ROLES.EMPLOYEE, label: 'Employee' },
  { value: ROLES.MANAGER, label: 'Manager' },
  { value: ROLES.ADMIN, label: 'Administrator' },
];

const CARD = {
  background: 'rgba(255,255,255,0.02)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '8px',
};

const LABEL = {
  display: 'block',
  fontSize: '0.875rem',
  color: 'rgba(255,255,255,0.7)',
  marginBottom: '8px',
};

const INPUT = {
  width: '100%',
  background: 'rgba(0,0,0,0.2)',
  border: '1px solid rgba(255,255,255,0.1)',
  padding: '12px',
  borderRadius: '6px',
  color: '#f5f4f0',
  outline: 'none',
  fontSize: '1rem',
};

export default function OrganizationPage() {
  const { user, hasRole } = useAuth();

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [newRole, setNewRole] = useState(ROLES.EMPLOYEE);
  const [managerId, setManagerId] = useState('');
  const [creating, setCreating] = useState(false);
  const [createdPassword, setCreatedPassword] = useState('');

  const applyUsers = useCallback((list) => {
    setUsers(list);
    setLoading(false);
  }, []);

  const applyFailure = useCallback((err) => {
    setError(err?.message || 'Could not load the organization directory.');
    setLoading(false);
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      applyUsers(await userService.listUsers());
    } catch (err) {
      applyFailure(err);
    }
  }, [applyUsers, applyFailure]);

  useEffect(() => {
    let cancelled = false;

    userService.listUsers().then(
      (list) => {
        if (!cancelled) {
          applyUsers(list);
        }
      },
      (err) => {
        if (!cancelled) {
          applyFailure(err);
        }
      }
    );

    return () => {
      cancelled = true;
    };
  }, [applyUsers, applyFailure]);

  const handleCreate = async (event) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setCreatedPassword('');
    setCreating(true);

    try {
      const created = await userService.createUser({
        email,
        fullName,
        role: newRole,
        managerId: managerId || undefined,
      });
      setCreatedPassword(created?.temporary_password || '');
      setNotice(`${created?.full_name || email} was added to the organization.`);
      setEmail('');
      setFullName('');
      setNewRole(ROLES.EMPLOYEE);
      setManagerId('');
      setShowCreate(false);
      await loadUsers();
    } catch (err) {
      setError(err?.message || 'Could not create the user.');
    } finally {
      setCreating(false);
    }
  };

  const changeRole = async (target, role) => {
    setError('');
    setNotice('');
    try {
      await userService.changeUserRole(target.id, role);
      setNotice(`${target.full_name} is now a ${roleLabel(role).toLowerCase()}.`);
      await loadUsers();
    } catch (err) {
      setError(err?.message || 'Could not change the role.');
    }
  };

  const setActive = async (target, active) => {
    setError('');
    setNotice('');
    try {
      if (active) {
        await userService.activateUser(target.id);
      } else {
        await userService.deactivateUser(target.id);
      }
      setNotice(`${target.full_name} was ${active ? 'activated' : 'deactivated'}.`);
      await loadUsers();
    } catch (err) {
      setError(err?.message || 'Could not change the account state.');
    }
  };

  const assignManager = async (target, nextManagerId) => {
    setError('');
    setNotice('');
    try {
      await userService.setUserManager(target.id, nextManagerId || null);
      setNotice(`${target.full_name}'s manager was updated.`);
      await loadUsers();
    } catch (err) {
      setError(err?.message || 'Could not assign the manager.');
    }
  };

  // Only an admin reaches this route, but the page still refuses to act
  // without the permission rather than relying on the route guard alone.
  const canManage = user?.role === ROLES.ADMIN;

  // The backend lets a manager or an admin assign a manager.
  const canAssignManager = hasRole(ROLES.MANAGER);

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main" style={{ overflowY: 'auto', padding: '40px 64px' }}>
        <motion.div
          className="org-content"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          style={{ maxWidth: '1200px', margin: '0 auto', width: '100%', paddingTop: '24px' }}
        >
          <div className="placeholder-label" style={{ color: 'var(--soft-lime)' }}>Organization</div>
          <h1
            className="placeholder-heading"
            style={{ fontSize: '3.5rem', marginBottom: '40px', color: '#f5f4f0', fontWeight: '800', letterSpacing: '-0.02em', textTransform: 'uppercase' }}
          >
            Team Directory
          </h1>

          {error && (
            <div
              role="alert"
              style={{ ...CARD, padding: '16px', marginBottom: '24px', color: '#ff8a65', borderColor: 'rgba(255,90,0,0.3)' }}
            >
              {error}
            </div>
          )}

          {notice && (
            <div
              role="status"
              style={{ ...CARD, padding: '16px', marginBottom: '24px', color: '#4ade80', borderColor: 'rgba(74,222,128,0.3)' }}
            >
              {notice}
            </div>
          )}

          {createdPassword && (
            <div
              role="status"
              style={{ ...CARD, padding: '16px', marginBottom: '24px' }}
            >
              <p style={{ fontSize: '0.875rem', marginBottom: '8px' }}>
                Temporary password for the new account. It is shown once and cannot be retrieved
                again.
              </p>
              <code
                style={{
                  display: 'inline-block',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.3)',
                  borderRadius: '4px',
                  color: 'var(--soft-lime)',
                  fontSize: '0.875rem',
                }}
              >
                {createdPassword}
              </code>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
            <h2 className="heading-medium" style={{ fontSize: '1.25rem' }}>
              Members
              {loading ? '' : ` (${users.length})`}
            </h2>
            {canManage && (
              <button
                onClick={() => setShowCreate((open) => !open)}
                style={{ background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '8px 16px', borderRadius: '4px', fontWeight: 600, fontSize: '0.875rem', cursor: 'pointer' }}
              >
                {showCreate ? 'Cancel' : '+ Add Member'}
              </button>
            )}
          </div>

          <AnimatePresence>
            {showCreate && (
              <motion.form
                onSubmit={handleCreate}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                style={{ ...CARD, padding: '24px', marginBottom: '24px' }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={LABEL} htmlFor="member-email">Email Address</label>
                    <input
                      id="member-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="colleague@company.com"
                      style={INPUT}
                    />
                  </div>
                  <div>
                    <label style={LABEL} htmlFor="member-name">Full Name</label>
                    <input
                      id="member-name"
                      type="text"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Jordan Park"
                      style={INPUT}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: '16px' }}>
                    <div style={{ flex: 1 }}>
                      <label style={LABEL}>Role</label>
                      <select
                        value={newRole}
                        onChange={(e) => setNewRole(e.target.value)}
                        style={INPUT}
                      >
                        {ROLE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={LABEL}>Manager</label>
                      <select
                        value={managerId}
                        onChange={(e) => setManagerId(e.target.value)}
                        style={INPUT}
                      >
                        <option value="">None</option>
                        {users
                          .filter((member) => member.role === ROLES.MANAGER || member.role === ROLES.ADMIN)
                          .map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.full_name}
                            </option>
                          ))}
                      </select>
                    </div>
                  </div>
                  <button
                    type="submit"
                    disabled={creating}
                    style={{ background: 'var(--soft-lime)', color: '#000', border: 'none', padding: '12px', borderRadius: '6px', fontWeight: 600, cursor: creating ? 'wait' : 'pointer' }}
                  >
                    {creating ? 'Creating…' : 'Create Member'}
                  </button>
                </div>
              </motion.form>
            )}
          </AnimatePresence>

          <div style={{ ...CARD, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                  <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Name & Email</th>
                  <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Role</th>
                  <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>Status</th>
                  {canManage && (
                    <th style={{ padding: '16px', fontSize: '0.875rem', fontWeight: 500, color: 'rgba(255,255,255,0.5)' }}>
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={4} style={{ padding: '24px', color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem' }}>
                      Loading the directory…
                    </td>
                  </tr>
                )}
                {!loading && users.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ padding: '24px', color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem' }}>
                      No members found in this organization.
                    </td>
                  </tr>
                )}
                {users.map((member) => (
                  <tr key={member.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '16px' }}>
                      <div style={{ fontSize: '0.875rem', color: '#f5f4f0', fontWeight: 500 }}>
                        {member.full_name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>
                        {member.email}
                      </div>
                    </td>
                    <td style={{ padding: '16px', fontSize: '0.875rem', color: '#f5f4f0' }}>
                      {canManage ? (
                        <select
                          value={member.role}
                          aria-label={`Role for ${member.full_name}`}
                          onChange={(e) => changeRole(member, e.target.value)}
                          style={{ ...INPUT, padding: '6px 8px', fontSize: '0.875rem' }}
                        >
                          {ROLE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        roleLabel(member.role)
                      )}
                    </td>
                    <td style={{ padding: '16px' }}>
                      <span
                        style={{
                          padding: '4px 8px',
                          background: member.is_active ? 'rgba(0,255,0,0.1)' : 'rgba(255,165,0,0.1)',
                          color: member.is_active ? '#4ade80' : '#ffa500',
                          borderRadius: '12px',
                          fontSize: '0.75rem',
                        }}
                      >
                        {member.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </td>
                    {canManage && (
                      <td style={{ padding: '16px' }}>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                          <button
                            onClick={() => setActive(member, !member.is_active)}
                            style={{ background: 'transparent', color: '#f5f4f0', border: '1px solid rgba(255,255,255,0.2)', padding: '6px 10px', borderRadius: '4px', fontSize: '0.75rem', cursor: 'pointer' }}
                          >
                            {member.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          {canAssignManager && (
                            <select
                              value=""
                              aria-label={`Assign manager for ${member.full_name}`}
                              onChange={(e) => assignManager(member, e.target.value)}
                              style={{ ...INPUT, padding: '6px 8px', fontSize: '0.75rem', width: 'auto' }}
                            >
                              <option value="">Set manager…</option>
                              <option value="">Clear manager</option>
                              {users
                                .filter(
                                  (candidate) =>
                                    candidate.id !== member.id &&
                                    (candidate.role === ROLES.MANAGER || candidate.role === ROLES.ADMIN)
                                )
                                .map((candidate) => (
                                  <option key={candidate.id} value={candidate.id}>
                                    {candidate.full_name}
                                  </option>
                                ))}
                            </select>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
