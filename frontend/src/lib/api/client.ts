/**
 * Centralized API client with JWT authentication, token refresh, and error handling.
 * Handles:
 * - Automatic token injection from cookies
 * - Token refresh on 401 responses
 * - Global error handling (401 → login, 403 → unauthorized, network errors)
 * - Request/response interceptors
 */

export interface ApiResponse<T = unknown> {
  data?: T;
  error?: string;
  detail?: string;
  status: number;
}

export interface ApiError extends Error {
  status?: number;
  response?: any;
}

class ApiClient {
  private baseUrl: string;
  private apiVersion: string;
  private isRefreshing = false;
  private refreshPromise: Promise<boolean> | null = null;
  private isHandlingUnauthorized = false;

  constructor() {
    const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
    // Dev + no env: use relative /api so Vite proxy hits backend (see vite.config.ts).
    // Set VITE_API_BASE_URL when you need a fixed host (e.g. Docker-only API URL).
    if (envBase !== undefined && envBase !== '') {
      this.baseUrl = envBase.replace(/\/$/, '');
    } else if (import.meta.env.DEV) {
      this.baseUrl = '';
    } else {
      this.baseUrl = 'http://127.0.0.1:8000';
    }
    this.apiVersion = import.meta.env.VITE_API_VERSION || 'v1';
  }

  private getToken(): string | null {
    // Read JWT from httpOnly cookie (set by server)
    // We can't directly access httpOnly cookies from JS, so we rely on the browser
    // to send them automatically with credentials: 'include'
    // For non-httpOnly scenarios, fall back to sessionStorage
    try {
      const token = sessionStorage.getItem('access_token');
      return token;
    } catch {
      return null;
    }
  }

  private setToken(token: string): void {
    try {
      sessionStorage.setItem('access_token', token);
    } catch (e) {
      console.error('Failed to store token:', e);
    }
  }

  private getRefreshToken(): string | null {
    try {
      return sessionStorage.getItem('refresh_token');
    } catch {
      return null;
    }
  }

  private setRefreshToken(token: string): void {
    try {
      sessionStorage.setItem('refresh_token', token);
    } catch (e) {
      console.error('Failed to store refresh token:', e);
    }
  }

  private clearTokens(): void {
    try {
      sessionStorage.removeItem('access_token');
      sessionStorage.removeItem('refresh_token');
      sessionStorage.removeItem('user');
    } catch (e) {
      console.error('Failed to clear tokens:', e);
    }
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (this.isRefreshing) {
      return this.refreshPromise || Promise.resolve(false);
    }

    this.isRefreshing = true;
    this.refreshPromise = (async () => {
      try {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
          this.clearTokens();
          return false;
        }

        const apiPrefix = this.baseUrl ? `${this.baseUrl}/api/` : `/api/`;
        const response = await fetch(`${apiPrefix}${this.apiVersion}/auth/refresh/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refresh: refreshToken }),
          credentials: 'include',
        });

        if (!response.ok) {
          this.clearTokens();
          return false;
        }

        const data = await response.json();
        this.setToken(data.access);
        if (data.refresh) {
          this.setRefreshToken(data.refresh);
        }
        return true;
      } catch (error) {
        console.error('Token refresh failed:', error);
        this.clearTokens();
        return false;
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  private buildHeaders(options: RequestInit = {}): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const token = this.getToken();
    if (token) {
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
    try {
      const prefix = this.baseUrl ? `${this.baseUrl}/api/` : `/api/`;
      const url = endpoint.startsWith('http') ? endpoint : `${prefix}${this.apiVersion}${endpoint}`;

      const response = await fetch(url, {
        ...options,
        headers: this.buildHeaders(options),
        credentials: 'include', // Include cookies in request
      });

      // Handle 401 - attempt token refresh
      if (response.status === 401 && retryCount < maxRetries) {
        const refreshed = await this.refreshAccessToken();
        if (refreshed) {
          return this.request<T>(endpoint, options, retryCount + 1, maxRetries);
        } else {
          this.clearTokens();
          this.handleAuthError();
          return {
            status: 401,
            error: 'Authentication failed. Please log in again.',
          };
        }
      }

      // Handle 403 - forbidden
      if (response.status === 403) {
        return {
          status: 403,
          error: 'You do not have permission to access this resource.',
        };
      }

      // Parse response
      const contentType = response.headers.get('content-type');
      let data: any = null;

      if (contentType?.includes('application/json')) {
        data = await response.json();
      } else if (response.ok) {
        data = await response.text();
      }

      // Non-OK responses
      if (!response.ok) {
        let fallback = typeof data?.detail === 'string' ? data.detail : '';
        if (!fallback && data && typeof data === 'object' && !Array.isArray(data)) {
          const msgs = Object.entries(data as Record<string, unknown>).flatMap(([field, msgs]) =>
            Array.isArray(msgs) ? msgs.map((m) => `${field}: ${m}` as string) : [`${field}: ${String(msgs)}`]
          );
          if (msgs.length) fallback = msgs.join('; ');
        }
        return {
          status: response.status,
          error: fallback || data?.error || data?.message || 'Request failed',
          data,
        };
      }

      return {
        data: data as T,
        status: response.status,
      };
    } catch (error) {
      // Retry once with alternate localhost host representation.
      // Some Windows/network setups resolve localhost inconsistently for browser fetch.
      if (allowHostFallback && !endpoint.startsWith('http') && this.baseUrl) {
        const originalBaseUrl = this.baseUrl;
        const alternateBaseUrl = this.baseUrl.includes('localhost')
          ? this.baseUrl.replace('localhost', '127.0.0.1')
          : this.baseUrl.includes('127.0.0.1')
            ? this.baseUrl.replace('127.0.0.1', 'localhost')
            : null;

        if (alternateBaseUrl && alternateBaseUrl !== originalBaseUrl) {
          this.baseUrl = alternateBaseUrl;
          try {
            return await this.request<T>(endpoint, options, retryCount, maxRetries, false);
          } finally {
            this.baseUrl = originalBaseUrl;
          }
        }
      }

      console.error(`API request failed: ${endpoint}`, error);
      const msg = error instanceof Error ? error.message.toLowerCase() : '';
      const isNetworkFailure =
        (error instanceof TypeError && msg.includes('fetch')) ||
        msg.includes('failed to fetch') ||
        msg.includes('networkerror');
      const target =
        this.baseUrl || '(Vite proxy → ensure Django at http://127.0.0.1:8000)';
      return {
        status: 0,
        error: isNetworkFailure
          ? `Unable to reach API (${target}). Start the Django server (e.g. runserver or docker compose web). If dev uses proxy, backend must listen on port 8000.`
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
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(endpoint: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  // Token management
  hasToken(): boolean {
    return this.getToken() !== null;
  }

  setAuthTokens(accessToken: string, refreshToken?: string): void {
    this.setToken(accessToken);
    if (refreshToken) {
      this.setRefreshToken(refreshToken);
    }
  }

  logout(): void {
    this.clearTokens();
  }

  // Error handler callback
  private onUnauthorized: (() => void) | null = null;

  setUnauthorizedHandler(handler: () => void): void {
    this.onUnauthorized = handler;
  }

  private handleAuthError(): void {
    if (this.isHandlingUnauthorized) {
      return;
    }

    this.isHandlingUnauthorized = true;

    try {
      if (this.onUnauthorized) {
        this.onUnauthorized();
      }
    } finally {
      this.isHandlingUnauthorized = false;
    }
  }

  clearUnauthorizedHandler(): void {
    this.onUnauthorized = null;
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
