/**
 * Admin API module
 * Handles: document management, analytics, user management, feedback analytics
 */

import { apiClient, ApiResponse } from './client';

export interface Document {
  id: number;
  title: string;
  file_name: string;
  file_size: number;
  status: 'pending' | 'processing' | 'ready' | 'failed';
  owner: number;
  owner_email?: string;
  extracted_text?: string;
  error_message?: string;
  chunk_count?: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  id: number;
  title: string;
  status: string;
}

export interface QueryLog {
  id: number;
  user: number;
  user_email?: string;
  query_text: string;
  llm_response: string;
  llm_model: string;
  retrieval_confidence: number;
  latency_ms: number;
  created_at: string;
}

export interface AnalyticsStats {
  total_queries: number;
  avg_latency_ms: number;
  avg_retrieval_confidence: number;
  queries_by_model: Record<string, number>;
  feedback_breakdown: {
    helpful: number;
    not_helpful: number;
  };
  total_users: number;
  period_days: number;
}

export interface User {
  id: number;
  email: string;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export class AdminAPI {
  /**
   * Get all documents (admin only)
   */
  static async getDocuments(
    limit = 50,
    offset = 0
  ): Promise<ApiResponse<{ count: number; results: Document[] }>> {
    return apiClient.get<{ count: number; results: Document[] }>(
      `/documents/?limit=${limit}&offset=${offset}`
    );
  }

  /**
   * Get single document
   */
  static async getDocument(id: number): Promise<ApiResponse<Document>> {
    return apiClient.get<Document>(`/documents/${id}/`);
  }

  /**
   * Upload document
   */
  static async uploadDocument(
    file: File,
    title?: string
  ): Promise<ApiResponse<DocumentUploadResponse>> {
    const formData = new FormData();
    formData.append('file', file);
    if (title) {
      formData.append('title', title);
    }

    // Use raw fetch for file upload (multipart/form-data)
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL}/api/${import.meta.env.VITE_API_VERSION || 'v1'}/documents/`,
        {
          method: 'POST',
          body: formData,
          credentials: 'include',
          headers: {
            Authorization: `Bearer ${sessionStorage.getItem('access_token') || ''}`,
          },
        }
      );

      const data = await response.json();

      if (!response.ok) {
        return {
          status: response.status,
          error: data.detail || data.error || 'Upload failed',
        };
      }

      return {
        status: response.status,
        data,
      };
    } catch (error) {
      return {
        status: 0,
        error: error instanceof Error ? error.message : 'Upload failed',
      };
    }
  }

  /**
   * Delete document
   */
  static async deleteDocument(id: number): Promise<ApiResponse<void>> {
    return apiClient.delete<void>(`/documents/${id}/`);
  }

  /**
   * Trigger document ingestion/embedding
   */
  static async ingestDocument(id: number): Promise<ApiResponse<{ status: string }>> {
    return apiClient.post<{ status: string }>(`/documents/${id}/ingest/`, {});
  }

  /**
   * Get AI analytics
   */
  static async getAnalytics(days = 7): Promise<ApiResponse<AnalyticsStats>> {
    return apiClient.get<AnalyticsStats>(`/ai/analytics/?days=${days}`);
  }

  /**
   * Get query logs with filtering
   */
  static async getQueryLogs(
    limit = 50,
    offset = 0,
    userId?: number
  ): Promise<ApiResponse<{ count: number; results: QueryLog[] }>> {
    let url = `/ai/query-logs/?limit=${limit}&offset=${offset}`;
    if (userId) {
      url += `&user=${userId}`;
    }
    return apiClient.get<{ count: number; results: QueryLog[] }>(url);
  }

  /**
   * Get all users (admin only)
   */
  static async getUsers(
    limit = 50,
    offset = 0
  ): Promise<ApiResponse<{ count: number; results: User[] }>> {
    return apiClient.get<{ count: number; results: User[] }>(
      `/accounts/users/?limit=${limit}&offset=${offset}`
    );
  }

  /**
   * Update user role (admin only)
   */
  static async updateUserRole(
    userId: number,
    role: string
  ): Promise<ApiResponse<User>> {
    return apiClient.patch<User>(`/accounts/users/${userId}/`, { role });
  }

  /**
   * Deactivate user (admin only)
   */
  static async deactivateUser(userId: number): Promise<ApiResponse<User>> {
    return apiClient.patch<User>(`/accounts/users/${userId}/`, { is_active: false });
  }
}
