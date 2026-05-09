/**
 * Authentication API module
 * Handles: login, register, logout, profile, token refresh
 */

import { apiClient, ApiResponse } from './client';

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
  created_at: raw.created_at,
});

export class AuthAPI {
  /**
   * Login user and store tokens
   */
  static async login(credentials: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    const response = await apiClient.post<LoginResponse>('/auth/login/', {
      email: credentials.email,
      password: credentials.password,
    });

    if (response.data?.access) {
      apiClient.setAuthTokens(response.data.access, response.data.refresh);
    }

    if (response.data?.user) {
      response.data.user = normalizeUser(response.data.user as unknown as BackendUser);
    }

    return response;
  }

  /**
   * Start an ephemeral guest session (JWT + server-side user). Frontend still tracks guest quota.
   */
  static async guestSession(): Promise<ApiResponse<LoginResponse>> {
    const response = await apiClient.post<LoginResponse>('/auth/guest-session/', {});

    if (response.data?.access) {
      apiClient.setAuthTokens(response.data.access, response.data.refresh);
    }

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
    if (!registerResponse.data) {
      return {
        status: registerResponse.status,
        error: registerResponse.error || 'Registration failed',
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
   * Logout user
   */
  static async logout(): Promise<void> {
    // Optional: notify backend of logout
    try {
      await apiClient.post('/auth/logout/', {});
    } catch (error) {
      console.warn('Logout notification failed (non-critical):', error);
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
