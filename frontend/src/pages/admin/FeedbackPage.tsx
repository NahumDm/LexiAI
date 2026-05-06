import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { mockFeedback } from '@/data/mockData';
import { Star, ThumbsUp, ThumbsDown, TrendingUp } from 'lucide-react';
import { format } from 'date-fns';

export default function FeedbackPage() {
  const averageRating = mockFeedback.reduce((acc, fb) => acc + fb.rating, 0) / mockFeedback.length;
  const positiveCount = mockFeedback.filter(fb => fb.rating >= 4).length;
  const negativeCount = mockFeedback.filter(fb => fb.rating <= 2).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-serif font-bold text-foreground">Feedback</h1>
        <p className="text-muted-foreground mt-1">Review user ratings and comments on AI responses</p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Star className="h-5 w-5 text-secondary fill-secondary" />
              <span className="text-2xl font-bold">{averageRating.toFixed(1)}</span>
            </div>
            <p className="text-sm text-muted-foreground">Average Rating</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{mockFeedback.length}</div>
            <p className="text-sm text-muted-foreground">Total Reviews</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <ThumbsUp className="h-5 w-5 text-success" />
              <span className="text-2xl font-bold text-success">{positiveCount}</span>
            </div>
            <p className="text-sm text-muted-foreground">Positive (4-5 ★)</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <ThumbsDown className="h-5 w-5 text-destructive" />
              <span className="text-2xl font-bold text-destructive">{negativeCount}</span>
            </div>
            <p className="text-sm text-muted-foreground">Needs Improvement (1-2 ★)</p>
          </CardContent>
        </Card>
      </div>

      {/* Rating Distribution */}
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">Rating Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[5, 4, 3, 2, 1].map((rating) => {
              const count = mockFeedback.filter(fb => fb.rating === rating).length;
              const percentage = (count / mockFeedback.length) * 100;
              return (
                <div key={rating} className="flex items-center gap-3">
                  <div className="flex items-center gap-1 w-16">
                    <span className="text-sm font-medium">{rating}</span>
                    <Star className="h-4 w-4 text-secondary fill-secondary" />
                  </div>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-secondary transition-all"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <span className="text-sm text-muted-foreground w-12">{count}</span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Recent Feedback */}
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-lg">All Feedback</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {mockFeedback.map((fb) => (
            <div key={fb.id} className="p-4 border rounded-lg">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium">{fb.userName}</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <Star
                          key={star}
                          className={`h-4 w-4 ${star <= fb.rating ? 'text-secondary fill-secondary' : 'text-muted'}`}
                        />
                      ))}
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground mb-2">
                    Query: "{fb.query}"
                  </p>
                  {fb.comment && (
                    <p className="text-sm italic bg-muted/50 p-2 rounded">
                      "{fb.comment}"
                    </p>
                  )}
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {format(fb.createdAt, 'MMM d, yyyy')}
                </span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
