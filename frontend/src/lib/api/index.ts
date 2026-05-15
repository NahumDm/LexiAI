/**
 * API module exports
 */

export {
  apiClient,
  formatApiErrorMessage,
  type ApiResponse,
  type ApiError,
  type AuthScope,
} from './client';
export { AuthAPI, type User, type LoginRequest, type LoginResponse } from './auth';
export {
  ChatAPI,
  type ChatResponse,
  type ChatSource,
  type Conversation,
  type ConversationMessage,
  type QueryFeedback,
} from './chat';
export {
  AdminAPI,
  type Document,
  type AnalyticsStats,
  type QueryLog,
  type AdminUser,
  type FeedbackEntry,
} from './admin';
