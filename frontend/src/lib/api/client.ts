/**
 * Centralized API client with JWT authentication, token refresh, and error handling.
 *
 * Responsibilities:
 * - Persist access + refresh tokens in localStorage (survives reloads + new tabs).
 * - Inject `Authorization: Bearer <access>` on every request.
 * - On 401 from PROTECTED endpoints: attempt a single refresh, retry once, else
 *   fire the unauthorized handler (AuthContext clears state + redirects to /login).
 * - 401 from AUTH endpoints (/auth/login/, /auth/register/, /auth/refresh/,
 *   /auth/guest-session/) is bubbled up as a normal error so the UI can show
 *   "invalid credentials" without nuking auth state. This was the production bug:
 *   wrong-credentials login was being interpreted as "token expired" → forced
 *   logout + "Authentication failed. Please log in again." error.
 */

import {
  AUTH_STORAGE_KEYS,
  LEGACY_AUTH_KEYS,
  type AuthScope,
} from './authScope';

export type { AuthScope };

export interface ApiResponse<T = unknown> {
  data?: T;
  error?: string;
  detail?: string;
  status: number;
}

export interface ApiError extends Error {
  status?: number;
  response?: unknown;
}

// Legacy sessionStorage keys — migrated into user scope on first read.
const LEGACY_SESSION_KEYS = ['access_token', 'refresh_token', 'user'] as const;

// Endpoints whose 401 must NOT trigger refresh/handleAuthError. These are
// PUBLIC auth endpoints; a 401 there means "bad credentials", not "expired token".
const AUTH_ENDPOINT_PATTERNS = [
  /\/auth\/login\/?$/,
  /\/auth\/register\/?$/,
  /\/auth\/refresh\/?$/,
  /\/auth\/guest-session\/?$/,
];

const isAuthEndpoint = (endpoint: string): boolean =>
  AUTH_ENDPOINT_PATTERNS.some((pattern) => pattern.test(endpoint));

/** Flatten DRF / SimpleJWT error JSON into a single human-readable string (never "[object Object]"). */
export function formatApiErrorMessage(data: unknown): string {
  if (data == null) return '';
  if (typeof data === 'string') return data;
  if (typeof data !== 'object' || Array.isArray(data)) return '';

  const o = data as Record<string, unknown>;
  if (typeof o.detail === 'string' && o.detail.trim()) return o.detail.trim();
  if (Array.isArray(o.detail)) {
    return o.detail
      .map((d) => (typeof d === 'string' ? d : JSON.stringify(d)))
      .filter(Boolean)
      .join('; ');
  }
  if (o.detail != null && typeof o.detail === 'object') {
    const nested = formatApiErrorMessage(o.detail);
    if (nested) return nested;
  }

  const parts: string[] = [];
  for (const [key, val] of Object.entries(o)) {
    if (key === 'detail') continue;
    if (Array.isArray(val)) {
      for (const item of val) {
        parts.push(
          typeof item === 'string' ? `${key}: ${item}` : `${key}: ${JSON.stringify(item)}`
        );
      }
    } else if (val != null && typeof val === 'object') {
      parts.push(`${key}: ${JSON.stringify(val)}`);
    } else if (val !== undefined && val !== null) {
      parts.push(`${key}: ${String(val)}`);
    }
  }
  return parts.join('; ');
}

const DEBUG_AUTH = (() => {
  try {
    return import.meta.env.DEV || import.meta.env.VITE_DEBUG_AUTH === 'true';
  } catch {
    return false;
  }
})();

/** Verbose API URL logging (browser console): set VITE_DEBUG_API=true on Vercel and redeploy. */
const DEBUG_API = (() => {
  try {
    return DEBUG_AUTH || import.meta.env.VITE_DEBUG_API === 'true';
  } catch {
    return false;
  }
})();

const debugLog = (...args: unknown[]) => {
  if (DEBUG_AUTH) {
    console.debug('[auth]', ...args);
  }
};

const debugApiLog = (...args: unknown[]) => {
  if (DEBUG_API) {
    console.info('[lexiai-api]', ...args);
  }
};

