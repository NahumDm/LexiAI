/**
 * ChatMessage Component
 * Renders individual chat messages with:
 * - User/Assistant distinction
 * - Source citations
 * - Confidence score
 * - Low-confidence warnings
 * - Feedback buttons (thumbs up/down)
 */

'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { AlertCircle, ThumbsUp, ThumbsDown, ExternalLink, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ConversationMessage, ChatSource } from '@/lib/api/chat';
import { useChat } from '@/contexts/ChatContext';

interface ChatMessageProps {
  message: ConversationMessage & {
    metadata?: {
      sources?: ChatSource[];
      retrieval_confidence?: number;
      warnings?: string[];
      model?: string;
      tokens?: { prompt: number; completion: number; total: number };
    };
  };
  isLoading?: boolean;
}

export const ChatMessage = ({ message, isLoading }: ChatMessageProps) => {
  const { submitFeedback } = useChat();
  const [feedbackRating, setFeedbackRating] = useState<'up' | 'down' | null>(null);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  const isAssistant = message.sender === 'assistant';
  const metadata = message.metadata || {};
  const sources = metadata.sources || [];
  const confidence = metadata.retrieval_confidence;
  const warnings = metadata.warnings || [];
  const hasLowConfidence = confidence !== undefined && confidence < 0.5;

  const handleSubmitFeedback = async () => {
    if (!feedbackRating) return;

    setIsSubmittingFeedback(true);
    try {
      // The message ID should be the query_log_id from the backend
      // For now, we'll use the message ID as a placeholder
      await submitFeedback(message.id, feedbackRating, feedbackComment);
      setFeedbackRating(null);
      setFeedbackComment('');
      setShowFeedbackDialog(false);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  return (
    <div
      className={cn('flex gap-3 mb-6', {
        'justify-end': !isAssistant,
      })}
    >
      {/* Avatar or indicator */}
      <div
        className={cn('flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center', {
          'bg-blue-500 text-white': isAssistant,
          'bg-gray-200': !isAssistant,
        })}
      >
        {isAssistant ? 'AI' : 'U'}
      </div>

      {/* Message body */}
      <div className={cn('max-w-2xl', { 'order-2': !isAssistant })}>
        {/* Main message */}
        <div
          className={cn('rounded-lg p-4', {
            'bg-gray-100 text-gray-900': !isAssistant,
            'bg-blue-50 border border-blue-200': isAssistant,
          })}
        >
          {isLoading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Generating response...</span>
            </div>
          ) : (
            <p className="whitespace-pre-wrap">{message.content}</p>
          )}
        </div>

        {/* Metadata for assistant messages */}
        {isAssistant && !isLoading && (
          <div className="mt-3 space-y-3">
            {/* Confidence & Model Info */}
            <div className="flex items-center gap-2 flex-wrap">
              {confidence !== undefined && (
                <>
                  <Badge
                    variant={hasLowConfidence ? 'destructive' : 'default'}
                    className="text-xs"
                  >
                    Confidence: {(confidence * 100).toFixed(0)}%
                  </Badge>
                </>
              )}
              {metadata.model && (
                <Badge variant="outline" className="text-xs">
                  {metadata.model}
                </Badge>
              )}
            </div>

            {/* Warnings */}
            {warnings.length > 0 && (
              <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
                {warnings.map((warning, idx) => (
                  <div key={idx} className="flex gap-2 text-sm text-yellow-800">
                    <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                    <span>{warning}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Sources */}
            {sources.length > 0 && (
              <details className="text-sm">
                <summary className="cursor-pointer font-medium mb-2">
                  Sources ({sources.length})
                </summary>
                <div className="space-y-2 ml-2">
                  {sources.map((source, idx) => (
                    <div
                      key={idx}
                      className="bg-white border rounded p-3 space-y-1"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div>
                          <p className="font-medium text-sm">
                            {source.document_title || `Source ${idx + 1}`}
                          </p>
                          <p className="text-xs text-gray-600 line-clamp-2">
                            {source.excerpt}
                          </p>
                        </div>
                        <Badge
                          variant="outline"
                          className="text-xs flex-shrink-0"
                        >
                          {(source.relevance * 100).toFixed(0)}%
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* Feedback buttons */}
            <div className="flex gap-2 pt-2">
              <Button
                size="sm"
                variant={feedbackRating === 'up' ? 'default' : 'ghost'}
                onClick={() => {
                  setFeedbackRating('up');
                  setShowFeedbackDialog(true);
                }}
                disabled={feedbackRating !== null}
                className="gap-1"
              >
                <ThumbsUp className="h-4 w-4" />
                <span className="text-xs">Helpful</span>
              </Button>
              <Button
                size="sm"
                variant={feedbackRating === 'down' ? 'destructive' : 'ghost'}
                onClick={() => {
                  setFeedbackRating('down');
                  setShowFeedbackDialog(true);
                }}
                disabled={feedbackRating !== null}
                className="gap-1"
              >
                <ThumbsDown className="h-4 w-4" />
                <span className="text-xs">Not helpful</span>
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Feedback Dialog */}
      {feedbackRating && (
        <Dialog open={showFeedbackDialog} onOpenChange={setShowFeedbackDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Provide Feedback</DialogTitle>
              <DialogDescription>
                Thank you for rating this response. You can add an optional comment.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">Comment (optional)</label>
                <Textarea
                  value={feedbackComment}
                  onChange={e => setFeedbackComment(e.target.value)}
                  placeholder="What could be improved?"
                  rows={4}
                  maxLength={500}
                />
                <p className="text-xs text-gray-500 mt-1">
                  {feedbackComment.length}/500
                </p>
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowFeedbackDialog(false);
                    setFeedbackRating(null);
                  }}
                  disabled={isSubmittingFeedback}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleSubmitFeedback}
                  disabled={isSubmittingFeedback}
                >
                  {isSubmittingFeedback ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    'Submit Feedback'\n                  )}\n                </Button>\n              </div>\n            </div>\n          </DialogContent>\n        </Dialog>\n      )}\n    </div>\n  );\n};\n