import React from 'react';
import { StatCard } from '@/components/admin/StatCard';
import { mockAdminStats, mockDocuments, mockFeedback } from '@/data/mockData';
import { FileText, Users, MessageSquare, Star, CheckCircle, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export default function AdminDashboard() {
  const processedPercentage = (mockAdminStats.documentsProcessed / mockAdminStats.totalDocuments) * 100;
  const indexedPercentage = (mockAdminStats.documentsIndexed / mockAdminStats.totalDocuments) * 100;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-serif font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground mt-1">Overview of LexiTax AI system status</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Documents"
          value={mockAdminStats.totalDocuments}
          subtitle={`${mockAdminStats.documentsIndexed} indexed`}
          icon={FileText}
          trend={{ value: 12, isPositive: true }}
        />
        <StatCard
          title="Registered Users"
          value={mockAdminStats.totalUsers}
          icon={Users}
          trend={{ value: 8, isPositive: true }}
        />
        <StatCard
          title="Total Queries"
          value={mockAdminStats.totalQueries.toLocaleString()}
          subtitle="This month"
          icon={MessageSquare}
          trend={{ value: 23, isPositive: true }}
        />
        <StatCard
          title="Average Rating"
          value={mockAdminStats.averageRating.toFixed(1)}
          subtitle="Out of 5.0"
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
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-muted-foreground">OCR Processed</span>
                <span className="font-medium">{mockAdminStats.documentsProcessed}/{mockAdminStats.totalDocuments}</span>
              </div>
              <Progress value={processedPercentage} className="h-2" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-muted-foreground">Indexed</span>
                <span className="font-medium">{mockAdminStats.documentsIndexed}/{mockAdminStats.totalDocuments}</span>
              </div>
              <Progress value={indexedPercentage} className="h-2" />
            </div>

            <div className="pt-4 border-t space-y-2">
              <h4 className="font-medium text-sm">Recent Documents</h4>
              {mockDocuments.slice(0, 3).map((doc) => (
                <div key={doc.id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="truncate max-w-[200px]">{doc.name}</span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    doc.status === 'indexed' ? 'bg-success/10 text-success' :
                    doc.status === 'ocr_processed' ? 'bg-warning/10 text-warning' :
                    'bg-muted text-muted-foreground'
                  }`}>
                    {doc.status === 'indexed' ? 'Indexed' : doc.status === 'ocr_processed' ? 'Processing' : 'Raw'}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Recent Feedback */}
        <Card>
          <CardHeader>
            <CardTitle className="font-serif text-lg">Recent Feedback</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {mockFeedback.slice(0, 4).map((fb) => (
              <div key={fb.id} className="flex items-start gap-3 pb-3 border-b last:border-0">
                <div className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${
                  fb.rating >= 4 ? 'bg-success/10' : fb.rating >= 3 ? 'bg-warning/10' : 'bg-destructive/10'
                }`}>
                  <Star className={`h-4 w-4 ${
                    fb.rating >= 4 ? 'text-success' : fb.rating >= 3 ? 'text-warning' : 'text-destructive'
                  }`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-sm">{fb.userName}</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <Star
                          key={star}
                          className={`h-3 w-3 ${star <= fb.rating ? 'text-secondary fill-secondary' : 'text-muted'}`}
                        />
                      ))}
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground truncate">{fb.query}</p>
                  {fb.comment && (
                    <p className="text-xs text-muted-foreground mt-1 italic">"{fb.comment}"</p>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* System Status */}
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
                <p className="text-xs text-muted-foreground">5 pending</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
