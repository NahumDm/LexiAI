/**
 * Authentication Context & Provider
 * Manages global auth state, user info, and login/logout flows
 * Handles:
 * - Session persistence across page refreshes
 * - Global auth state
 * - Automatic redirect to login on 401
 * - User role-based access
 */

'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { AuthAPI, type User } from '@/lib/api/auth';
import { apiClient } from '@/lib/api/client';
import { useLocation, useNavigate } from 'react-router-dom';

const GUEST_QUERY_LIMIT = 3;

type RegisterInput =
  | {
      email: string;
      password: string;
      first_name?: string;
      last_name?: string;
    }
  | [name: string, email: string, password: string];

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isGuest: boolean;
  isAdmin: boolean;
  guestQueriesRemaining: number;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (...args: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  continueAsGuest: () => Promise<void>;
  consumeGuestQuery: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isGuest, setIsGuest] = useState(false);
  const [guestQueriesRemaining, setGuestQueriesRemaining] = useState(GUEST_QUERY_LIMIT);
  const navigate = useNavigate();
  const location = useLocation();

  // Load user from sessionStorage on mount (SSR-safe)
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // Try to get stored user
        const storedUser = sessionStorage.getItem('user');
        const storedGuest = sessionStorage.getItem('is_guest');
        const storedGuestRemaining = sessionStorage.getItem('guest_queries_remaining');

        if (storedGuest === 'true') {
          setIsGuest(true);
          setGuestQueriesRemaining(
            storedGuestRemaining ? Math.max(parseInt(storedGuestRemaining, 10) || 0, 0) : GUEST_QUERY_LIMIT
          );
        } else {
          setIsGuest(false);
          setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
        }

        if (storedUser) {
          try {
            setUser(JSON.parse(storedUser));
          } catch (parseError) {
            console.warn('Invalid stored user found, clearing session user:', parseError);
            sessionStorage.removeItem('user');
          }
        } else if (!apiClient.hasToken()) {
          // Keep session storage/state consistent when no user and no token.
          apiClient.logout();
        }

        // Verify token is still valid by fetching current user
        if (apiClient.hasToken()) {
          const response = await AuthAPI.getCurrentUser();
          if (response.data) {
            setUser(response.data);
            sessionStorage.setItem('user', JSON.stringify(response.data));
          } else if (response.status === 401) {
            // Token expired, clear auth
            apiClient.logout();
            setUser(null);
            sessionStorage.removeItem('user');
          }
        }
      } catch (err) {
        console.error('Auth initialization error:', err);
      } finally {
        setIsLoading(false);
      }
    };

    initializeAuth();

    const isAuthPage = location.pathname === '/login' || location.pathname === '/register';

    // Set up global error handler for 401 responses.
    apiClient.setUnauthorizedHandler(() => {
      setUser(null);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      sessionStorage.removeItem('user');
      sessionStorage.removeItem('is_guest');
      sessionStorage.removeItem('guest_queries_remaining');
      apiClient.logout();

      // Avoid redirect loops when we are already on an auth page.
      if (!isAuthPage) {
        navigate('/login', { replace: true, state: { from: location.pathname } });
      }
    });

    return () => {
      apiClient.clearUnauthorizedHandler();
    };
  }, [location.pathname, navigate]);

  const handleLogin = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await AuthAPI.login({ email, password });

      if (!response.data) {
        throw new Error(response.error || 'Login failed');
      }

      const userData = response.data.user;
      setUser(userData);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      sessionStorage.removeItem('is_guest');
      sessionStorage.removeItem('guest_queries_remaining');
      sessionStorage.setItem('user', JSON.stringify(userData));

      navigate('/chat');
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Login failed';
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  const handleRegister = useCallback(
    async (...args: RegisterInput) => {
      setIsLoading(true);
      setError(null);

      try {
        let email = '';
        let password = '';
        let firstName = '';
        let lastName = '';

        if (typeof args[0] === 'string') {
          const [name, emailArg, passwordArg] = args as [string, string, string];
          email = emailArg;
          password = passwordArg;
          const [first = '', ...rest] = name.trim().split(/\s+/);
          firstName = first;
          lastName = rest.join(' ');
        } else {
          const payload = args[0];
          email = payload.email;
          password = payload.password;
          firstName = payload.first_name || '';
          lastName = payload.last_name || '';
        }

        const username = email.split('@')[0] || email;
        const fullName = [firstName, lastName].filter(Boolean).join(' ').trim();

        const response = await AuthAPI.registerAndLogin({
          email,
          username,
          password,
          password_confirm: password,
          full_name: fullName || undefined,
        });

        if (!response.data) {
          throw new Error(response.error || 'Registration failed');
        }

        const userData = response.data.user;
        setUser(userData);
        setIsGuest(false);
        setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
        sessionStorage.removeItem('is_guest');
        sessionStorage.removeItem('guest_queries_remaining');
        sessionStorage.setItem('user', JSON.stringify(userData));

        navigate('/chat');
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Registration failed';
        setError(errorMsg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [navigate]
  );

  const handleLogout = useCallback(async () => {
    setIsLoading(true);

    try {
      await AuthAPI.logout();
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      setUser(null);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      sessionStorage.removeItem('user');
      sessionStorage.removeItem('is_guest');
      sessionStorage.removeItem('guest_queries_remaining');
      setIsLoading(false);
      navigate('/');
    }
  }, [navigate]);

  const handleRefreshUser = useCallback(async () => {
    try {
      const response = await AuthAPI.getCurrentUser();
      if (response.data) {
        setUser(response.data);
        sessionStorage.setItem('user', JSON.stringify(response.data));
      }
    } catch (err) {
      console.error('Failed to refresh user:', err);
    }
  }, []);

  const handleContinueAsGuest = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await AuthAPI.guestSession();
      if (!response.data?.user) {
        throw new Error(response.error || 'Could not start guest session');
      }

      const userData = response.data.user;
      setUser(userData);
      setIsGuest(true);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);

      sessionStorage.setItem('user', JSON.stringify(userData));
      sessionStorage.setItem('is_guest', 'true');
      sessionStorage.setItem('guest_queries_remaining', String(GUEST_QUERY_LIMIT));
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Guest session failed';
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleConsumeGuestQuery = useCallback(() => {
    if (!isGuest) return;
    setGuestQueriesRemaining(prev => {
      const next = Math.max(0, prev - 1);
      sessionStorage.setItem('guest_queries_remaining', String(next));
      return next;
    });
  }, [isGuest]);

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user && !isGuest,
    isGuest,
    isAdmin: user?.role === 'admin',
    guestQueriesRemaining,
    error,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
    refreshUser: handleRefreshUser,
    continueAsGuest: handleContinueAsGuest,
    consumeGuestQuery: handleConsumeGuestQuery,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to use auth context
 * Must be used inside AuthProvider
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
