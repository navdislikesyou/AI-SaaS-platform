import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authService } from '../services/authService';
import { clearAccessToken, onSessionLost } from '../services/api';
import { AUTH_STATUS, ROLE_RANK, ROLES } from './authRoles';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState(AUTH_STATUS.LOADING);
  const [isAuthorizing, setIsAuthorizing] = useState(false);

  // Rebuild the session on startup. The access token is in memory only, so a
  // page load has to re-establish it from the refresh cookie before the
  // application can decide whether the user is signed in.
  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      const current = await authService.hydrateSession();

      if (cancelled) {
        return;
      }

      if (current) {
        setUser(current);
        setStatus(AUTH_STATUS.AUTHENTICATED);
      } else {
        setUser(null);
        setStatus(AUTH_STATUS.UNAUTHENTICATED);
      }
    }

    hydrate();

    return () => {
      cancelled = true;
    };
  }, []);

  // The API client tells us when a session can no longer be renewed. The UI
  // has to drop the user at that moment, otherwise protected screens stay
  // on screen with a token the server will reject.
  useEffect(() => {
    return onSessionLost(() => {
      clearAccessToken();
      setUser(null);
      setStatus(AUTH_STATUS.UNAUTHENTICATED);
    });
  }, []);

  const login = useCallback(async (email, password) => {
    setIsAuthorizing(true);
    try {
      const signedIn = await authService.login(email, password);
      setUser(signedIn);
      setStatus(AUTH_STATUS.AUTHENTICATED);
      return signedIn;
    } catch (error) {
      // A failed login must leave the application unauthenticated, never
      // half-authenticated.
      clearAccessToken();
      setUser(null);
      setStatus(AUTH_STATUS.UNAUTHENTICATED);
      throw error;
    } finally {
      setIsAuthorizing(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsAuthorizing(true);
    try {
      await authService.logout();
    } finally {
      // The local session is cleared whether or not the server acknowledged
      // the logout: the user asked to sign out.
      clearAccessToken();
      setUser(null);
      setStatus(AUTH_STATUS.UNAUTHENTICATED);
      setIsAuthorizing(false);
    }
  }, []);

  /**
   * Return whether the signed-in user holds at least the given role.
   *
   * This is a UI convenience only. The backend enforces the same rules, and
   * a user who is not shown a control is still refused by the server.
   */
  const hasRole = useCallback(
    (role) => {
      if (!user?.role) {
        return false;
      }
      const current = ROLE_RANK[user.role] || 0;
      const required = ROLE_RANK[role] || 0;
      return current >= required;
    },
    [user]
  );

  const isAdmin = useCallback(() => hasRole(ROLES.ADMIN), [hasRole]);
  const isManager = useCallback(() => hasRole(ROLES.MANAGER), [hasRole]);

  const value = useMemo(
    () => ({
      user,
      status,
      isAuthenticated: status === AUTH_STATUS.AUTHENTICATED,
      isLoading: status === AUTH_STATUS.LOADING,
      isAuthorizing,
      setIsAuthorizing,
      login,
      logout,
      hasRole,
      isAdmin,
      isManager,
    }),
    [user, status, isAuthorizing, login, logout, hasRole, isAdmin, isManager]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
