/**
 * API module exports
 */

export { apiClient, type ApiResponse, type ApiError } from './client';
export { AuthAPI, type User, type LoginRequest, type LoginResponse } from './auth';
export {
  ChatAPI,
  type ChatResponse,
  type ChatSource,
  type Conversation,
  type ConversationMessage,
  type QueryFeedback,
} from './chat';
export { AdminAPI, type Document, type AnalyticsStats, type QueryLog } from './admin';
