'use client';

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { getMe, logout as logoutFn } from '@/lib/auth';

/**
 * AuthContext — global auth state for the app.
 *
 * Wrap the app in <AuthProvider> (e.g. in layout.tsx) to make auth state
 * available everywhere via useAuth().
 *
 * Context shape:
 *   user     — the authenticated user object, or null if logged out / loading
 *   loading  — true only during the initial auth check, not on subsequent refreshes
 *   refresh  — re-fetches auth state (useful after login); silent after first mount
 *   logout   — calls the logout endpoint and clears user state
 *
 * Throws if useAuth() is called outside of AuthProvider.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const initialised = useRef(false);

  const refresh = useCallback(() => {
    if (!initialised.current) setLoading(true);
    return getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => {
        setLoading(false);
        initialised.current = true;
      });
  }, []);

  const logout = useCallback(async () => {
    await logoutFn();
    setUser(null);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}