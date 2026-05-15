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
  const { isAuthenticated, isGuest, isAdminAuthenticated, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (isGuest) return <Navigate to="/chat" replace />;
  if (isAuthenticated) return <Navigate to="/chat" replace />;
  if (isAdminAuthenticated) return <Navigate to="/admin" replace />;
  return <>{children}</>;
}

/** `/admin/login`: only an admin-session redirects away; user JWT does not count. */
export function AdminLoginGate({ children }: { children: ReactNode }) {
  const { isAdminAuthenticated, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (isAdminAuthenticated) return <Navigate to="/admin" replace />;
  return <>{children}</>;
}

/** Authenticated non-admin users and guests (for `/chat`). */
export function UserRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isGuest, isAdminAuthenticated, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (!isAuthenticated && !isGuest) {
    if (isAdminAuthenticated) return <Navigate to="/login" replace />;
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/** Staff dashboard: requires admin storage session only. */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAdminAuthenticated, isLoading } = useAuth();

  if (isLoading) return <RouteSpinner />;
  if (!isAdminAuthenticated) return <Navigate to="/admin/login" replace />;
  return <>{children}</>;
}
