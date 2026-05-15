import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

function RouteSpinner() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center p-8 text-muted-foreground">
      Loading…
    </div>
  );
}

/** `/login`: hide form while auth resolves; bounce guests and signed-in users away. */
export function UserLoginGate({ children }: { children: ReactNode }) {
  const { isAuthenticated, isGuest, isAdmin, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (isGuest) return <Navigate to="/chat" replace />;
  if (isAuthenticated) return <Navigate to={isAdmin ? '/admin' : '/chat'} replace />;
  return <>{children}</>;
}

/** `/admin/login`: same, plus non-staff sessions → home (not user chat). */
export function AdminLoginGate({ children }: { children: ReactNode }) {
  const { isAuthenticated, isGuest, isAdmin, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (isAuthenticated || isGuest) {
    return <Navigate to={isAdmin ? '/admin' : '/'} replace />;
  }
  return <>{children}</>;
}

/** Authenticated non-admin users and guests (for `/chat`). Admins → `/admin`. */
export function UserRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isGuest, isAdmin, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (!isAuthenticated && !isGuest) return <Navigate to="/login" replace />;
  if (isAdmin) return <Navigate to="/admin" replace />;
  return <>{children}</>;
}

/** Staff dashboard: signed-in staff/superuser only. */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isGuest, isAdmin, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (!isAuthenticated && !isGuest) return <Navigate to="/admin/login" replace />;
  if (!isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}
