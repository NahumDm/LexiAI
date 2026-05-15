/**
 * Authentication Context & Provider
 *
 * Manages global auth state, user info, and login/logout flows.
 *
 * Production-grade guarantees:
 *  - `user` / guest flags are hydrated synchronously from storage on first
 *    render so the UI can show stable data, but `isLoading` stays true until
 *    the one-time `initAuth` effect finishes (token profile check or fast no-op).
 *    That prevents refresh races where route guards redirect before validation.
 *  - `initAuth` runs EXACTLY ONCE per AuthProvider mount — not on every
 *    navigation.
 *  - The 401-redirect handler uses refs (not closures) for `navigate` /
 *    `location`, so it always sees the LATEST route without re-binding the
 *    handler on every render.
 *  - Token storage lives in `localStorage` (via apiClient), so sessions
 *    survive reloads and new tabs.
 *
 * ROLE / ROUTE SEPARATION
 * ────────────────────────────────────────────────────────────────
 * User JWT (`lexiai.user.*`) and admin JWT (`lexiai.admin.*`) are stored
 * separately. A normal user session must not unlock `/admin/*`; only
 * `isAdminAuthenticated` (admin storage + staff flags) does.
 */

'use client';

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  ReactNode,
} from 'react';
import { AuthAPI, type User } from '@/lib/api/auth';
import { apiClient, formatApiErrorMessage, type AuthScope } from '@/lib/api/client';
import { useLocation, useNavigate } from 'react-router-dom';

const GUEST_QUERY_LIMIT = 3;
const GUEST_FLAG_KEY = 'lexiai.is_guest';
const GUEST_REMAINING_KEY = 'lexiai.guest_queries_remaining';

type RegisterInput =
  | {
      email: string;
      password: string;
      first_name?: string;
      last_name?: string;
    }
  | [name: string, email: string, password: string];