const redact = (token: string | null | undefined): string =>
  token ? `${token.slice(0, 12)}…${token.slice(-6)} (len=${token.length})` : 'null';

class ApiClient {
  private baseUrl: string;
  private apiVersion: string;
  private isRefreshing = false;
  private refreshPromise: Promise<boolean> | null = null;
  private isHandlingUnauthorized = false;
  private onUnauthorized: ((scope: AuthScope) => void) | null = null;
  private hasLoggedApiBootstrap = false;

  constructor() {
    const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
    if (envBase !== undefined && envBase !== '') {
      this.baseUrl = envBase.replace(/\/$/, '');
    } else if (import.meta.env.DEV) {
      // Dev: rely on Vite proxy (see vite.config.ts) so we stay same-origin.
      this.baseUrl = '';
    } else {
      // Production browser bundle: never default to localhost (Vercel users would hit their own machine).
      this.baseUrl = '';
      if (typeof window !== 'undefined') {
        console.error(
          '[LexiAI] VITE_API_BASE_URL was not set at build time. Set it in Vercel Environment Variables to your Django API origin (e.g. https://api.yourapp.com), then redeploy the frontend.'
        );
      }
    }
    this.apiVersion = import.meta.env.VITE_API_VERSION || 'v1';

    this.migrateLegacyStorage();
  }

  // --- Storage (localStorage with sessionStorage fallback) -----------------

  private safeStorage(): Storage | null {
    try {
      // Probe localStorage availability (Safari private mode, etc.).
      const testKey = '__lexiai_probe__';
      window.localStorage.setItem(testKey, '1');
      window.localStorage.removeItem(testKey);
      return window.localStorage;
    } catch {
      try {
        return window.sessionStorage;
      } catch {
        return null;
      }
    }
  }

  private migrateLegacyStorage(): void {
    try {
      const storage = this.safeStorage();
      if (!storage) return;

      const userKeys = AUTH_STORAGE_KEYS.user;
      const pairs: [string, string][] = [
        [LEGACY_AUTH_KEYS.access, userKeys.access],
        [LEGACY_AUTH_KEYS.refresh, userKeys.refresh],
        [LEGACY_AUTH_KEYS.profile, userKeys.profile],
      ];
      for (const [legacyKey, newKey] of pairs) {
        const legacyValue = storage.getItem(legacyKey);
        if (legacyValue && !storage.getItem(newKey)) {
          storage.setItem(newKey, legacyValue);
        }
        storage.removeItem(legacyKey);
      }

      for (const legacy of LEGACY_SESSION_KEYS) {
        const newKey =
          legacy === 'access_token'
            ? userKeys.access
            : legacy === 'refresh_token'
              ? userKeys.refresh
              : userKeys.profile;
        const sessionValue = window.sessionStorage?.getItem(legacy);
        if (sessionValue && !storage.getItem(newKey)) {
          storage.setItem(newKey, sessionValue);
        }
        window.sessionStorage?.removeItem(legacy);
      }
    } catch {
      // Storage may be unavailable — ignore.
    }
  }

  private keys(scope: AuthScope) {
    return AUTH_STORAGE_KEYS[scope];
  }

  getToken(scope: AuthScope = 'user'): string | null {
    try {
      return this.safeStorage()?.getItem(this.keys(scope).access) ?? null;
    } catch {
      return null;
    }
  }

  private setToken(token: string, scope: AuthScope): void {
    try {
      this.safeStorage()?.setItem(this.keys(scope).access, token);
    } catch (e) {
      console.error(`[auth] Failed to persist ${scope} access token:`, e);
    }
  }

  getRefreshToken(scope: AuthScope = 'user'): string | null {
    try {
      return this.safeStorage()?.getItem(this.keys(scope).refresh) ?? null;
    } catch {
      return null;
    }
  }

  private setRefreshToken(token: string, scope: AuthScope): void {
    try {
      this.safeStorage()?.setItem(this.keys(scope).refresh, token);
    } catch (e) {
      console.error(`[auth] Failed to persist ${scope} refresh token:`, e);
    }
  }

