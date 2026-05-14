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

const ACCESS_TOKEN_KEY = 'lexiai.access_token';
const REFRESH_TOKEN_KEY = 'lexiai.refresh_token';
const USER_KEY = 'lexiai.user';

// Legacy keys (sessionStorage) — migrated on first read so existing tabs don't break.
const LEGACY_KEYS = ['access_token', 'refresh_token', 'user'] as const;

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

const DEBUG_AUTH = (() => {
  try {
    return import.meta.env.DEV || import.meta.env.VITE_DEBUG_AUTH === 'true';
  } catch {
    return false;
  }
})();

const debugLog = (...args: unknown[]) => {
  if (DEBUG_AUTH) {
    console.debug('[auth]', ...args);
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
  private onUnauthorized: (() => void) | null = null;

  constructor() {
    const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
    if (envBase !== undefined && envBase !== '') {
      this.baseUrl = envBase.replace(/\/$/, '');
    } else if (import.meta.env.DEV) {
      // Dev: rely on Vite proxy (see vite.config.ts) so we stay same-origin.
      this.baseUrl = '';
    } else {
      // Production build without VITE_API_BASE_URL — Docker on Windows often uses 18000 on the host.
      this.baseUrl = 'http://127.0.0.1:18000';
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
      for (const legacy of LEGACY_KEYS) {
        const newKey =
          legacy === 'access_token' ? ACCESS_TOKEN_KEY :
          legacy === 'refresh_token' ? REFRESH_TOKEN_KEY : USER_KEY;
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

  getToken(): string | null {
    try {
      return this.safeStorage()?.getItem(ACCESS_TOKEN_KEY) ?? null;
    } catch {
      return null;
    }
  }

  private setToken(token: string): void {
    try {
      this.safeStorage()?.setItem(ACCESS_TOKEN_KEY, token);
    } catch (e) {
      console.error('[auth] Failed to persist access token:', e);
    }
  }

  getRefreshToken(): string | null {
    try {
      return this.safeStorage()?.getItem(REFRESH_TOKEN_KEY) ?? null;
    } catch {
      return null;
    }
  }

  private setRefreshToken(token: string): void {
    try {
      this.safeStorage()?.setItem(REFRESH_TOKEN_KEY, token);
    } catch (e) {
      console.error('[auth] Failed to persist refresh token:', e);
    }
  }

  getStoredUser<T = unknown>(): T | null {
    try {
      const raw = this.safeStorage()?.getItem(USER_KEY);
      if (!raw) return null;
      return JSON.parse(raw) as T;
    } catch {
      try { this.safeStorage()?.removeItem(USER_KEY); } catch { /* ignore */ }
      return null;
    }
  }

  setStoredUser(user: unknown): void {
    try {
      this.safeStorage()?.setItem(USER_KEY, JSON.stringify(user));
    } catch (e) {
      console.error('[auth] Failed to persist user:', e);
    }
  }

  clearStoredUser(): void {
    try { this.safeStorage()?.removeItem(USER_KEY); } catch { /* ignore */ }
  }

  private clearTokens(): void {
    try {
      const storage = this.safeStorage();
      storage?.removeItem(ACCESS_TOKEN_KEY);
      storage?.removeItem(REFRESH_TOKEN_KEY);
      storage?.removeItem(USER_KEY);
    } catch (e) {
      console.error('[auth] Failed to clear tokens:', e);
    }
  }

  hasToken(): boolean {
    return this.getToken() !== null;
  }

  setAuthTokens(accessToken: string, refreshToken?: string): void {
    this.setToken(accessToken);
    if (refreshToken) {
      this.setRefreshToken(refreshToken);
    }
    debugLog('tokens persisted', { access: redact(accessToken), refresh: redact(refreshToken ?? null) });
  }

  logout(): void {
    this.clearTokens();
  }

  // --- Refresh -------------------------------------------------------------

  private async refreshAccessToken(): Promise<boolean> {
    if (this.isRefreshing && this.refreshPromise) {
      return this.refreshPromise;
    }

    this.isRefreshing = true;
    this.refreshPromise = (async () => {
      try {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
          debugLog('refresh skipped: no refresh token in storage');
          this.clearTokens();
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
          debugLog('refresh failed', { status: response.status });
          this.clearTokens();
          return false;
        }

        const data = await response.json();
        if (!data?.access) {
          debugLog('refresh response missing access token', data);
          this.clearTokens();
          return false;
        }

        this.setToken(data.access);
        // Backend has ROTATE_REFRESH_TOKENS=True + BLACKLIST_AFTER_ROTATION=True,
        // so we MUST persist the new refresh token if returned.
        if (data.refresh) {
          this.setRefreshToken(data.refresh);
        }
        debugLog('refresh succeeded', { access: redact(data.access) });
        return true;
      } catch (error) {
        console.error('[auth] Token refresh threw:', error);
        this.clearTokens();
        return false;
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  // --- Request ------------------------------------------------------------

  private buildHeaders(options: RequestInit = {}): Record<string, string> {
    // Don't auto-set Content-Type for FormData — browser must add the boundary.
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers as Record<string, string> | undefined),
    };

    const token = this.getToken();
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
    allowHostFallback = true
  ): Promise<ApiResponse<T>> {
    const isAuthCall = isAuthEndpoint(endpoint);

    try {
      const prefix = this.baseUrl ? `${this.baseUrl}/api/` : `/api/`;
      const url = endpoint.startsWith('http') ? endpoint : `${prefix}${this.apiVersion}${endpoint}`;

      const headers = this.buildHeaders(options);
      debugLog('→', options.method || 'GET', url, {
        hasAuthHeader: Boolean(headers['Authorization']),
      });

      const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include',
      });

      debugLog('←', options.method || 'GET', url, { status: response.status });

      // Handle 401 — ONLY for protected endpoints. Auth endpoints return 401 for
      // "bad credentials" and must bubble up as a normal error.
      if (response.status === 401 && !isAuthCall && retryCount < maxRetries) {
        const refreshed = await this.refreshAccessToken();
        if (refreshed) {
          return this.request<T>(endpoint, options, retryCount + 1, maxRetries, allowHostFallback);
        }
        // Refresh failed — clear creds and notify AuthContext.
        this.clearTokens();
        this.handleAuthError();
        return {
          status: 401,
          error: 'Authentication failed. Please log in again.',
        };
      }

      // 403 — authenticated but forbidden.
      if (response.status === 403) {
        let detail: string | undefined;
        try {
          const ct = response.headers.get('content-type');
          if (ct?.includes('application/json')) {
            const body = await response.json();
            detail = typeof body?.detail === 'string' ? body.detail : undefined;
          }
        } catch { /* ignore */ }
        return {
          status: 403,
          error: detail || 'You do not have permission to access this resource.',
        };
      }

      const contentType = response.headers.get('content-type');
      let data: unknown = null;
      if (contentType?.includes('application/json')) {
        try {
          data = await response.json();
        } catch {
          data = null;
        }
      } else if (response.ok) {
        try { data = await response.text(); } catch { data = null; }
      }

      if (!response.ok) {
        const errObj = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
        let fallback = typeof errObj.detail === 'string' ? errObj.detail : '';
        if (!fallback && data && typeof data === 'object' && !Array.isArray(data)) {
          const msgs = Object.entries(errObj).flatMap(([field, msgs]) =>
            Array.isArray(msgs)
              ? msgs.map((m) => `${field}: ${m}`)
              : [`${field}: ${String(msgs)}`]
          );
          if (msgs.length) fallback = msgs.join('; ');
        }
        return {
          status: response.status,
          error: fallback || (typeof errObj.error === 'string' ? errObj.error : '')
            || (typeof errObj.message === 'string' ? errObj.message : '')
            || 'Request failed',
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
            return await this.request<T>(endpoint, options, retryCount, maxRetries, false);
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
      const target = this.baseUrl || '(Vite proxy → Django port from vite.config, default 18000 for Docker)';
      return {
        status: 0,
        error: isNetworkFailure
          ? `Unable to reach API (${target}). Start Django (Docker: compose web on WEB_HOST_PORT, default 18000; or runserver). If dev uses Vite proxy, set VITE_DJANGO_PROXY_PORT to match.`
          : error instanceof Error
            ? error.message
            : 'Network error',
      };
    }
  }

  async get<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  async post<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  // --- Unauthorized handler ------------------------------------------------

  setUnauthorizedHandler(handler: () => void): void {
    this.onUnauthorized = handler;
  }

  clearUnauthorizedHandler(): void {
    this.onUnauthorized = null;
  }

  private handleAuthError(): void {
    if (this.isHandlingUnauthorized) return;
    this.isHandlingUnauthorized = true;
    try {
      this.onUnauthorized?.();
    } finally {
      this.isHandlingUnauthorized = false;
    }
  }
}

export const apiClient = new ApiClient();
