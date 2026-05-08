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
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
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

        const response = await fetch(`${this.baseUrl}/api/${this.apiVersion}/auth/refresh/`, {
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
      const url = endpoint.startsWith('http')
        ? endpoint
        : `${this.baseUrl}/api/${this.apiVersion}${endpoint}`;

      // #region agent log
      fetch('http://127.0.0.1:7247/ingest/bc726661-d383-4043-b18b-3deaa5cf7028',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'c2a3f7'},body:JSON.stringify({sessionId:'c2a3f7',runId:'pre-fix',hypothesisId:'H1',location:'client.ts:request:url-build',message:'API request prepared',data:{endpoint,url,baseUrl:this.baseUrl,apiVersion:this.apiVersion,method:options.method||'GET',hasAuthHeader:Boolean(this.getToken())},timestamp:Date.now()})}).catch(()=>{});
      // #endregion

      const response = await fetch(url, {
        ...options,
        headers: this.buildHeaders(options),
        credentials: 'include', // Include cookies in request
      });

      // #region agent log
      fetch('http://127.0.0.1:7247/ingest/bc726661-d383-4043-b18b-3deaa5cf7028',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'c2a3f7'},body:JSON.stringify({sessionId:'c2a3f7',runId:'pre-fix',hypothesisId:'H3',location:'client.ts:request:response',message:'API response received',data:{endpoint,url,status:response.status,ok:response.ok},timestamp:Date.now()})}).catch(()=>{});
      // #endregion

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
        return {
          status: response.status,
          error: data?.detail || data?.error || data?.message || 'Request failed',
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
      if (allowHostFallback && !endpoint.startsWith('http')) {
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
      // #region agent log
      fetch('http://127.0.0.1:7247/ingest/bc726661-d383-4043-b18b-3deaa5cf7028',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'c2a3f7'},body:JSON.stringify({sessionId:'c2a3f7',runId:'pre-fix',hypothesisId:'H2',location:'client.ts:request:catch',message:'API request threw before response',data:{endpoint,baseUrl:this.baseUrl,errorName:error instanceof Error?error.name:'unknown',errorMessage:error instanceof Error?error.message:'unknown'},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      const isNetworkFailure = error instanceof TypeError && error.message.toLowerCase().includes('fetch');
      return {
        status: 0,
        error: isNetworkFailure
          ? `Unable to reach API at ${this.baseUrl}. Please ensure backend is running and CORS is configured.`
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
