import React from 'react';
import { Button } from '@/components/ui/button';
import { AlertCircle, LogIn } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface GuestBannerProps {
  onLoginClick: () => void;
}

export function GuestBanner({ onLoginClick }: GuestBannerProps) {
  const { guestQueriesRemaining } = useAuth();

  return (
    <div className="bg-warning/10 border-b border-warning/30 px-4 py-3">
      <div className="flex items-center justify-between gap-4 max-w-4xl mx-auto">
        <div className="flex items-center gap-2 text-sm">
          <AlertCircle className="h-4 w-4 text-warning" />
          <span className="text-warning font-medium">Guest Mode</span>
          <span className="text-muted-foreground">
            — {guestQueriesRemaining} {guestQueriesRemaining === 1 ? 'query' : 'queries'} remaining
          </span>
        </div>
        <Button variant="gold" size="sm" onClick={onLoginClick}>
          <LogIn className="h-4 w-4 mr-1" />
          Sign In
        </Button>
      </div>
    </div>
  );
}
