/**
 * Chat API module
 * Handles: conversations, chat queries, message history, feedback
 */

import { apiClient, ApiResponse } from './client';

export interface ChatSource {
  chunk_id: number;
  document_title: string | null;
  relevance: number;
  excerpt: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  model_used: string;
  tokens_used: {
    prompt: number;
    completion: number;
    total: number;
  };
  retrieval_confidence: number;
  warnings: string[];
}

export interface ChatQueryRequest {
  query: string;
  top_k?: number;
}

export interface ConversationMessage {
  id: number;
  sender: 'user' | 'assistant';
  content: string;
  metadata: Record<string, any>;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  document: number | null;
  document_title?: string;
  summary?: string;
  status: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueryFeedback {
  id?: number;
  rating: 'up' | 'down';
  comment?: string;
  created_at?: string;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

const unwrapListResponse = <T>(payload: T[] | PaginatedResponse<T> | null | undefined): T[] => {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray((payload as PaginatedResponse<T>).results)) {
    return (payload as PaginatedResponse<T>).results;
  }
  return [];
};

export class ChatAPI {
  /**
   * Get all conversations for current user
   */
  static async getConversations(): Promise<ApiResponse<Conversation[]>> {
    const response = await apiClient.get<Conversation[] | PaginatedResponse<Conversation>>('/conversations/');
    return {
      ...response,
      data: unwrapListResponse(response.data),
    };
  }

  /**
   * Get single conversation with messages
   */
  static async getConversation(id: number): Promise<ApiResponse<Conversation>> {
    return apiClient.get<Conversation>(`/conversations/${id}/`);
  }

  /**
   * Create new conversation
   */
  static async createConversation(data: {
    title: string;
    document?: number;
  }): Promise<ApiResponse<Conversation>> {
    return apiClient.post<Conversation>('/conversations/', data);
  }

  /**
   * Update conversation
   */
  static async updateConversation(
    id: number,
    data: Partial<Conversation>
  ): Promise<ApiResponse<Conversation>> {
    return apiClient.patch<Conversation>(`/conversations/${id}/`, data);
  }

  /**
   * Delete conversation
   */
  static async deleteConversation(id: number): Promise<ApiResponse<void>> {
    return apiClient.delete<void>(`/conversations/${id}/`);
  }

  /**
   * Get conversation messages
   */
  static async getMessages(
    conversationId: number,
    limit = 50
  ): Promise<ApiResponse<ConversationMessage[]>> {
    const response = await apiClient.get<ConversationMessage[] | PaginatedResponse<ConversationMessage>>(
      `/conversations/${conversationId}/messages/?limit=${limit}`
    );
    return {
      ...response,
      data: unwrapListResponse(response.data),
    };
  }

  /**
   * Send chat query and get AI response
   */
  static async sendQuery(
    conversationId: number,
    request: ChatQueryRequest
  ): Promise<ApiResponse<ChatResponse>> {
    return apiClient.post<ChatResponse>(`/chat/${conversationId}/ask/`, request);
  }

  /**
   * Submit feedback on a response
   */
  static async submitFeedback(
    queryLogId: number,
    feedback: QueryFeedback
  ): Promise<ApiResponse<QueryFeedback>> {
    return apiClient.post<QueryFeedback>(`/chat/feedback/${queryLogId}/`, feedback);
  }

  /**
   * Create a new message in conversation (user message)
   */
  static async createMessage(
    conversationId: number,
    content: string,
    metadata?: Record<string, any>
  ): Promise<ApiResponse<ConversationMessage>> {
    return apiClient.post<ConversationMessage>(
      `/conversations/${conversationId}/messages/`,
      {
        content,
        metadata: metadata || {},
      }
    );
  }
}
