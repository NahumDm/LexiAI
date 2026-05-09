/**
 * Chat Context & Provider
 * Manages conversation state, message history, and API interactions
 */

'use client';

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { ChatAPI, type ChatResponse, type Conversation } from '@/lib/api/chat';

export interface ChatContextType {
  currentConversation: Conversation | null;
  messages: any[]; // ConversationMessage[]
  isLoading: boolean;
  isSendingQuery: boolean;
  error: string | null;
  
  // Conversation management
  setCurrentConversation: (conversation: Conversation | null) => void;
  createConversation: (title: string, documentId?: number) => Promise<Conversation>;
  loadConversation: (id: number) => Promise<void>;
  deleteConversation: (id: number) => Promise<void>;
  
  // Message management — pass conversationId when React state is stale right after createConversation
  sendQuery: (query: string, topK?: number, conversationId?: number) => Promise<ChatResponse | null>;
  addMessage: (content: string, role: 'user' | 'assistant', metadata?: any) => void;
  clearMessages: () => void;
  
  // Feedback
  submitFeedback: (queryLogId: number, rating: 'up' | 'down', comment?: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider = ({ children }: { children: ReactNode }) => {
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSendingQuery, setIsSendingQuery] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSetCurrentConversation = useCallback((conversation: Conversation | null) => {
    setCurrentConversation(conversation);
    if (!conversation) {
      setMessages([]);
    }
  }, []);

  const handleCreateConversation = useCallback(async (title: string, documentId?: number) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await ChatAPI.createConversation({
        title,
        document: documentId,
      });

      if (!response.data) {
        throw new Error(response.error || 'Failed to create conversation');
      }

      setCurrentConversation(response.data);
      setMessages([]);
      return response.data;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to create conversation';
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleLoadConversation = useCallback(async (id: number) => {
    setIsLoading(true);
    setError(null);

    try {
      const convResponse = await ChatAPI.getConversation(id);
      if (!convResponse.data) {
        throw new Error('Failed to load conversation');
      }

      setCurrentConversation(convResponse.data);

      // Load messages
      const messagesResponse = await ChatAPI.getMessages(id);
      if (messagesResponse.data) {
        setMessages(messagesResponse.data);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load conversation';
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleDeleteConversation = useCallback(async (id: number) => {
    setError(null);

    try {
      await ChatAPI.deleteConversation(id);

      if (currentConversation?.id === id) {
        setCurrentConversation(null);
        setMessages([]);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to delete conversation';
      setError(errorMsg);
      throw err;
    }
  }, [currentConversation?.id]);

  const handleSendQuery = useCallback(
    async (query: string, topK = 5, conversationId?: number): Promise<ChatResponse | null> => {
      const targetId = conversationId ?? currentConversation?.id;
      if (!targetId) {
        setError('No conversation selected');
        return null;
      }

      setIsSendingQuery(true);
      setError(null);

      try {
        // Add user message optimistically
        const userMessage = {
          id: Date.now(),
          sender: 'user' as const,
          content: query,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, userMessage]);

        // Send query to backend
        const response = await ChatAPI.sendQuery(targetId, {
          query,
          top_k: topK,
        });

        const statusOk = typeof response.status === 'number' && response.status >= 200 && response.status < 300;
        if (!statusOk || !response.data || typeof response.data !== 'object' || typeof response.data.answer !== 'string') {
          throw new Error(response.error || 'Failed to get response');
        }

        // Add assistant message
        const assistantMessage = {
          id: Date.now() + 1,
          sender: 'assistant' as const,
          content: response.data.answer ?? '',
          created_at: new Date().toISOString(),
          metadata: {
            sources: response.data.sources,
            model: response.data.model_used,
            tokens: response.data.tokens_used,
            retrieval_confidence: response.data.retrieval_confidence,
            warnings: response.data.warnings,
            query_log_id: response.data.query_id ?? undefined,
          },
        };
        setMessages(prev => [...prev, assistantMessage]);

        return response.data;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Query failed';
        setError(errorMsg);

        // Remove optimistic user message on error
        setMessages(prev => prev.slice(0, -1));
        throw err;
      } finally {
        setIsSendingQuery(false);
      }
    },
    [currentConversation]
  );

  const handleAddMessage = useCallback((content: string, role: 'user' | 'assistant', metadata?: any) => {
    const message = {
      id: Date.now(),
      sender: role,
      content,
      created_at: new Date().toISOString(),
      metadata,
    };
    setMessages(prev => [...prev, message]);
  }, []);

  const handleClearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const handleSubmitFeedback = useCallback(
    async (queryLogId: number, rating: 'up' | 'down', comment?: string) => {
      setError(null);

      try {
        await ChatAPI.submitFeedback(queryLogId, {
          rating,
          comment,
        });
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to submit feedback';
        setError(errorMsg);
        throw err;
      }
    },
    []
  );

  const value: ChatContextType = {
    currentConversation,
    messages,
    isLoading,
    isSendingQuery,
    error,
    setCurrentConversation: handleSetCurrentConversation,
    createConversation: handleCreateConversation,
    loadConversation: handleLoadConversation,
    deleteConversation: handleDeleteConversation,
    sendQuery: handleSendQuery,
    addMessage: handleAddMessage,
    clearMessages: handleClearMessages,
    submitFeedback: handleSubmitFeedback,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

/**
 * Hook to use chat context
 */
export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used inside ChatProvider');
  }
  return context;
};
