import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { RefreshCw, CheckCircle, AlertCircle, Info, XCircle } from 'lucide-react';

const mockLogs = [
  { id: 1, level: 'info', message: 'Document ingestion completed: CITA_2004.pdf', timestamp: '2024-12-15 14:32:05', source: 'Ingestion Pipeline' },
  { id: 2, level: 'success', message: 'Index updated successfully (47 documents)', timestamp: '2024-12-15 14:30:00', source: 'Search Index' },
  { id: 3, level: 'warning', message: 'OCR quality below threshold for page 45', timestamp: '2024-12-15 14:28:12', source: 'OCR Service' },
  { id: 4, level: 'info', message: 'User login: admin@lexitax.ai', timestamp: '2024-12-15 14:25:00', source: 'Auth Service' },
  { id: 5, level: 'error', message: 'Failed to process document: corrupted PDF', timestamp: '2024-12-15 14:20:33', source: 'Ingestion Pipeline' },
  { id: 6, level: 'info', message: 'AI query processed in 1.2s', timestamp: '2024-12-15 14:18:00', source: 'AI Service' },
  { id: 7, level: 'success', message: 'Daily backup completed', timestamp: '2024-12-15 03:00:00', source: 'System' },
  { id: 8, level: 'info', message: 'Cache cleared successfully', timestamp: '2024-12-15 02:00:00', source: 'System' },
];

export default function LogsPage() {
  const getLogIcon = (level: string) => {
    switch (level) {
      case 'success': return <CheckCircle className="h-4 w-4 text-success" />;
      case 'warning': return <AlertCircle className="h-4 w-4 text-warning" />;
      case 'error': return <XCircle className="h-4 w-4 text-destructive" />;
      default: return <Info className="h-4 w-4 text-primary" />;
    }
  };

  const getLogBadge = (level: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      success: 'default',
      warning: 'secondary',
      error: 'destructive',
      info: 'outline',
    };
    return <Badge variant={variants[level] || 'outline'}>{level}</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground">System Logs</h1>
          <p className="text-muted-foreground mt-1">Monitor system activity and errors</p>
        </div>
        <Button variant="outline">
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* System Health */}
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
            <div className="text-2xl font-bold">99.9%</div>
            <p className="text-sm text-muted-foreground">Uptime (30 days)</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">1.2s</div>
            <p className="text-sm text-muted-foreground">Avg Response Time</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-destructive">3</div>
            <p className="text-sm text-muted-foreground">Errors (24h)</p>
          </CardContent>
        </Card>
      </div>

      {/* Log Entries */}
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px]">
            <div className="space-y-3">
              {mockLogs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-start gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className="mt-0.5">{getLogIcon(log.level)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {getLogBadge(log.level)}
                      <span className="text-xs text-muted-foreground">{log.source}</span>
                    </div>
                    <p className="text-sm mt-1">{log.message}</p>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {log.timestamp}
                  </span>
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
