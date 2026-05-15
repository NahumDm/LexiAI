/**
 * Protected Route Wrapper
 *
 * Gates routes by authentication and, optionally, by Django admin status.
 *
 * `requireAdmin` is true iff the user has `is_staff` or `is_superuser` on the
 * backend (see `AuthContext.isAdmin`). The SPA admin dashboards are a CONVENIENCE
 * UI for staff users — the canonical model-CRUD admin still lives at Django's
 * `/admin/`. Backend endpoints are independently protected with DRF's
 * `IsAdminUser`, so this guard is UI-only.
 */

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
  fallback?: React.ReactNode;
  redirectTo?: string;
  allowGuest?: boolean;
  /**
   * Where to send a logged-in NON-admin who hits an admin-gated route. We
   * default to `/admin/login` so the admin flow stays self-contained: a user
   * who reaches an admin URL by mistake is offered the dedicated admin sign-in
   * (where they can switch accounts) rather than being silently bounced to
   * `/chat`. Set to `/chat` to preserve the legacy behaviour.
   */
  adminRedirectTo?: string;
}

export const ProtectedRoute = ({
  children,
  requireAdmin = false,
  fallback,
  redirectTo = '/login',
  allowGuest = false,
  adminRedirectTo = '/admin/login',
}: ProtectedRouteProps) => {
  const { isAuthenticated, isAdminAuthenticated, isLoading, isGuest } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return fallback || <div className="flex items-center justify-center p-8">Loading...</div>;
  }

  // For ADMIN-gated routes, an unauthenticated visitor should land on the
  // admin sign-in (not the user sign-in) so the flow doesn't loop them
  // through /login → /chat → "where's the admin link?". For regular routes
  // we keep the existing /login redirect untouched.
  if (!isAuthenticated && !(allowGuest && isGuest)) {
    const target = requireAdmin ? adminRedirectTo : redirectTo;
    return <Navigate to={target} replace state={{ from: location.pathname }} />;
  }

  if (requireAdmin && !isAdminAuthenticated) {
    return <Navigate to={adminRedirectTo} replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
};
