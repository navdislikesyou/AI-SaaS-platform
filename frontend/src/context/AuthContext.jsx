import React, { createContext, useContext, useState } from 'react';
import { authService } from '../services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isAuthorizing, setIsAuthorizing] = useState(false);

  const login = async (email, password) => {
    setIsAuthorizing(true);
    try {
      const loggedInUser = await authService.login(email, password);
      setUser(loggedInUser);
      return loggedInUser;
    } finally {
      setIsAuthorizing(false);
    }
  };

  const logout = async () => {
    await authService.logout();
    setUser(null);
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