  getStoredUser<T = unknown>(scope: AuthScope = 'user'): T | null {
    try {
      const raw = this.safeStorage()?.getItem(this.keys(scope).profile);
      if (!raw) return null;
      return JSON.parse(raw) as T;
    } catch {
      try {
        this.safeStorage()?.removeItem(this.keys(scope).profile);
      } catch {
        /* ignore */
      }
      return null;
    }
  }

  setStoredUser(user: unknown, scope: AuthScope = 'user'): void {
    try {
      this.safeStorage()?.setItem(this.keys(scope).profile, JSON.stringify(user));
    } catch (e) {
      console.error(`[auth] Failed to persist ${scope} profile:`, e);
    }
  }

  clearStoredUser(scope: AuthScope = 'user'): void {
    try {
      this.safeStorage()?.removeItem(this.keys(scope).profile);
    } catch {
      /* ignore */
    }
  }

  private clearTokens(scope: AuthScope): void {
    try {
      const storage = this.safeStorage();
      const k = this.keys(scope);
      storage?.removeItem(k.access);
      storage?.removeItem(k.refresh);
      storage?.removeItem(k.profile);
    } catch (e) {
      console.error(`[auth] Failed to clear ${scope} tokens:`, e);
    }
  }

  hasToken(scope: AuthScope = 'user'): boolean {
    return this.getToken(scope) !== null;
  }

  setAuthTokens(accessToken: string, refreshToken: string | undefined, scope: AuthScope): void {
    this.setToken(accessToken, scope);
    if (refreshToken) {
      this.setRefreshToken(refreshToken, scope);
    }
    debugLog(`${scope} tokens persisted`, {
      access: redact(accessToken),
      refresh: redact(refreshToken ?? null),
    });
  }

  logout(scope: AuthScope = 'user'): void {
    this.clearTokens(scope);
  }

  // --- Refresh -------------------------------------------------------------

