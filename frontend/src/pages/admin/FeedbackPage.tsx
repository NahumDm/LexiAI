/**
 * Admin → Feedback
 *
 * Live feedback feed. Sources data from TWO endpoints, both real:
 *   - `AdminAPI.getFeedback()` → GET /api/v1/feedback/ (admin-only).
 *     Returns each row with the joined `query` and `response` text inline,
 *     plus an `is_helpful` boolean (mapped from `rating`).
 *   - `AdminAPI.getAnalytics(30)` → aggregate helpful / not-helpful counts
 *     used for the top stat cards. Kept server-side so the percentage
 *     stays correct even if the per-row feed is capped (see backend
 *     AdminFeedbackListView).
 *
 * Refresh forces both calls; a 30s auto-refresh interval keeps the table
 * live while the tab is visible.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertCircle,
  Loader2,
  RefreshCw,
  Star,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { AdminAPI, type FeedbackEntry } from '@/lib/api/admin';
import { useAdminAutoRefresh } from '@/hooks/use-admin-auto-refresh';
import { format, formatDistanceToNow } from 'date-fns';

const formatTimestamp = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return formatDistanceToNow(date, { addSuffix: true });
};

const formatAbsoluteTimestamp = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return format(date, 'PPpp');
};

export default function FeedbackPage() {
  const [feedback, setFeedback] = useState<FeedbackEntry[]>([]);
  const [feedbackStats, setFeedbackStats] = useState({ total: 0, helpful: 0, unhelpful: 0 });
  const [feedbackEndpointMissing, setFeedbackEndpointMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    setError(null);
    setFeedbackEndpointMissing(false);

    const feedbackResponse = await AdminAPI.getFeedback({ reload: mode === 'refresh' });

    if (feedbackResponse.data) {
      setFeedback(feedbackResponse.data.results);
      setFeedbackStats(feedbackResponse.data.stats);
    } else if (feedbackResponse.status === 404) {
      setFeedbackEndpointMissing(true);
      setFeedback([]);
    } else if (feedbackResponse.status !== 200) {
      setError(feedbackResponse.error || 'Could not load feedback.');
    }

    setIsLoading(false);
    setIsRefreshing(false);
  }, []);

  useEffect(() => {
    fetchData('initial');
  }, [fetchData]);

  useAdminAutoRefresh(
    () => fetchData('refresh'),
    { enabled: !isRefreshing && !feedbackEndpointMissing },
  );

  // Aggregate stat-card values prefer the new top-level fields and fall
  // back to the legacy nested `feedback_breakdown` shape — both are
  // emitted by the backend, but downstream renames could drop one.
  const helpful = feedbackStats.helpful;
  const notHelpful = feedbackStats.unhelpful;
  const total = feedbackStats.total;
  const helpfulnessPct = total === 0 ? 0 : Math.round((helpful / total) * 100);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground">Feedback</h1>
          <p className="text-muted-foreground mt-1">
            Helpfulness ratings users have submitted on AI responses
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => fetchData('refresh')}
          disabled={isLoading || isRefreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading || isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {feedbackEndpointMissing && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Per-entry feedback endpoint (<code>GET /api/v1/feedback/</code>) is not
            reachable right now. Stat cards and the timeline will populate once it
            is available.
          </AlertDescription>
        </Alert>
      )}

      {error && !feedbackEndpointMissing && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Star className="h-5 w-5 text-secondary fill-secondary" />
              <span className="text-2xl font-bold">
                {total === 0 ? '—' : `${helpfulnessPct}%`}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">Helpful Ratio</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{total}</div>
            <p className="text-sm text-muted-foreground">Total Ratings</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <ThumbsUp className="h-5 w-5 text-success" />
              <span className="text-2xl font-bold text-success">{helpful}</span>
            </div>
            <p className="text-sm text-muted-foreground">Helpful</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <ThumbsDown className="h-5 w-5 text-destructive" />
              <span className="text-2xl font-bold text-destructive">{notHelpful}</span>
            </div>
            <p className="text-sm text-muted-foreground">Not Helpful</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Helpfulness Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          {total === 0 ? (
            <p className="text-sm text-muted-foreground">No ratings recorded yet.</p>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 w-28">
                  <ThumbsUp className="h-4 w-4 text-success" />
                  <span className="text-sm font-medium">Helpful</span>
                </div>
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-success transition-all"
                    style={{ width: `${(helpful / total) * 100}%` }}
                  />
                </div>
                <span className="text-sm text-muted-foreground w-12 text-right">{helpful}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 w-28">
                  <ThumbsDown className="h-4 w-4 text-destructive" />
                  <span className="text-sm font-medium">Not helpful</span>
                </div>
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-destructive transition-all"
                    style={{ width: `${(notHelpful / total) * 100}%` }}
                  />
                </div>
                <span className="text-sm text-muted-foreground w-12 text-right">{notHelpful}</span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Recent Feedback</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Loading feedback…
            </div>
          ) : feedback.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">
              {feedbackEndpointMissing
                ? 'Per-entry feedback will be displayed here once the backend endpoint is available.'
                : 'No feedback entries yet.'}
            </p>
          ) : (
            feedback.map((entry) => {
              const isHelpful = entry.is_helpful ?? entry.rating === 'up';
              const queryText = entry.query ?? entry.query_text;
              const responseText = entry.response;
              return (
                <div key={entry.id} className="p-4 border rounded-lg">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="font-medium">
                          {entry.user_email || `User #${entry.user ?? entry.id}`}
                        </span>
                        <Badge variant={isHelpful ? 'default' : 'destructive'}>
                          {isHelpful ? (
                            <>
                              <ThumbsUp className="h-3 w-3 mr-1" />
                              Helpful
                            </>
                          ) : (
                            <>
                              <ThumbsDown className="h-3 w-3 mr-1" />
                              Not helpful
                            </>
                          )}
                        </Badge>
                      </div>
                      {queryText && (
                        <p className="text-sm text-muted-foreground mb-2">Query: "{queryText}"</p>
                      )}
                      {responseText && (
                        <p className="text-xs text-muted-foreground/80 mb-2 line-clamp-2">
                          Response: {responseText}
                        </p>
                      )}
                      {entry.comment && (
                        <p className="text-sm italic bg-muted/50 p-2 rounded">"{entry.comment}"</p>
                      )}
                    </div>
                    <span
                      className="text-xs text-muted-foreground whitespace-nowrap"
                      title={formatAbsoluteTimestamp(entry.created_at)}
                    >
                      {formatTimestamp(entry.created_at)}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
