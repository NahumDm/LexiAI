/**
 * Admin → Documents
 *
 * Lists EVERY document on the system (global, not owner-scoped) via
 * `AdminAPI.getDocuments({ search })` → `GET /api/v1/documents/admin/`.
 * Supports delete via `DELETE /api/v1/documents/<id>/` (still owner-scoped
 * on the backend — see admin.ts notes). Reprocess and upload UI paths
 * surface backend gaps explicitly rather than silently failing.
 *
 * Search:
 *   The input is debounced into a backend `?search=` filter (icontains
 *   over title + description). We DO NOT additionally re-filter the
 *   returned list in React — what the backend matches is exactly what
 *   the user sees.
 *
 * Refresh:
 *   The Refresh button calls `fetchDocuments('refresh')` which forces a
 *   network round-trip (no client caching). A 30s auto-refresh interval
 *   keeps the table live while the tab is visible.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DocumentTable } from '@/components/admin/DocumentTable';
import { Document, AdminAPI } from '@/lib/api/admin';
import {
  AlertCircle,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  Upload,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { useAdminAutoRefresh } from '@/hooks/use-admin-auto-refresh';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const SEARCH_DEBOUNCE_MS = 350;

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [stats, setStats] = useState({
    total: 0,
    ready: 0,
    processing: 0,
    uploaded: 0,
    failed: 0,
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { toast } = useToast();

  // Debounce search input → backend query. Without this, every keystroke
  // would hit the API (and re-render with stale-then-fresh data, causing
  // visible flicker for the admin).
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedSearch(searchQuery.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const fetchDocuments = useCallback(
    async (mode: 'initial' | 'refresh' = 'initial', search?: string) => {
      if (mode === 'initial') {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);

      const response = await AdminAPI.getDocuments({
        search,
        reload: mode === 'refresh',
      });
      if (response.data) {
        setDocuments(response.data.results);
        const s = response.data.stats;
        setStats({
          total: s.total,
          ready: s.ready,
          processing: s.processing,
          uploaded: s.pending,
          failed: s.failed,
        });
      } else {
        setError(response.error || 'Could not load documents.');
      }
      setIsLoading(false);
      setIsRefreshing(false);
    },
    []
  );

  useEffect(() => {
    // First fetch is "initial" (spinner); subsequent search-driven fetches
    // are "refresh" (no spinner, no layout shift). We never re-key the
    // visible table on every keystroke for the same reason.
    const mode = documents.length === 0 && !error ? 'initial' : 'refresh';
    fetchDocuments(mode, debouncedSearch || undefined);
    // We intentionally exclude `documents` and `error` — the effect re-runs
    // ONLY when the debounced search term changes (or on mount). The mode
    // computation above is a one-shot at fire time, not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, fetchDocuments]);

  // 30s background refresh — pauses when a delete confirmation is open
  // (don't change the list under the admin's finger).
  useAdminAutoRefresh(
    () => fetchDocuments('refresh', debouncedSearch || undefined),
    { enabled: !isRefreshing && pendingDeleteId === null && !isDeleting },
  );

  const filteredDocuments = documents;

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so the same file can be selected twice in a row.
    event.target.value = '';
    if (!file) return;

    toast({
      title: 'Uploading document…',
      description: file.name,
    });

    const response = await AdminAPI.uploadDocument(file, file.name);
    if (response.data) {
      toast({
        title: 'Upload complete',
        description: `${file.name} has been queued for ingestion.`,
      });
      fetchDocuments('refresh', debouncedSearch || undefined);
    } else {
      toast({
        title: 'Upload failed',
        description: response.error || 'The server rejected the upload.',
        variant: 'destructive',
      });
    }
  };

  const handleProcess = async (id: number) => {
    const response = await AdminAPI.ingestDocument(id);
    if (response.data) {
      toast({
        title: 'Reprocess queued',
        description: 'The document is being re-ingested.',
      });
      fetchDocuments('refresh', debouncedSearch || undefined);
      return;
    }

    // 404 here means the reingest endpoint isn't wired up yet — see
    // admin.ts TODO. Surface it as a non-destructive toast rather than a
    // generic "failed" error.
    if (response.status === 404) {
      toast({
        title: 'Reprocess not available',
        description:
          'The backend does not expose a reingest endpoint yet. New uploads still trigger embedding automatically.',
        variant: 'destructive',
      });
      return;
    }

    toast({
      title: 'Reprocess failed',
      description: response.error || 'Unknown error.',
      variant: 'destructive',
    });
  };

  const requestDelete = (id: number) => setPendingDeleteId(id);

  const confirmDelete = async () => {
    if (pendingDeleteId == null) return;
    const idToDelete = pendingDeleteId;
    setIsDeleting(true);
    const response = await AdminAPI.deleteDocumentAdmin(idToDelete, true);
    setIsDeleting(false);
    setPendingDeleteId(null);

    if (response.status >= 200 && response.status < 300) {
      setDocuments((prev) => prev.filter((doc) => doc.id !== idToDelete));
      setStats((prev) => ({
        ...prev,
        total: Math.max(0, prev.total - 1),
      }));
      void fetchDocuments('refresh', debouncedSearch || undefined);
      toast({
        title: 'Document deleted',
        description: 'The document has been removed.',
      });
    } else {
      toast({
        title: 'Delete failed',
        description: response.error || 'Could not delete the document.',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground">Documents</h1>
          <p className="text-muted-foreground mt-1">
            Manage tax law documents and the ingestion pipeline
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => fetchDocuments('refresh', debouncedSearch || undefined)}
            disabled={isRefreshing || isLoading}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button onClick={handleUploadClick}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Document
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.txt"
            className="hidden"
            onChange={handleFileSelected}
          />
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-sm text-muted-foreground">Total Documents</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-success">{stats.ready}</div>
            <p className="text-sm text-muted-foreground">Ready</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-warning">{stats.processing}</div>
            <p className="text-sm text-muted-foreground">Processing</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-muted-foreground">{stats.uploaded}</div>
            <p className="text-sm text-muted-foreground">Awaiting Ingestion</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button variant="outline" disabled>
          <Filter className="h-4 w-4 mr-2" />
          Filters
        </Button>
      </div>

      {isLoading ? (
        <div className="border rounded-lg p-12 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 mr-2 animate-spin" />
          Loading documents…
        </div>
      ) : (
        <DocumentTable
          documents={filteredDocuments}
          onProcess={handleProcess}
          onDelete={requestDelete}
        />
      )}

      <AlertDialog open={pendingDeleteId !== null} onOpenChange={(open) => !open && setPendingDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this document?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the document and its associated chunks /
              embeddings from the index. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                confirmDelete();
              }}
              disabled={isDeleting}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting…
                </>
              ) : (
                'Delete'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