export interface AuthContextType {
  /** Core surface: `user`, `isAuthenticated`, `isAdmin`, `login`, `logout` (+ extras below). */
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isGuest: boolean;
  /** True when a valid admin-scoped JWT session exists (staff/superuser). */
  isAdminAuthenticated: boolean;
  /** Admin profile from `lexiai.admin.*` storage (null if not admin-signed-in). */
  adminUser: User | null;
  /** @deprecated Use `isAdminAuthenticated` — kept for existing imports. */
  isAdmin: boolean;
  /** @deprecated Alias of `isAdminAuthenticated`. */
  isAdminUser: boolean;
  refreshAdminUser: () => Promise<void>;
  adminLogout: () => Promise<void>;
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

// Storage helpers. We can't import the keys directly because client.ts owns
// the access/refresh token namespace; guest flags are AuthContext-owned.
const safeStorage = (): Storage | null => {
  try {
    return window.localStorage;
  } catch {
    try { return window.sessionStorage; } catch { return null; }
  }
};

const readGuestFlag = (): boolean => safeStorage()?.getItem(GUEST_FLAG_KEY) === 'true';
const readGuestRemaining = (): number => {
  const raw = safeStorage()?.getItem(GUEST_REMAINING_KEY);
  if (!raw) return GUEST_QUERY_LIMIT;
  const parsed = parseInt(raw, 10);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : GUEST_QUERY_LIMIT;
};

// Synchronous initial state — runs once, during useState initialization,
// before any effect or render commits. This is what prevents the
// "logged-in user sees login screen on reload" flicker.
const hydrateInitialUser = (): User | null => apiClient.getStoredUser<User>('user');
const hydrateInitialAdmin = (): User | null => apiClient.getStoredUser<User>('admin');

const isStaffUser = (u: User | null): boolean =>
  !!u && !!(u.is_staff || u.is_superuser);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => hydrateInitialUser());
  const [adminUser, setAdminUser] = useState<User | null>(() => hydrateInitialAdmin());
  const [isGuest, setIsGuest] = useState<boolean>(() => readGuestFlag());
  const [guestQueriesRemaining, setGuestQueriesRemaining] = useState<number>(() =>
    readGuestRemaining()
  );

  // Stay true until initAuth completes so gates/middleware don't mis-route on reload.
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const location = useLocation();

  // Refs let the 401 handler always read the LATEST route without us having to
  // re-bind the handler on every navigation (the original bug).
  const navigateRef = useRef(navigate);
  const locationRef = useRef(location);
  useEffect(() => { navigateRef.current = navigate; }, [navigate]);
  useEffect(() => { locationRef.current = location; }, [location]);

  // --- One-time init: validate stored token via /auth/profile/ ------------
  useEffect(() => {
    let cancelled = false;

    const initSession = async (scope: AuthScope, apply: (u: User | null) => void) => {
      if (!apiClient.hasToken(scope)) {
        if (apiClient.getStoredUser(scope) !== null) apiClient.clearStoredUser(scope);
        if (!cancelled) apply(null);
        return;
      }
      const response = await AuthAPI.getCurrentUser(scope);
      if (cancelled) return;
      if (response.data) {
        if (scope === 'admin' && !isStaffUser(response.data)) {
          apiClient.logout(scope);
          apply(null);
          return;
        }
        apply(response.data);
        apiClient.setStoredUser(response.data, scope);
      } else if (response.status === 401) {
        apply(null);
        apiClient.clearStoredUser(scope);
        apiClient.logout(scope);
      }
    };

    const initAuth = async () => {
      try {
        await Promise.all([
          initSession('user', setUser),
          initSession('admin', setAdminUser),
        ]);
      } catch (err) {
        console.error('[auth] init error:', err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    initAuth();
    return () => {
      cancelled = true;
    };
    // Intentionally empty deps: this MUST run only once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Stable 401 handler --------------------------------------------------
  useEffect(() => {
    apiClient.setUnauthorizedHandler((scope) => {
      const path = locationRef.current?.pathname ?? '/';

      if (scope === 'admin') {
        setAdminUser(null);
        apiClient.logout('admin');
        const onAdminAuthPage = path === '/admin/login' || path.startsWith('/admin/login/');
        if (!onAdminAuthPage && path.startsWith('/admin')) {
          navigateRef.current('/admin/login', { replace: true, state: { from: path } });
        }
        return;
      }

      setUser(null);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      try {
        safeStorage()?.removeItem(GUEST_FLAG_KEY);
        safeStorage()?.removeItem(GUEST_REMAINING_KEY);
      } catch { /* ignore */ }
      apiClient.logout('user');

      const isUserAuthPage =
        path === '/login' ||
        path === '/register' ||
        path === '/' ||
        path === '/admin/login';
      if (!isUserAuthPage && !path.startsWith('/admin')) {
        navigateRef.current('/login', { replace: true, state: { from: path } });
      }
    });

    return () => { apiClient.clearUnauthorizedHandler(); };
  }, []);

  // --- Login --------------------------------------------------------------
  const handleLogin = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await AuthAPI.login({ email, password });

      // AuthAPI.login validates response shape internally; if access is
      // missing or status is non-2xx, `response.error` is populated.
      if (!response.data?.access || !response.data?.user) {
        const message = response.error || 'Login failed. Please try again.';
        setError(message);
        throw new Error(message);
      }

      const userData = response.data.user;

      // Staff/superusers MUST use /admin/login (admin sign-in surface).
      // Reverse the just-completed authentication (blacklist + token wipe)
      // BEFORE we touch React state so the user never sees a flash of the
      // user app and the leakage guard never has to clean up after us.
      const isStaffOrSuper = !!(userData.is_staff || userData.is_superuser);
      if (isStaffOrSuper) {
        try {
          await AuthAPI.logout('user');
        } catch {
          /* best-effort blacklist — local tokens are cleared below */
        }
        apiClient.logout('user');
        apiClient.clearStoredUser('user');
        const message =
          'Admin accounts must sign in at /admin/login. This login form is for regular users only.';
        setError(message);
        throw new Error(message);
      }

      setUser(userData);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      try {
        safeStorage()?.removeItem(GUEST_FLAG_KEY);
        safeStorage()?.removeItem(GUEST_REMAINING_KEY);
      } catch { /* ignore */ }
      apiClient.setStoredUser(userData, 'user');

      navigate('/chat', { replace: true });
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  // --- Register -----------------------------------------------------------
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

        // `username` is unique in Django; local-part of email alone collides (e.g. alice@a.com vs alice@b.com).
        const username = email.slice(0, 150);

        const fullName = [firstName, lastName].filter(Boolean).join(' ').trim();

        const response = await AuthAPI.registerAndLogin({
          email,
          username,
          password,
          password_confirm: password,
          full_name: fullName || undefined,
        });

        if (!response.data?.access || !response.data?.user) {
          const message =
            (typeof response.error === 'string' && response.error.trim()) ||
            formatApiErrorMessage(response.data) ||
            'Registration failed.';
          setError(message);
          throw new Error(message);
        }

        const userData = response.data.user;
        setUser(userData);
        setIsGuest(false);
        setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
        try {
          safeStorage()?.removeItem(GUEST_FLAG_KEY);
          safeStorage()?.removeItem(GUEST_REMAINING_KEY);
        } catch { /* ignore */ }
        apiClient.setStoredUser(userData, 'user');

        navigate('/chat', { replace: true });
      } finally {
        setIsLoading(false);
      }
    },
    [navigate]
  );

  // --- Logout (user app only; does not clear admin session) ---------------
  const handleLogout = useCallback(async () => {
    setIsLoading(true);
    try {
      await AuthAPI.logout('user');
    } catch (err) {
      console.error('[auth] logout error:', err);
    } finally {
      setUser(null);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      try {
        safeStorage()?.removeItem(GUEST_FLAG_KEY);
        safeStorage()?.removeItem(GUEST_REMAINING_KEY);
      } catch { /* ignore */ }
      apiClient.logout('user');
      setIsLoading(false);
      window.location.replace('/');
    }
  }, []);

  const handleAdminLogout = useCallback(async () => {
    setIsLoading(true);
    try {
      await AuthAPI.logout('admin');
    } catch (err) {
      console.error('[auth] admin logout error:', err);
    } finally {
      setAdminUser(null);
      apiClient.logout('admin');
      setIsLoading(false);
      window.location.replace('/admin/login');
    }
  }, []);

  const handleRefreshUser = useCallback(async () => {
    try {
      const response = await AuthAPI.getCurrentUser('user');
      if (response.data) {
        setUser(response.data);
        apiClient.setStoredUser(response.data, 'user');
      }
    } catch (err) {
      console.error('[auth] refresh user failed:', err);
    }
  }, []);

  const handleRefreshAdminUser = useCallback(async () => {
    try {
      const response = await AuthAPI.getCurrentUser('admin');
      if (response.data && isStaffUser(response.data)) {
        setAdminUser(response.data);
        apiClient.setStoredUser(response.data, 'admin');
      } else if (response.data) {
        await AuthAPI.logout('admin');
        setAdminUser(null);
        apiClient.logout('admin');
      }
    } catch (err) {
      console.error('[auth] refresh admin failed:', err);
    }
  }, []);

  // --- Guest session ------------------------------------------------------
  const handleContinueAsGuest = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await AuthAPI.guestSession();
      if (!response.data?.access || !response.data?.user) {
        const message = response.error || 'Could not start guest session.';
        setError(message);
        throw new Error(message);
      }

      const userData = response.data.user;
      setUser(userData);
      setIsGuest(true);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);

      apiClient.setStoredUser(userData, 'user');
      try {
        safeStorage()?.setItem(GUEST_FLAG_KEY, 'true');
        safeStorage()?.setItem(GUEST_REMAINING_KEY, String(GUEST_QUERY_LIMIT));
      } catch { /* ignore */ }

      navigate('/chat', { replace: true });
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  const handleConsumeGuestQuery = useCallback(() => {
    if (!isGuest) return;
    setGuestQueriesRemaining(prev => {
      const next = Math.max(0, prev - 1);
      try { safeStorage()?.setItem(GUEST_REMAINING_KEY, String(next)); } catch { /* ignore */ }
      return next;
    });
  }, [isGuest]);

  const isAdminAuthenticated = isStaffUser(adminUser);

  const value: AuthContextType = {
    user,
    adminUser,
    isLoading,
    // Preserve original semantic: guests carry a JWT for API calls but are
    // NOT "authenticated" in the UI sense — they cannot access protected
    // routes that omit `allowGuest`. `UserRoute` / `ProtectedRoute` handle this:
    //   if (!isAuthenticated && !(allowGuest && isGuest)) redirect
    isAuthenticated: !!user && !isGuest,
    isGuest,
    isAdminAuthenticated,
    isAdmin: isAdminAuthenticated,
    isAdminUser: isAdminAuthenticated,
    guestQueriesRemaining,
    error,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
    adminLogout: handleAdminLogout,
    refreshUser: handleRefreshUser,
    refreshAdminUser: handleRefreshAdminUser,
    continueAsGuest: handleContinueAsGuest,
    consumeGuestQuery: handleConsumeGuestQuery,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to use auth context. Must be used inside AuthProvider.
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
