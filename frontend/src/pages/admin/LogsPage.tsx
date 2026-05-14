/**
 * Admin → System Logs
 *
 * Live RAG query feed sourced from two endpoints:
 *   - `AdminAPI.getQueryLogs()` → GET /api/v1/ai/query-logs/ (IsAdminUser,
 *     ?search=, ?min_confidence=). Returns per-row data plus `stats`
 *     (global aggregates for the filtered queryset, including
 *     low_confidence_count for the stat card).
 *
 * Refresh forces a fresh round-trip; a 30s interval auto-refreshes the
 * feed while the tab is visible.
 *
 * "Low confidence" highlight: any row with `retrieval_confidence < 0.5`
 * is flagged with the destructive badge and a warning icon. This is the
 * boundary the spec calls out.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Clock,
  Info,
  Loader2,
  RefreshCw,
  Search,
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AdminAPI, type QueryLog } from '@/lib/api/admin';
import { useAdminAutoRefresh } from '@/hooks/use-admin-auto-refresh';
import { format, formatDistanceToNow } from 'date-fns';

// Confidence buckets mirror the spec: < 0.5 is flagged as LOW CONFIDENCE
// (red badge), >= 0.7 is treated as high confidence (success), and the
// 0.5–0.7 band is "medium" (informational). Keep `low` at 0.5 — that's
// the threshold the admin UX promises.
const LOW_CONFIDENCE = 0.5;
const HIGH_CONFIDENCE = 0.7;

const confidenceLevel = (confidence: number): 'high' | 'medium' | 'low' => {
  if (confidence >= HIGH_CONFIDENCE) return 'high';
  if (confidence >= LOW_CONFIDENCE) return 'medium';
  return 'low';
};

const SEARCH_DEBOUNCE_MS = 350;

const truncate = (value: string, maxLength = 140): string => {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength).trim()}…`;
};

export default function LogsPage() {
  const [logs, setLogs] = useState<QueryLog[]>([]);
  const [logStats, setLogStats] = useState({
    total_queries: 0,
    avg_latency_ms: 0,
    avg_retrieval_confidence: 0,
    low_confidence_count: 0,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logsEndpointMissing, setLogsEndpointMissing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const fetchData = useCallback(
    async (mode: 'initial' | 'refresh' = 'initial', search?: string) => {
      if (mode === 'initial') {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setLogsError(null);
      setLogsEndpointMissing(false);

      const logsResponse = await AdminAPI.getQueryLogs({
        search,
        reload: mode === 'refresh',
      });

      if (logsResponse.data) {
        setLogs(logsResponse.data.results);
        setLogStats(logsResponse.data.stats);
      } else if (logsResponse.status === 404) {
        setLogsEndpointMissing(true);
        setLogs([]);
      } else {
        setLogsError(logsResponse.error || 'Could not load query logs.');
      }

      setIsLoading(false);
      setIsRefreshing(false);
    },
    [],
  );

  useEffect(() => {
    fetchData(logs.length === 0 ? 'initial' : 'refresh', debouncedSearch || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, fetchData]);

  useAdminAutoRefresh(
    () => fetchData('refresh', debouncedSearch || undefined),
    { enabled: !isRefreshing && !logsEndpointMissing },
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground">Query Logs</h1>
          <p className="text-muted-foreground mt-1">Monitor AI query activity and retrieval quality</p>
        </div>
        <Button
          variant="outline"
          onClick={() => fetchData('refresh', debouncedSearch || undefined)}
          disabled={isLoading || isRefreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading || isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {logsEndpointMissing && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Per-query log endpoint (<code>GET /api/v1/ai/query-logs/</code>) is not
            available right now. Showing aggregate analytics below — the full
            timeline will return once the backend is reachable.
          </AlertDescription>
        </Alert>
      )}

      {logsError && !logsEndpointMissing && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{logsError}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-success" />
              <span className="font-medium">All Systems</span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">Operational</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">
              {logStats.total_queries.toLocaleString()}
            </div>
            <p className="text-sm text-muted-foreground">Queries (matching filters)</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">
              {Math.round(logStats.avg_latency_ms)} ms
            </div>
            <p className="text-sm text-muted-foreground">Avg Response Time</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-destructive">{logStats.low_confidence_count}</div>
            <p className="text-sm text-muted-foreground">
              Low confidence (&lt;{Math.round(LOW_CONFIDENCE * 100)}%)
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search query text or response..."
          className="pl-9"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          disabled={logsEndpointMissing}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px]">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground">
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Loading logs…
              </div>
            ) : logs.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground py-12">
                {logsEndpointMissing
                  ? 'No log entries to display until the query-logs endpoint is available.'
                  : 'No query activity recorded yet.'}
              </div>
            ) : (
              <div className="space-y-3">
                {logs.map((log) => {
                  const level = confidenceLevel(log.retrieval_confidence);
                  const isLow = level === 'low';
                  const icon = isLow ? (
                    <AlertTriangle className="h-4 w-4 text-destructive" />
                  ) : level === 'medium' ? (
                    <Info className="h-4 w-4 text-primary" />
                  ) : (
                    <CheckCircle className="h-4 w-4 text-success" />
                  );
                  const created = new Date(log.created_at);
                  return (
                    <div
                      key={log.id}
                      // Low-confidence rows get a destructive accent so admins
                      // can scan the timeline for retrieval problems without
                      // reading each line. The contrast also makes a screenshot
                      // self-documenting.
                      className={
                        'flex items-start gap-3 p-3 rounded-lg transition-colors ' +
                        (isLow
                          ? 'bg-destructive/5 border border-destructive/30 hover:bg-destructive/10'
                          : 'bg-muted/30 hover:bg-muted/50')
                      }
                    >
                      <div className="mt-0.5">{icon}</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge
                            variant={
                              level === 'high'
                                ? 'default'
                                : level === 'medium'
                                  ? 'secondary'
                                  : 'destructive'
                            }
                          >
                            {Math.round(log.retrieval_confidence * 100)}% confidence
                          </Badge>
                          {isLow && (
                            <Badge variant="destructive" className="uppercase tracking-wide">
                              Low confidence
                            </Badge>
                          )}
                          <Badge variant="outline">{log.llm_model}</Badge>
                          <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {log.latency_ms} ms
                          </span>
                          {log.user_email && (
                            <span className="text-xs text-muted-foreground">· {log.user_email}</span>
                          )}
                        </div>
                        <p className="text-sm mt-1 font-medium">
                          {truncate(log.query ?? log.query_text ?? '(no query)', 200)}
                        </p>
                        {(log.response ?? log.llm_response) && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {truncate(log.response ?? log.llm_response ?? '', 220)}
                          </p>
                        )}
                      </div>
                      <span
                        className="text-xs text-muted-foreground whitespace-nowrap"
                        title={Number.isNaN(created.getTime()) ? log.created_at : format(created, 'PPpp')}
                      >
                        {Number.isNaN(created.getTime())
                          ? log.created_at
                          : formatDistanceToNow(created, { addSuffix: true })}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
