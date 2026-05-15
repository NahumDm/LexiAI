/**
 * Admin API module
 * Handles: document management, analytics, user management, feedback analytics.
 *
 * Every call here goes through `apiClient`, which injects
 * `Authorization: Bearer <access>` from localStorage and handles 401 → refresh →
 * retry transparently. DO NOT introduce a parallel fetch path or duplicate the
 * token-reading logic — admin uploads previously did this and read tokens from
 * `sessionStorage`, which silently broke after the auth refactor moved tokens
 * to localStorage.
 *
 * Endpoint reality (verified against lexiai_backend URLConf):
 *   - GET    /api/v1/documents/admin/        ✓ AdminDocumentListView  (IsAdminUser, ?search=)
 *   - GET    /api/v1/documents/<id>/         ✓ DocumentDetailView     (owner-scoped — admin retrieve TODO)
 *   - DELETE /api/v1/documents/admin/<id>/     ✓ AdminDocumentDestroyView (IsAdminUser)
 *   - POST   /api/v1/documents/<id>/ingest/    ✓ AdminDocumentReprocessView (IsAdminUser)
 *   - POST   /api/v1/documents/               ✓ DocumentListCreateView (uploads land owner-scoped)
 *   - GET    /api/v1/ai/analytics/?days=N    ✓ analytics_view         (IsAdminUser, extended payload)
 *   - GET    /api/v1/ai/query-logs/          ✓ AdminQueryLogListView  (IsAdminUser, ?search=, ?min_confidence=)
 *   - GET    /api/v1/accounts/users/         ✓ AdminUserListView      (IsAdminUser, ?search=)
 *   - PATCH  /api/v1/accounts/users/<id>/   ✓ AdminUserDetailView    (IsAdminUser, partial update)
 *   - GET    /api/v1/feedback/               ✓ AdminFeedbackListView  (IsAdminUser, ?is_helpful=, ?search=)
 *
 * REMAINING BACKEND GAPS:
 *   1. Admin retrieve on `DocumentDetailView`: still owner-scoped for GET.
 *   2. Admin upload: files land under the caller's `owner` FK (no on-behalf upload).
 */

import { apiClient, ApiResponse, type AuthScope } from './client';

const ADMIN_SCOPE: AuthScope = 'admin';

/** Global document counts from GET /documents/admin/ (`stats`); not affected by ?search=. */
export interface DocumentAdminStats {
  total: number;
  ready: number;
  processing: number;
  pending: number;
  failed: number;
  archived: number;
}

export interface AdminUserStats {
  total: number;
  active: number;
  staff: number;
}

export interface FeedbackAdminStats {
  total: number;
  helpful: number;
  unhelpful: number;
}

export interface QueryLogAdminStats {
  total_queries: number;
  avg_latency_ms: number;
  avg_retrieval_confidence: number;
  low_confidence_count: number;
}

export interface Document {
  id: number;
  title: string;
  description?: string;
  source_file?: string | null;
  source_file_url?: string | null;
  /** Admin list remaps uploaded→pending and metadata failures→failed. */
  status: 'ready' | 'processing' | 'pending' | 'failed' | 'archived' | 'uploaded' | string;
  metadata?: Record<string, unknown>;
  page_count?: number | null;
  file_size?: number | null;
  extracted_text?: string;
  analysis_summary?: string;
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
  user: number | null;
  user_email?: string;
  /**
   * Backend mirrors the storage column as both `query`/`response` (the
   * admin-API spec) and the original `query_text`/`llm_response` (legacy
   * callers). Both are surfaced here as optional so the UI can render
   * whichever shape the server emitted without runtime checks.
   */
  query?: string;
  response?: string;
  query_text?: string;
  llm_response?: string;
  llm_model: string;
  retrieval_confidence: number;
  latency_ms: number;
  created_at: string;
}

