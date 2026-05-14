// Re-export types from API modules for convenience
export type { User } from '@/lib/api/auth';
export type {
  ChatResponse,
  ChatSource,
  Conversation as ChatConversation,
  ConversationMessage,
  QueryFeedback,
} from '@/lib/api/chat';
export type {
  Document,
  AnalyticsStats,
  QueryLog,
  AdminUser,
  FeedbackEntry,
} from '@/lib/api/admin';

// Local UI types
export type UserRole = 'guest' | 'user' | 'admin';

/**
 * Message with UI metadata
 * Extends ConversationMessage with local UI state
 */
export interface UIMessage {
  id: number;
  content: string;
  sender: 'user' | 'assistant';
  created_at: string;
  metadata?: Record<string, any>;
  isLoading?: boolean;
  error?: string;
}

/**
 * Chat feedback UI state
 */
export interface ChatFeedbackState {
  queryLogId: number;
  isSubmitting: boolean;
  hasSubmitted: boolean;
  rating?: 'up' | 'down';
  comment?: string;
}
