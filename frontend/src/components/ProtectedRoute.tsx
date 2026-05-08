/**
 * Protected Route Wrapper
 * Restricts access to authenticated users only
 * Optionally restricts to admin users (requireAdmin prop)
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
}

export const ProtectedRoute = ({
  children,
  requireAdmin = false,
  fallback,
  redirectTo = '/login',
  allowGuest = false,
}: ProtectedRouteProps) => {
  const { isAuthenticated, isAdmin, isLoading, isGuest } = useAuth();
  const location = useLocation();

  // Show loading state or fallback while checking auth
  if (isLoading) {
    return fallback || <div className="flex items-center justify-center p-8">Loading...</div>;
  }

  // Redirect unauthenticated users to login and preserve intended path.
  if (!isAuthenticated && !(allowGuest && isGuest)) {
    return <Navigate to={redirectTo} replace state={{ from: location.pathname }} />;
  }

  // Authenticated but unauthorized for this route.
  if (requireAdmin && !isAdmin) {
    return <Navigate to="/chat" replace />;
  }

  // Render protected content
  return <>{children}</>;
};