export interface AnalyticsStats {
  // Window-scoped (over `period_days`):
  total_queries: number;
  avg_latency_ms: number;
  avg_retrieval_confidence: number;
  queries_by_model: Record<string, number>;
  helpful_feedback: number;
  unhelpful_feedback: number;
  /**
   * Legacy alias for `helpful_feedback` / `unhelpful_feedback`. Kept so
   * older consumers (FeedbackPage stat cards) keep working unchanged.
   */
  feedback_breakdown: {
    helpful: number;
    not_helpful: number;
  };
  period_days: number;

  // Global (not window-scoped):
  total_documents: number;
  total_users: number;
  active_users_in_period: number;

  /** All-time QueryLog / feedback rollups split out from primary keys (additive). */
  total_queries_in_period?: number;
  avg_latency_ms_in_period?: number;
  avg_retrieval_confidence_in_period?: number;
  helpful_feedback_in_period?: number;
  unhelpful_feedback_in_period?: number;
}

export interface AdminUser {
  id: number;
  email: string;
  username: string;
  first_name?: string;
  last_name?: string;
  role: string | { code?: string; name?: string } | null;
  is_active: boolean;
  is_staff?: boolean;
  is_superuser?: boolean;
  is_verified?: boolean;
  is_premium?: boolean;
  date_joined?: string;
  last_login?: string | null;
  created_at?: string;
}

export interface FeedbackEntry {
  id: number;
  query_log: number;
  user?: number | null;
  user_email?: string;
  /** Backend-derived boolean: true when rating === 'up'. */
  is_helpful: boolean;
  /** Underlying rating value; preserved for filtering / display. */
  rating: 'up' | 'down';
  comment?: string;
  /** Joined from the parent QueryLog so the UI doesn't need a 2nd fetch. */
  query?: string;
  response?: string;
  /** Legacy aliases — kept so older callers keep compiling. */
  query_text?: string;
  created_at: string;
}

/** DRF pagination envelope. We accept either this shape or a raw array. */
export interface Paginated<T> {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}

const unwrapList = <T>(payload: unknown): T[] => {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload as T[];
  const env = payload as Paginated<T>;
  if (Array.isArray(env.results)) return env.results;
  return [];
};

// Small helper to build a query string from a sparse object. Skips
// undefined/empty values so we don't end up with `?search=&limit=`.
const qs = (
  params: Record<string, string | number | undefined | null>,
  reload?: boolean
): string => {
  const entries = Object.entries(params).filter(
    ([, value]) => value !== undefined && value !== null && value !== ''
  );
  const search = new URLSearchParams();
  for (const [key, value] of entries) {
    search.set(key, String(value));
  }
  if (reload) {
    search.set('_cb', String(Date.now()));
  }
  const q = search.toString();
  return q ? `?${q}` : reload ? `?_cb=${Date.now()}` : '';
};

