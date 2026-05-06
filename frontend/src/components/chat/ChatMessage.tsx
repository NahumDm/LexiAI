import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import type { ConversationMessage, ChatSource } from '@/lib/api/chat';
import { Button } from '@/components/ui/button';
import { ThumbsUp, ThumbsDown, FileText, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface LegacyMessage {
  id: string | number;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date | string;
  citations?: Array<{ id: string | number; title?: string; section?: string; source?: string }>;
  confidence?: number;
  feedback?: { rating?: number };
}

interface ChatMessageProps {
  message: ConversationMessage | LegacyMessage;
  onFeedback?: (rating: number) => void;
}

export function ChatMessage({ message, onFeedback }: ChatMessageProps) {
  const { isAuthenticated, isGuest } = useAuth();

  // Support both legacy UI message shape and backend ConversationMessage shape
  const isNewShape = (message as any).sender !== undefined;
  const sender = isNewShape ? (message as ConversationMessage).sender : (message as LegacyMessage).role;
  const isUser = sender === 'user';

  const content = (message as any).content as string;
  const timestamp = isNewShape
    ? new Date((message as ConversationMessage).created_at)
    : new Date((message as LegacyMessage).timestamp as string);

  const confidence = isNewShape
    ? (message as ConversationMessage).metadata?.retrieval_confidence
    : (message as LegacyMessage).confidence;

  const citations: ChatSource[] | undefined = isNewShape
    ? (message as ConversationMessage).metadata?.sources
    : (message as LegacyMessage).citations as any;

  const [showCitations, setShowCitations] = useState(false);
  const [feedback, setFeedback] = useState<number | null>((message as any).feedback?.rating || null);

  const handleFeedback = (rating: number) => {
    if (!isAuthenticated) return;
    setFeedback(rating);
    onFeedback?.(rating);
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 animate-slide-up`}>
      <div className={`max-w-[85%] ${isUser ? 'order-1' : ''}`}>
        {/* Message bubble */}
        <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        </div>

        {/* AI Response extras */}
        {!isUser && (
          <div className="mt-2 space-y-2">
                {/* Confidence indicator */}
                {confidence !== undefined && confidence !== null && (
                  <div className="confidence-indicator">
                    <Sparkles className="h-3 w-3" />
                    <span>Confidence: {Math.round(confidence * 100)}%</span>
                  </div>
                )}

            {/* Citations */}
            {citations && citations.length > 0 && (
              <div className="space-y-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-auto py-1 px-2 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setShowCitations(!showCitations)}
                >
                  <FileText className="h-3 w-3 mr-1" />
                  {citations.length} Source{citations.length > 1 ? 's' : ''}
                  {showCitations ? <ChevronUp className="h-3 w-3 ml-1" /> : <ChevronDown className="h-3 w-3 ml-1" />}
                </Button>

                {showCitations && (
                  <div className="space-y-2 pl-2 border-l-2 border-secondary/30">
                    {citations.map((citation, i) => (
                      <CitationCard key={citation.chunk_id ?? i} citation={citation as any} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Feedback */}
            <div className="flex items-center gap-2">
              {isAuthenticated ? (
                <>
                  <span className="text-xs text-muted-foreground">Was this helpful?</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className={`h-7 w-7 p-0 ${feedback === 1 ? 'text-success' : 'text-muted-foreground'}`}
                    onClick={() => handleFeedback(1)}
                  >
                    <ThumbsUp className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className={`h-7 w-7 p-0 ${feedback === -1 ? 'text-destructive' : 'text-muted-foreground'}`}
                    onClick={() => handleFeedback(-1)}
                  >
                    <ThumbsDown className="h-4 w-4" />
                  </Button>
                </>
              ) : (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="text-xs text-muted-foreground cursor-help">
                      Login to provide feedback
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Sign in to rate responses and help improve our AI</p>
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
          </div>
        )}

        {/* Timestamp */}
        <p className={`text-[10px] text-muted-foreground mt-1 ${isUser ? 'text-right' : ''}`}>
          {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  );
}

function CitationCard({ citation }: { citation: Partial<ChatSource> }) {
  return (
    <div className="p-3 bg-citation-bg rounded-lg border border-secondary/20">
      <div className="flex items-start gap-2">
        <FileText className="h-4 w-4 text-secondary mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-medium text-foreground">{citation.document_title || 'Source'}</p>
          {citation.excerpt && <p className="text-xs text-muted-foreground truncate">{citation.excerpt}</p>}
          {citation.relevance !== undefined && (
            <p className="text-xs text-secondary mt-1">Relevance: {(citation.relevance * 100).toFixed(0)}%</p>
          )}
        </div>
      </div>
    </div>
  );
}
