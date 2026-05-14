import React from 'react';
import { Document } from '@/lib/api/admin';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { FileText, MoreVertical, Trash2, RefreshCw, ExternalLink } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { format } from 'date-fns';

interface DocumentTableProps {
  documents: Document[];
  onProcess?: (id: number) => void;
  onDelete?: (id: number) => void;
}

/**
 * Map the backend `Document.status` enum
 * (`uploaded | processing | ready | archived`) to a Badge variant + label.
 * Unknown statuses fall back to an outline badge with the raw status text so
 * we never crash on an in-flight schema change.
 */
const STATUS_PRESENTATION: Record<
  string,
  { variant: 'default' | 'secondary' | 'outline' | 'destructive'; label: string }
> = {
  uploaded: { variant: 'outline', label: 'Uploaded' },
  pending: { variant: 'outline', label: 'Pending' },
  processing: { variant: 'secondary', label: 'Processing' },
  ready: { variant: 'default', label: 'Ready' },
  archived: { variant: 'outline', label: 'Archived' },
  // legacy/mock statuses kept for graceful migration off mockData
  raw: { variant: 'outline', label: 'Raw' },
  ocr_processed: { variant: 'secondary', label: 'OCR Done' },
  indexed: { variant: 'default', label: 'Indexed' },
  failed: { variant: 'destructive', label: 'Failed' },
};

const formatFileSize = (bytes: number | null | undefined): string => {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const safeFormatDate = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return format(date, 'MMM d, yyyy');
};

export function DocumentTable({ documents, onProcess, onDelete }: DocumentTableProps) {
  const getStatusBadge = (status: Document['status']) => {
    const presentation = STATUS_PRESENTATION[status] || { variant: 'outline' as const, label: status };
    return <Badge variant={presentation.variant}>{presentation.label}</Badge>;
  };

  return (
    <div className="border rounded-lg overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead>Document</TableHead>
            <TableHead>Pages</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Uploaded</TableHead>
            <TableHead className="w-[50px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                No documents uploaded yet
              </TableCell>
            </TableRow>
          ) : (
            documents.map((doc) => {
              const canReprocess = doc.status !== 'ready' && doc.status !== 'archived';
              return (
                <TableRow key={doc.id}>
                  <TableCell>
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-4 w-4 text-primary shrink-0" />
                      <span className="font-medium truncate" title={doc.title}>
                        {doc.title}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{doc.page_count ?? '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{formatFileSize(doc.file_size)}</TableCell>
                  <TableCell>{getStatusBadge(doc.status)}</TableCell>
                  <TableCell className="text-muted-foreground">{safeFormatDate(doc.created_at)}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {doc.source_file_url && (
                          <DropdownMenuItem asChild>
                            <a href={doc.source_file_url} target="_blank" rel="noopener noreferrer">
                              <ExternalLink className="h-4 w-4 mr-2" />
                              Open file
                            </a>
                          </DropdownMenuItem>
                        )}
                        {canReprocess && onProcess && (
                          <DropdownMenuItem onClick={() => onProcess(doc.id)}>
                            <RefreshCw className="h-4 w-4 mr-2" />
                            Reprocess
                          </DropdownMenuItem>
                        )}
                        {onDelete && (
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => onDelete(doc.id)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Delete
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
    </div>
  );
}
