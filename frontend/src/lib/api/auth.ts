/**
 * Authentication API module
 * Handles: login, register, logout, profile, token refresh
 */

import { apiClient, ApiResponse, formatApiErrorMessage } from './client';

export interface User {
  id: number;
  name: string;
  email: string;
  username: string;
  first_name?: string;
  last_name?: string;
  role: 'guest' | 'user' | 'admin';
  is_active?: boolean;
  is_verified?: boolean;
  is_premium?: boolean;
  // Canonical Django admin flags. Mirrored from
  // `accounts.AccountProfileSerializer`. Used by `AuthContext.isAdmin` and
  // `ProtectedRoute(requireAdmin)`. NEVER trust these alone for backend
  // authorization — they are echoed from the JWT user payload purely for UI
  // gating; the backend still enforces `IsAdminUser` / `is_staff` on every
  // protected endpoint.
  is_staff?: boolean;
  is_superuser?: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  password_confirm: string;
  full_name?: string;
}

export interface RegisterResponse {
  id: number;
  email: string;
  username: string | null;
  first_name?: string;
  last_name?: string;
  role?: { code?: string; name?: string } | string | null;
  created_at: string;
}

type BackendUser = {
  id: number;
  email: string;
  username?: string | null;
  first_name?: string;
  last_name?: string;
  role?: { code?: string; name?: string } | string | null;
  is_active?: boolean;
  is_verified?: boolean;
  is_premium?: boolean;
  is_staff?: boolean;
  is_superuser?: boolean;
  created_at: string;
};

const normalizeRole = (role: BackendUser['role']): User['role'] => {
  if (typeof role === 'string') {
    if (role === 'admin' || role === 'guest') return role;
    return 'user';
  }

  if (role?.code === 'admin') return 'admin';
  if (role?.code === 'guest') return 'guest';
  return 'user';
};

const buildDisplayName = (raw: BackendUser): string => {
  const fullName = `${raw.first_name || ''} ${raw.last_name || ''}`.trim();
  if (fullName) return fullName;
  if (raw.username) return raw.username;
  return raw.email;
};

export const normalizeUser = (raw: BackendUser): User => ({
  id: raw.id,
  name: buildDisplayName(raw),
  email: raw.email,
  username: raw.username || raw.email,
  first_name: raw.first_name,
  last_name: raw.last_name,
  role: normalizeRole(raw.role),
  is_active: raw.is_active,
  is_verified: raw.is_verified,
  is_premium: raw.is_premium,
  is_staff: raw.is_staff,
  is_superuser: raw.is_superuser,
  created_at: raw.created_at,
});

const isSuccessfulAuth = (response: ApiResponse<LoginResponse>): boolean => {
  const data = response.data;
  return (
    response.status >= 200 &&
    response.status < 300 &&
    !!data &&
    typeof data.access === 'string' &&
    data.access.length > 0
  );
};

export class AuthAPI {
  /**
   * Authenticate by email + password.
   *
   * On 401 / 400 the apiClient bubbles the error in `response.error` WITHOUT
   * triggering the global unauthorized handler (auth endpoints are exempt by
   * design — see client.ts AUTH_ENDPOINT_PATTERNS). We rely on that here so
   * "wrong password" surfaces as a normal form error, not a forced logout.
   */
  static async login(credentials: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    const response = await apiClient.post<LoginResponse>('/auth/login/', {
      email: credentials.email,
      password: credentials.password,
    });

    if (!isSuccessfulAuth(response)) {
      // Strip stale tokens just in case a prior login left them; do NOT call
      // setAuthTokens with undefined access.
      return {
        status: response.status,
        error:
          response.error ||
          (response.status === 401
            ? 'Invalid email or password.'
            : 'Login failed. Please try again.'),
        data: response.data,
      };
    }

    apiClient.setAuthTokens(response.data!.access, response.data!.refresh);

    if (response.data?.user) {
      response.data.user = normalizeUser(response.data.user as unknown as BackendUser);
    }

    return response;
  }

  /**
   * Start an ephemeral authenticated guest session (real JWT, ephemeral user).
   */
  static async guestSession(): Promise<ApiResponse<LoginResponse>> {
    const response = await apiClient.post<LoginResponse>('/auth/guest-session/', {});

    if (!isSuccessfulAuth(response)) {
      return {
        status: response.status,
        error: response.error || 'Could not start guest session.',
        data: response.data,
      };
    }

    apiClient.setAuthTokens(response.data!.access, response.data!.refresh);

    if (response.data?.user) {
      response.data.user = normalizeUser(response.data.user as unknown as BackendUser);
    }

    return response;
  }

  /**
   * Register new user
   */
  static async register(data: RegisterRequest): Promise<ApiResponse<RegisterResponse>> {
    return apiClient.post<RegisterResponse>('/auth/register/', data);
  }

  /**
   * Register and immediately login user
   */
  static async registerAndLogin(data: RegisterRequest): Promise<ApiResponse<LoginResponse>> {
    const registerResponse = await this.register(data);
    if (registerResponse.status < 200 || registerResponse.status >= 300) {
      const err =
        (typeof registerResponse.error === 'string' && registerResponse.error.trim()) ||
        formatApiErrorMessage(registerResponse.data) ||
        'Registration failed.';
      return {
        status: registerResponse.status,
        error: err,
      };
    }

    return this.login({
      email: data.email,
      password: data.password,
    });
  }

  /**
   * Get current user profile
   */
  static async getCurrentUser(): Promise<ApiResponse<User>> {
    const response = await apiClient.get<BackendUser>('/auth/profile/');
    if (!response.data) {
      return response as ApiResponse<User>;
    }

    return {
      ...response,
      data: normalizeUser(response.data),
    };
  }

  /**
   * Update user profile (`full_name` maps to profile on backend)
   */
  static async updateProfile(
    updates: Partial<User> & { full_name?: string }
  ): Promise<ApiResponse<User>> {
    const payload: Record<string, unknown> = { ...updates };
    if (updates.name !== undefined && updates.full_name === undefined) {
      payload.full_name = updates.name;
      delete payload.name;
    }
    const response = await apiClient.patch<BackendUser>('/auth/profile/', payload);
    if (!response.data) {
      return response as ApiResponse<User>;
    }

    return {
      ...response,
      data: normalizeUser(response.data),
    };
  }

  /**
   * Logout: blacklist refresh token on backend, then clear local creds.
   *
   * Backend's `TokenBlacklistView` REQUIRES the refresh token in the body,
   * otherwise it 400s. Previously we sent `{}` which silently failed and left
   * the refresh token usable for `ACCESS_TOKEN_LIFETIME` more minutes.
   */
  static async logout(): Promise<void> {
    const refresh = apiClient.getRefreshToken();
    if (refresh) {
      try {
        await apiClient.post('/auth/logout/', { refresh });
      } catch (error) {
        console.warn('Logout notification failed (non-critical):', error);
      }
    }

    apiClient.logout();
  }

  /**
   * Check if token is valid
   */
  static isAuthenticated(): boolean {
    return apiClient.hasToken();
  }
}
