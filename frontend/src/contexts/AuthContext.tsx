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
import { useRouter } from 'next/navigation';

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string, password2: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  // Load user from sessionStorage on mount (SSR-safe)
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // Try to get stored user
        const storedUser = sessionStorage.getItem('user');
        if (storedUser) {
          setUser(JSON.parse(storedUser));
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

    // Set up global error handler for 401 responses
    apiClient.setUnauthorizedHandler(() => {
      setUser(null);
      sessionStorage.removeItem('user');
      apiClient.logout();
      router.push('/login');
    });
  }, [router]);

  const handleLogin = useCallback(async (username: string, password: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await AuthAPI.login({ username, password });

      if (!response.data) {
        throw new Error(response.error || 'Login failed');
      }

      const userData = response.data.user;
      setUser(userData);
      sessionStorage.setItem('user', JSON.stringify(userData));

      router.push('/chat');
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Login failed';
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  const handleRegister = useCallback(
    async (email: string, username: string, password: string, password2: string) => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await AuthAPI.register({
          email,
          username,
          password,
          password2,
        });

        if (!response.data) {
          throw new Error(response.error || 'Registration failed');
        }

        const userData = response.data.user;
        setUser(userData);
        sessionStorage.setItem('user', JSON.stringify(userData));

        router.push('/chat');
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Registration failed';
        setError(errorMsg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [router]
  );

  const handleLogout = useCallback(async () => {
    setIsLoading(true);

    try {
      await AuthAPI.logout();
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      setUser(null);
      sessionStorage.removeItem('user');
      setIsLoading(false);
      router.push('/');
    }
  }, [router]);

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

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    isAdmin: user?.role === 'admin',
    error,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
    refreshUser: handleRefreshUser,
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