  private async refreshAccessToken(scope: AuthScope): Promise<boolean> {
    if (this.isRefreshing && this.refreshPromise) {
      return this.refreshPromise;
    }

    this.isRefreshing = true;
    this.refreshPromise = (async () => {
      try {
        const refreshToken = this.getRefreshToken(scope);
        if (!refreshToken) {
          debugLog('refresh skipped: no refresh token in storage', { scope });
          this.clearTokens(scope);
          return false;
        }

        const apiPrefix = this.baseUrl ? `${this.baseUrl}/api/` : `/api/`;
        const response = await fetch(`${apiPrefix}${this.apiVersion}/auth/refresh/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ refresh: refreshToken }),
          credentials: 'include',
        });

        if (!response.ok) {
          debugLog('refresh failed', { status: response.status, scope });
          this.clearTokens(scope);
          return false;
        }

        const data = await response.json();
        if (!data?.access) {
          debugLog('refresh response missing access token', data);
          this.clearTokens(scope);
          return false;
        }

        this.setToken(data.access, scope);
        if (data.refresh) {
          this.setRefreshToken(data.refresh, scope);
        }
        debugLog('refresh succeeded', { access: redact(data.access), scope });
        return true;
      } catch (error) {
        console.error('[auth] Token refresh threw:', error);
        this.clearTokens(scope);
        return false;
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  // --- Request ------------------------------------------------------------

  private buildHeaders(options: RequestInit = {}, scope: AuthScope = 'user'): Record<string, string> {
    // Don't auto-set Content-Type for FormData — browser must add the boundary.
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers as Record<string, string> | undefined),
    };

    const token = this.getToken(scope);
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
  }

  async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retryCount = 0,
    maxRetries = 1,
    allowHostFallback = true,
    scope: AuthScope = 'user'
  ): Promise<ApiResponse<T>> {
    const isAuthCall = isAuthEndpoint(endpoint);

    try {
      if (!this.baseUrl && !import.meta.env.DEV) {
        return {
          status: 0,
          error:
            'API base URL is not configured. In Vercel → Project Settings → Environment Variables, set VITE_API_BASE_URL to your Railway HTTPS origin (e.g. https://xxx.up.railway.app, no trailing slash), then Redeploy the frontend.',
        };
      }

      const prefix = this.baseUrl ? `${this.baseUrl}/api/` : `/api/`;
      const url = endpoint.startsWith('http') ? endpoint : `${prefix}${this.apiVersion}${endpoint}`;

      if (!this.hasLoggedApiBootstrap) {
        this.hasLoggedApiBootstrap = true;
        const envRaw = import.meta.env.VITE_API_BASE_URL as string | undefined;
        const origin = typeof window !== 'undefined' ? window.location.origin : '(ssr)';
        console.info('[LexiAI API]', {
          VITE_API_BASE_URL: envRaw && envRaw.trim() ? envRaw.trim() : '(unset)',
          resolvedRelativePrefix: `${prefix}${this.apiVersion}`,
          effectiveHostForRequests: this.baseUrl || origin,
          note:
            envRaw && envRaw.trim()
              ? 'Requests go to VITE_API_BASE_URL + /api/v1/…'
              : 'Without VITE_API_BASE_URL, requests use the SAME ORIGIN as this page + /api/v1/… (Vercel static has no Django — set VITE_API_BASE_URL to your Railway API and rebuild).',
        });
      }

      const headers = this.buildHeaders(options, scope);
      debugLog('→', options.method || 'GET', url, {
        hasAuthHeader: Boolean(headers['Authorization']),
        scope,
      });
      debugApiLog(options.method || 'GET', url);

      const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include',
      });

      debugLog('←', options.method || 'GET', url, { status: response.status });

      // Handle 401 — ONLY for protected endpoints. Auth endpoints return 401 for
      // "bad credentials" and must bubble up as a normal error.
      if (response.status === 401 && !isAuthCall && retryCount < maxRetries) {
        const refreshed = await this.refreshAccessToken(scope);
        if (refreshed) {
          return this.request<T>(
            endpoint,
            options,
            retryCount + 1,
            maxRetries,
            allowHostFallback,
            scope
          );
        }
        this.clearTokens(scope);
        this.handleAuthError(scope);
        return {
          status: 401,
          error: 'Authentication failed. Please log in again.',
        };
      }

      const contentType = (response.headers.get('content-type') || '').toLowerCase();
      const rawBody = await response.text();
      let data: unknown = null;
      if (rawBody) {
        if (contentType.includes('application/json')) {
          try {
            data = JSON.parse(rawBody) as unknown;
          } catch {
            data = { _nonJsonBody: rawBody.slice(0, 400) };
          }
        } else {
          data = rawBody;
        }
      }

      if (response.status === 403) {
        const detail =
          formatApiErrorMessage(data) ||
          (typeof data === 'object' &&
          data &&
          typeof (data as { detail?: unknown }).detail === 'string'
            ? String((data as { detail: string }).detail)
            : undefined);
        return {
          status: 403,
          error: detail || 'You do not have permission to access this resource.',
        };
      }

      if (!response.ok) {
        const errObj = (data && typeof data === 'object' && !Array.isArray(data) ? data : {}) as Record<
          string,
          unknown
        >;
        const flattened = formatApiErrorMessage(data);
        const textSnippet =
          typeof data === 'string'
            ? data.replace(/\s+/g, ' ').trim().slice(0, 200)
            : typeof errObj._nonJsonBody === 'string'
              ? String(errObj._nonJsonBody).replace(/\s+/g, ' ').trim().slice(0, 200)
              : '';
        const hintMissingApi =
          (response.status === 404 || response.status === 405) &&
          !this.baseUrl &&
          !import.meta.env.DEV
            ? ' This usually means VITE_API_BASE_URL was not set at build time, so the browser called /api/… on the Vercel host (static SPA — POST returns 405). Set VITE_API_BASE_URL to your Railway API origin (e.g. https://xxx.up.railway.app, no trailing slash) in Vercel → Settings → Environment Variables → Production, then Redeploy.'
            : '';

        const fallback =
          flattened ||
          (typeof errObj.error === 'string' ? errObj.error : '') ||
          (typeof errObj.message === 'string' ? errObj.message : '') ||
          (textSnippet ? `HTTP ${response.status}: ${textSnippet}` : '') ||
          `Request failed (HTTP ${response.status})`;
        return {
          status: response.status,
          error: `${fallback}${hintMissingApi}`,
          data: data as T,
        };
      }

      return { data: data as T, status: response.status };
    } catch (error) {
      // Network-level failure (DNS, offline, mixed-host). Retry once with
      // localhost ↔ 127.0.0.1 swap to work around Windows resolver quirks.
      if (allowHostFallback && !endpoint.startsWith('http') && this.baseUrl) {
        const originalBaseUrl = this.baseUrl;
        const alt = this.baseUrl.includes('localhost')
          ? this.baseUrl.replace('localhost', '127.0.0.1')
          : this.baseUrl.includes('127.0.0.1')
            ? this.baseUrl.replace('127.0.0.1', 'localhost')
            : null;
        if (alt && alt !== originalBaseUrl) {
          this.baseUrl = alt;
          try {
            return await this.request<T>(endpoint, options, retryCount, maxRetries, false, scope);
          } finally {
            this.baseUrl = originalBaseUrl;
          }
        }
      }

      console.error(`[auth] API request failed: ${endpoint}`, error);
      const msg = error instanceof Error ? error.message.toLowerCase() : '';
      const isNetworkFailure =
        (error instanceof TypeError && msg.includes('fetch')) ||
        msg.includes('failed to fetch') ||
        msg.includes('networkerror');
      const target = this.baseUrl || '(Vite proxy → Django)';
      const devHint =
        isNetworkFailure && import.meta.env.DEV
          ? ' Start Django (Docker: compose web / vite proxy) or match VITE_DJANGO_PROXY_PORT.'
          : '';
      const corsHint =
        isNetworkFailure && this.baseUrl && !import.meta.env.DEV
          ? ' If the browser console shows a CORS error, add this exact frontend origin to Railway CORS_ALLOWED_ORIGINS (no trailing slash), e.g. https://lexiai-one.vercel.app'
          : '';
      const missingBaseHint =
        isNetworkFailure && !this.baseUrl && !import.meta.env.DEV
          ? ' Set VITE_API_BASE_URL to your API origin on Vercel and redeploy. If the API is reachable, a CORS block also shows as "Failed to fetch" — fix CORS on the backend.'
          : '';
      return {
        status: 0,
        error: isNetworkFailure
          ? `Unable to reach API (${target}).${devHint}${corsHint}${missingBaseHint}`
          : error instanceof Error
            ? error.message
            : 'Network error',
      };
    }
  }

  async get<T>(endpoint: string, scope: AuthScope = 'user'): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' }, 0, 1, true, scope);
  }

  async post<T>(
    endpoint: string,
    body?: unknown,
    scope: AuthScope = 'user'
  ): Promise<ApiResponse<T>> {
    return this.request<T>(
      endpoint,
      {
        method: 'POST',
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
      },
      0,
      1,
      true,
      scope
    );
  }

  async put<T>(
    endpoint: string,
    body?: unknown,
    scope: AuthScope = 'user'
  ): Promise<ApiResponse<T>> {
    return this.request<T>(
      endpoint,
      {
        method: 'PUT',
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
      },
      0,
      1,
      true,
      scope
    );
  }

  async patch<T>(
    endpoint: string,
    body?: unknown,
    scope: AuthScope = 'user'
  ): Promise<ApiResponse<T>> {
    return this.request<T>(
      endpoint,
      {
        method: 'PATCH',
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
      },
      0,
      1,
      true,
      scope
    );
  }

  async delete<T>(endpoint: string, scope: AuthScope = 'user'): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' }, 0, 1, true, scope);
  }

  // --- Unauthorized handler ------------------------------------------------

  setUnauthorizedHandler(handler: (scope: AuthScope) => void): void {
    this.onUnauthorized = handler;
  }

  clearUnauthorizedHandler(): void {
    this.onUnauthorized = null;
  }

  private handleAuthError(scope: AuthScope): void {
    if (this.isHandlingUnauthorized) return;
    this.isHandlingUnauthorized = true;
    try {
      this.onUnauthorized?.(scope);
    } finally {
      this.isHandlingUnauthorized = false;
    }
  }
}

export const apiClient = new ApiClient();
