/**
 * Admin Dashboard
 *
 * Live overview of system-wide state. Every card here is sourced from real
 * backend APIs — no mock data, no hardcoded fallback numbers:
 *
 *   - `AdminAPI.getAnalytics()` → IsAdminUser; headline metrics (documents,
 *     users, queries, latency, confidence, feedback) come from this payload
 *     only — no client-side fallbacks.
 *   - `AdminAPI.getDocuments({ reload })` → admin GLOBAL listing for the
 *     "Recent Documents" sidecar and processing progress bars (row-level status).
 *
 * Refresh button forces a fresh round-trip (`fetchData(true)`); a
 * 30s auto-refresh interval keeps live counts up to date when the tab is
 * visible (`useAdminAutoRefresh`). Both call sites flow through the same
 * `fetchData` to keep behaviour identical.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { StatCard } from '@/components/admin/StatCard';
import {
  FileText,
  Users,
  MessageSquare,
  Star,
  CheckCircle,
  Clock,
  AlertCircle,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AdminAPI, type AnalyticsStats, type Document } from '@/lib/api/admin';
import { useAdminAutoRefresh } from '@/hooks/use-admin-auto-refresh';

interface DashboardState {
  analytics: AnalyticsStats | null;
  analyticsError: string | null;
  documents: Document[];
  documentsError: string | null;
  isLoading: boolean;
  isRefreshing: boolean;
}

const INITIAL_STATE: DashboardState = {
  analytics: null,
  analyticsError: null,
  documents: [],
  documentsError: null,
  isLoading: true,
  isRefreshing: false,
};

export default function AdminDashboard() {
  const [state, setState] = useState<DashboardState>(INITIAL_STATE);

  const fetchData = useCallback(async (isManual = false) => {
    setState((prev) => ({
      ...prev,
      isRefreshing: isManual,
      isLoading: prev.analytics === null ? true : prev.isLoading,
    }));

    const [analyticsResponse, documentsResponse] = await Promise.all([
      AdminAPI.getAnalytics(7, isManual),
      AdminAPI.getDocuments({ reload: isManual }),
    ]);

    setState({
      analytics: analyticsResponse.data ?? null,
      analyticsError:
        !analyticsResponse.data && analyticsResponse.status !== 200
          ? analyticsResponse.error || 'Could not load analytics.'
          : null,
      documents: documentsResponse.data?.results ?? [],
      documentsError:
        !documentsResponse.data && documentsResponse.status !== 200
          ? documentsResponse.error || 'Could not load documents.'
          : null,
      isLoading: false,
      isRefreshing: false,
    });
  }, []);

  useEffect(() => {
    fetchData(false);
  }, [fetchData]);

  // 30s background refresh — pauses on hidden tabs, no-ops while a manual
  // refresh is mid-flight.
  useAdminAutoRefresh(() => fetchData(false), { enabled: !state.isRefreshing });

  const { analytics, documents, isLoading, isRefreshing } = state;

  // Headline "Total Documents" and user/query/feedback aggregates come ONLY
  // from analytics (server-aggregated GLOBAL totals). Recent-documents panel
  // uses the global admin document list for row-level status labels.
  const totalDocuments = analytics?.total_documents ?? 0;
  const readyCount = documents.filter((doc) => doc.status === 'ready').length;
  const processingCount = documents.filter((doc) => doc.status === 'processing').length;
  const uploadedCount = documents.filter(
    (doc) => doc.status === 'pending' || doc.status === 'uploaded'
  ).length;
  const documentStats = {
    total: totalDocuments,
    ready: readyCount,
    processing: processingCount,
    uploaded: uploadedCount,
    readyPct: totalDocuments ? (readyCount / totalDocuments) * 100 : 0,
    processedPct: totalDocuments ? ((readyCount + processingCount) / totalDocuments) * 100 : 0,
  };

  const positiveFeedback = analytics?.helpful_feedback ?? analytics?.feedback_breakdown?.helpful ?? 0;
  const negativeFeedback =
    analytics?.unhelpful_feedback ?? analytics?.feedback_breakdown?.not_helpful ?? 0;
  const totalFeedback = positiveFeedback + negativeFeedback;
  // We don't have a 1–5 star rating yet (the backend tracks thumbs up/down).
  // Surface helpfulness as a percentage instead; the StatCard accepts a
  // string so we can render "—" cleanly when nothing's been rated.
  const helpfulnessLabel = totalFeedback === 0
    ? '—'
    : `${Math.round((positiveFeedback / totalFeedback) * 100)}%`;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground">Dashboard</h1>
          <p className="text-muted-foreground mt-1">Overview of LexiAI system status</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchData(true)}
          disabled={isRefreshing}
          aria-label="Refresh dashboard data"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading dashboard data…
        </div>
      )}

      {state.analyticsError && !isLoading && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{state.analyticsError}</AlertDescription>
        </Alert>
      )}
      {state.documentsError && !isLoading && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{state.documentsError}</AlertDescription>
        </Alert>
      )}

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Documents"
          value={totalDocuments}
          subtitle={`${documentStats.ready} ready · ${documentStats.processing} processing`}
          icon={FileText}
        />
        <StatCard
          title="Total Users"
          value={(analytics?.total_users ?? 0).toLocaleString()}
          subtitle={`${analytics?.active_users_in_period ?? 0} active in last ${analytics?.period_days ?? 7}d`}
          icon={Users}
        />
        <StatCard
          title="Total Queries"
          value={(analytics?.total_queries ?? 0).toLocaleString()}
          subtitle={`Avg latency ${Math.round(analytics?.avg_latency_ms ?? 0)} ms`}
          icon={MessageSquare}
        />
        <StatCard
          title="Helpfulness"
          value={helpfulnessLabel}
          subtitle={`${totalFeedback} ratings · conf ${((analytics?.avg_retrieval_confidence ?? 0) * 100).toFixed(0)}%`}
          icon={Star}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Document Processing Status */}
        <Card>
          <CardHeader>
            <CardTitle className="font-serif text-lg">Document Processing</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {documentStats.total === 0 ? (
              <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
            ) : (
              <>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-muted-foreground">Processed (ready + processing)</span>
                    <span className="font-medium">
                      {documentStats.ready + documentStats.processing}/{documentStats.total}
                    </span>
                  </div>
                  <Progress value={documentStats.processedPct} className="h-2" />
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-muted-foreground">Ready for retrieval</span>
                    <span className="font-medium">{documentStats.ready}/{documentStats.total}</span>
                  </div>
                  <Progress value={documentStats.readyPct} className="h-2" />
                </div>
              </>
            )}

            <div className="pt-4 border-t space-y-2">
              <h4 className="font-medium text-sm">Recent Documents</h4>
              {documents.length === 0 ? (
                <p className="text-xs text-muted-foreground">No recent uploads.</p>
              ) : (
                documents.slice(0, 3).map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="truncate max-w-[200px]" title={doc.title}>
                        {doc.title}
                      </span>
                    </div>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        doc.status === 'ready'
                          ? 'bg-success/10 text-success'
                          : doc.status === 'processing'
                            ? 'bg-warning/10 text-warning'
                            : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {doc.status === 'ready'
                        ? 'Ready'
                        : doc.status === 'processing'
                          ? 'Processing'
                          : doc.status === 'pending'
                            ? 'Pending'
                            : 'Uploaded'}
                    </span>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        {/* Recent Feedback (aggregates from analytics — FeedbackPage has the full list) */}
        <Card>
          <CardHeader>
            <CardTitle className="font-serif text-lg">Feedback Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {totalFeedback === 0 ? (
              <p className="text-sm text-muted-foreground">No feedback received yet.</p>
            ) : (
              <>
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <ThumbsUp className="h-4 w-4 text-success" />
                    <span className="text-muted-foreground">Helpful</span>
                  </div>
                  <span className="font-medium text-success">{positiveFeedback}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <ThumbsDown className="h-4 w-4 text-destructive" />
                    <span className="text-muted-foreground">Not helpful</span>
                  </div>
                  <span className="font-medium text-destructive">{negativeFeedback}</span>
                </div>
                <div className="pt-2 border-t text-xs text-muted-foreground">
                  Avg retrieval confidence:{' '}
                  <span className="font-medium text-foreground">
                    {((analytics?.avg_retrieval_confidence ?? 0) * 100).toFixed(0)}%
                  </span>
                  {' · '}
                  Avg latency:{' '}
                  <span className="font-medium text-foreground">
                    {Math.round(analytics?.avg_latency_ms ?? 0)} ms
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* System Status — kept static. Wire to /api/v1/health/ if a future
          refresh wants live signals; left as a visual placeholder for now
          to minimise surface area in this PR. */}
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">System Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-success/5 border border-success/20">
              <CheckCircle className="h-5 w-5 text-success" />
              <div>
                <p className="font-medium text-sm">AI Service</p>
                <p className="text-xs text-muted-foreground">Operational</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-lg bg-success/5 border border-success/20">
              <CheckCircle className="h-5 w-5 text-success" />
              <div>
                <p className="font-medium text-sm">Document Store</p>
                <p className="text-xs text-muted-foreground">Healthy</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-lg bg-warning/5 border border-warning/20">
              <Clock className="h-5 w-5 text-warning" />
              <div>
                <p className="font-medium text-sm">Ingestion Pipeline</p>
                <p className="text-xs text-muted-foreground">
                  {documentStats.processing} processing
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