export class AdminAPI {
  /**
   * GET /api/v1/documents/admin/
   *
   * Admin-only GLOBAL list of every document on the system (not
   * owner-scoped). Optional `search` filters via the backend's
   * `?search=` query param (icontains over title + description).
   */
  static async getDocuments(
    options: { search?: string; reload?: boolean } = {}
  ): Promise<ApiResponse<{ count: number; results: Document[]; stats: DocumentAdminStats }>> {
    const response = await apiClient.get<
      | Document[]
      | Paginated<Document>
      | { count: number; results: Document[]; stats: DocumentAdminStats }
    >(`/documents/admin/${qs({ search: options.search }, options.reload)}`, ADMIN_SCOPE);
    const raw = response.data;
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'results' in raw && 'stats' in raw) {
      const env = raw as { count: number; results: Document[]; stats: DocumentAdminStats };
      return {
        ...response,
        data: { count: env.count, results: env.results, stats: env.stats },
      };
    }
    const list = unwrapList<Document>(raw);
    const count = !Array.isArray(raw) ? (raw as Paginated<Document>)?.count ?? list.length : list.length;
    const stats: DocumentAdminStats = {
      total: count,
      ready: list.filter((d) => d.status === 'ready').length,
      processing: list.filter((d) => d.status === 'processing').length,
      pending: list.filter((d) => d.status === 'pending' || d.status === 'uploaded').length,
      failed: list.filter((d) => d.status === 'failed').length,
      archived: list.filter((d) => d.status === 'archived').length,
    };
    return { ...response, data: { count, results: list, stats } };
  }

  static async getDocument(id: number): Promise<ApiResponse<Document>> {
    return apiClient.get<Document>(`/documents/${id}/`, ADMIN_SCOPE);
  }

  /**
   * Upload document. Uses apiClient so the Authorization header is sourced
   * from the SAME place as every other call (localStorage via apiClient),
   * NOT from sessionStorage like the legacy implementation.
   */
  static async uploadDocument(
    file: File,
    title?: string
  ): Promise<ApiResponse<DocumentUploadResponse>> {
    const formData = new FormData();
    formData.append('source_file', file);
    formData.append('title', title || file.name);
    return apiClient.post<DocumentUploadResponse>('/documents/', formData, ADMIN_SCOPE);
  }

  static async deleteDocument(id: number): Promise<ApiResponse<void>> {
    return apiClient.delete<void>(`/documents/${id}/`, ADMIN_SCOPE);
  }

  /** Admin-only delete of any document (global). */
  static async deleteDocumentAdmin(id: number, reload?: boolean): Promise<ApiResponse<void>> {
    const suffix = reload ? `?_cb=${Date.now()}` : '';
    return apiClient.delete<void>(`/documents/admin/${id}/${suffix}`, ADMIN_SCOPE);
  }

  /**
   * Trigger document ingestion/embedding.
   * NOTE: this endpoint is NOT implemented on the backend yet. The UI will
   * receive a 404 — DocumentsPage surfaces this as a non-destructive warning.
   */
  static async ingestDocument(
    id: number
  ): Promise<ApiResponse<{ message: string; document_id: number; job_id: string; status: string }>> {
    return apiClient.post<{ message: string; document_id: number; job_id: string; status: string }>(
      `/documents/${id}/ingest/`,
      {},
      ADMIN_SCOPE
    );
  }

  /** GET /api/v1/ai/analytics/?days=N — IsAdminUser. */
  static async getAnalytics(days = 7, reload?: boolean): Promise<ApiResponse<AnalyticsStats>> {
    const params = new URLSearchParams();
    params.set('days', String(days));
    if (reload) {
      params.set('_cb', String(Date.now()));
    }
    return apiClient.get<AnalyticsStats>(`/ai/analytics/?${params.toString()}`, ADMIN_SCOPE);
  }

  /**
   * GET /api/v1/ai/query-logs/
   *
   * Admin-only RAG query log feed. The backend serializer maps storage
   * names → SPA names: `query_text` → `query`, `llm_response` → `response`.
   * Both shapes are surfaced on the typed `QueryLog` below so legacy
   * callers stay compiling. Supports `?search=` and confidence bounds.
   */
  static async getQueryLogs(
    options: {
      search?: string;
      minConfidence?: number;
      maxConfidence?: number;
      reload?: boolean;
    } = {}
  ): Promise<ApiResponse<{ count: number; results: QueryLog[]; stats: QueryLogAdminStats }>> {
    const response = await apiClient.get<
      QueryLog[] | Paginated<QueryLog> | { count: number; results: QueryLog[]; stats: QueryLogAdminStats }
    >(
      `/ai/query-logs/${qs(
        {
          search: options.search,
          min_confidence: options.minConfidence,
          max_confidence: options.maxConfidence,
        },
        options.reload
      )}`,
      ADMIN_SCOPE
    );
    const raw = response.data;
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'results' in raw && 'stats' in raw) {
      const env = raw as { count: number; results: QueryLog[]; stats: QueryLogAdminStats };
      return { ...response, data: { count: env.count, results: env.results, stats: env.stats } };
    }
    const list = unwrapList<QueryLog>(raw);
    const count = !Array.isArray(raw) ? (raw as Paginated<QueryLog>)?.count ?? list.length : list.length;
    const stats: QueryLogAdminStats = {
      total_queries: count,
      avg_latency_ms: 0,
      avg_retrieval_confidence: 0,
      low_confidence_count: list.filter((l) => l.retrieval_confidence < 0.5).length,
    };
    return { ...response, data: { count, results: list, stats } };
  }

  /**
   * GET /api/v1/accounts/users/
   *
   * Admin-only list of every account on the system. Supports
   * `?search=` (icontains over email / username / first_name / last_name).
   */
  static async getUsers(
    options: { search?: string; reload?: boolean } = {}
  ): Promise<ApiResponse<{ count: number; results: AdminUser[]; stats: AdminUserStats }>> {
    const response = await apiClient.get<
      AdminUser[] | Paginated<AdminUser> | { count: number; results: AdminUser[]; stats: AdminUserStats }
    >(`/accounts/users/${qs({ search: options.search }, options.reload)}`, ADMIN_SCOPE);
    const raw = response.data;
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'results' in raw && 'stats' in raw) {
      const env = raw as { count: number; results: AdminUser[]; stats: AdminUserStats };
      return { ...response, data: { count: env.count, results: env.results, stats: env.stats } };
    }
    const list = unwrapList<AdminUser>(raw);
    const count = !Array.isArray(raw) ? (raw as Paginated<AdminUser>)?.count ?? list.length : list.length;
    const stats: AdminUserStats = {
      total: count,
      active: list.filter((u) => u.is_active).length,
      staff: list.filter((u) => u.is_staff || u.is_superuser).length,
    };
    return { ...response, data: { count, results: list, stats } };
  }

  static async updateUserRole(
    userId: number,
    role: string
  ): Promise<ApiResponse<AdminUser>> {
    return apiClient.patch<AdminUser>(`/accounts/users/${userId}/`, { role }, ADMIN_SCOPE);
  }

  static async deactivateUser(userId: number): Promise<ApiResponse<AdminUser>> {
    return apiClient.patch<AdminUser>(
      `/accounts/users/${userId}/`,
      { is_active: false },
      ADMIN_SCOPE
    );
  }

  /**
   * GET /api/v1/feedback/
   *
   * Admin-only feedback feed. Backend joins to the parent `QueryLog`
   * so each row carries `query` / `response` text inline; the SPA
   * doesn't need a second fetch. Supports `?is_helpful=true|false`
   * and `?search=`.
   */
  static async getFeedback(
    options: { search?: string; isHelpful?: boolean; reload?: boolean } = {}
  ): Promise<ApiResponse<{ count: number; results: FeedbackEntry[]; stats: FeedbackAdminStats }>> {
    const response = await apiClient.get<
      | FeedbackEntry[]
      | Paginated<FeedbackEntry>
      | { count: number; results: FeedbackEntry[]; stats: FeedbackAdminStats }
    >(
      `/feedback/${qs(
        {
          search: options.search,
          is_helpful: options.isHelpful === undefined ? undefined : options.isHelpful ? 'true' : 'false',
        },
        options.reload
      )}`,
      ADMIN_SCOPE
    );
    const raw = response.data;
    if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'results' in raw && 'stats' in raw) {
      const env = raw as { count: number; results: FeedbackEntry[]; stats: FeedbackAdminStats };
      return { ...response, data: { count: env.count, results: env.results, stats: env.stats } };
    }
    const list = unwrapList<FeedbackEntry>(raw);
    const count = !Array.isArray(raw) ? (raw as Paginated<FeedbackEntry>)?.count ?? list.length : list.length;
    const stats: FeedbackAdminStats = {
      total: count,
      helpful: list.filter((e) => e.is_helpful ?? e.rating === 'up').length,
      unhelpful: list.filter((e) => !(e.is_helpful ?? e.rating === 'up')).length,
    };
    return { ...response, data: { count, results: list, stats } };
  }
}
