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
 * User vs admin (Django `is_staff` / `is_superuser`) surfaces are kept
 * disjoint by `getNavigationRedirect` + `RouteMiddleware` (see
 * `src/lib/routeAuth.ts`). Staff accounts must use `/admin/login`, not
 * `/login` — `handleLogin` still rejects staff on the user form so tokens
 * never land in the user app from that path.
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
import { apiClient, formatApiErrorMessage } from '@/lib/api/client';
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
  /**
   * True iff the logged-in user has Django staff/superuser privileges.
   * Sourced from the backend's user payload (`is_staff || is_superuser`),
   * NOT from the custom `role` field. This is the SAME signal Django uses
   * to gate access to `/admin/`, so the SPA and Django admin agree on who
   * is "admin".
   *
   * `isAdminUser` is an alias kept for naming alignment with the
   * session-isolation spec (`isAdminUser = user?.is_staff || user?.is_superuser`).
   * Always equal to `isAdmin`.
   */
  isAdmin: boolean;
  isAdminUser: boolean;
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
const hydrateInitialUser = (): User | null => {
  return apiClient.getStoredUser<User>();
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => hydrateInitialUser());
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

    const initAuth = async () => {
      try {
        if (!apiClient.hasToken()) {
          if (apiClient.getStoredUser() !== null) apiClient.clearStoredUser();
          if (!cancelled) setUser(null);
          return;
        }

        const response = await AuthAPI.getCurrentUser();
        if (cancelled) return;

        if (response.data) {
          setUser(response.data);
          apiClient.setStoredUser(response.data);
        } else if (response.status === 401) {
          setUser(null);
          apiClient.clearStoredUser();
        }
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
    apiClient.setUnauthorizedHandler(() => {
      // Clear all auth state.
      setUser(null);
      setIsGuest(false);
      setGuestQueriesRemaining(GUEST_QUERY_LIMIT);
      try {
        safeStorage()?.removeItem(GUEST_FLAG_KEY);
        safeStorage()?.removeItem(GUEST_REMAINING_KEY);
      } catch { /* ignore */ }
      apiClient.logout();

      const path = locationRef.current?.pathname ?? '/';
      const isAuthPage =
        path === '/login' ||
        path === '/register' ||
        path === '/' ||
        path === '/admin/login' ||
        path.startsWith('/admin/login/');
      if (!isAuthPage) {
        const target = path.startsWith('/admin') ? '/admin/login' : '/login';
        navigateRef.current(target, { replace: true, state: { from: path } });
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
          await AuthAPI.logout();
        } catch {
          /* best-effort blacklist — local tokens are cleared below */
        }
        apiClient.logout();
        apiClient.clearStoredUser();
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
      apiClient.setStoredUser(userData);

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
        apiClient.setStoredUser(userData);

        navigate('/chat', { replace: true });
      } finally {
        setIsLoading(false);
      }
    },
    [navigate]
  );

  // --- Logout -------------------------------------------------------------
  const handleLogout = useCallback(async () => {
    const wasAdmin =
      !!user &&
      !isGuest &&
      !!(user.is_staff || user.is_superuser);

    setIsLoading(true);
    try {
      await AuthAPI.logout();
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
      apiClient.logout();
      setIsLoading(false);
      const next = wasAdmin ? '/admin/login' : '/';
      window.location.replace(next);
    }
  }, [user, isGuest]);

  // --- Refresh user data --------------------------------------------------
  const handleRefreshUser = useCallback(async () => {
    try {
      const response = await AuthAPI.getCurrentUser();
      if (response.data) {
        setUser(response.data);
        apiClient.setStoredUser(response.data);
      }
    } catch (err) {
      console.error('[auth] refresh user failed:', err);
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

      apiClient.setStoredUser(userData);
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

  // Drive admin UI gating off Django's canonical staff/superuser flags.
  // Guests never have these; even if a guest payload accidentally carried
  // is_staff, the explicit `!isGuest` guards against it. Computed once
  // so both `isAdmin` and the spec-aligned alias `isAdminUser` stay in
  // sync without two boolean expressions to keep aligned.
  const isAdmin = !!user && !isGuest && !!(user.is_staff || user.is_superuser);

  const value: AuthContextType = {
    user,
    isLoading,
    // Preserve original semantic: guests carry a JWT for API calls but are
    // NOT "authenticated" in the UI sense — they cannot access protected
    // routes that omit `allowGuest`. `UserRoute` / `ProtectedRoute` handle this:
    //   if (!isAuthenticated && !(allowGuest && isGuest)) redirect
    isAuthenticated: !!user && !isGuest,
    isGuest,
    isAdmin,
    isAdminUser: isAdmin,
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
 * Hook to use auth context. Must be used inside AuthProvider.
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
