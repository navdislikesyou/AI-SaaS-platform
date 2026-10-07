import React, { createContext, useContext, useState } from 'react';
import { authService } from '../services/authService';

const AuthContext = createContext(null);

const getInitialUser = () => {
  try {
    const saved = localStorage.getItem('saas_active_user');
    if (saved) return JSON.parse(saved);
  } catch (e) {
    console.warn('Failed to read saved session', e);
  }
  return {
    id: 'usr_001',
    name: 'Marcus Webb',
    email: 'marcus@axiom-corp.com',
    role: 'Organization Owner',
    accessLevel: 'Global',
    organization: 'Axiom Corp',
    avatar: 'MW',
    permissions: {
      hiring: 'full',
      research: 'full',
      knowledge: 'full',
      communication: 'full',
      automation: 'full',
      insights: 'full',
      performance: 'full',
    },
  };
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getInitialUser);
  const [isAuthorizing, setIsAuthorizing] = useState(false);

  const login = async (email, password) => {
    setIsAuthorizing(true);
    try {
      const loggedInUser = await authService.login(email, password);
      setUser(loggedInUser);
      try {
        localStorage.setItem('saas_active_user', JSON.stringify(loggedInUser));
      } catch (err) {
        // ignore
      }
      return loggedInUser;
    } finally {
      setIsAuthorizing(false);
    }
  };

  const logout = async () => {
    await authService.logout();
    setUser(null);
    try {
      localStorage.removeItem('saas_active_user');
    } catch (err) {
      // ignore
    }
    setIsAuthorizing(false);
  };

  const canAccess = (module) => {
    if (!user) return false;
    return user.permissions[module] !== 'none';
  };

  const accessLevel = (module) => {
    if (!user) return 'none';
    return user.permissions[module];
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthorizing, setIsAuthorizing, canAccess, accessLevel }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
