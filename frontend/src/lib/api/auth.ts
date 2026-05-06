/**
 * Authentication API module
 * Handles: login, register, logout, profile, token refresh
 */

import { apiClient, ApiResponse } from './client';

export interface User {
  id: number;
  email: string;
  username: string;
  first_name?: string;
  last_name?: string;
  role: 'guest' | 'user' | 'admin';
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  username: string;
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
  password2: string;
}

export interface RegisterResponse {
  user: User;
  access: string;
  refresh: string;
}

export class AuthAPI {
  /**
   * Login user and store tokens
   */
  static async login(credentials: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    const response = await apiClient.post<LoginResponse>('/auth/login/', credentials);

    if (response.data) {
      apiClient.setAuthTokens(response.data.access, response.data.refresh);
    }

    return response;
  }

  /**
   * Register new user
   */
  static async register(data: RegisterRequest): Promise<ApiResponse<RegisterResponse>> {
    const response = await apiClient.post<RegisterResponse>('/auth/register/', data);

    if (response.data) {
      apiClient.setAuthTokens(response.data.access, response.data.refresh);
    }

    return response;
  }

  /**
   * Get current user profile
   */
  static async getCurrentUser(): Promise<ApiResponse<User>> {
    return apiClient.get<User>('/accounts/me/');
  }

  /**
   * Update user profile
   */
  static async updateProfile(updates: Partial<User>): Promise<ApiResponse<User>> {
    return apiClient.patch<User>('/accounts/me/', updates);
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
