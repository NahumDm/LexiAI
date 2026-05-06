/**
 * Protected Route Wrapper
 * Restricts access to authenticated users only
 * Optionally restricts to admin users (requireAdmin prop)
 */

'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
  fallback?: React.ReactNode;
}

export const ProtectedRoute = ({ children, requireAdmin = false, fallback }: ProtectedRouteProps) => {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated) {
        // Redirect to login
        router.push('/login');
      } else if (requireAdmin && !isAdmin) {
        // Redirect to unauthorized or back to chat
        router.push('/chat');
      }
    }
  }, [isAuthenticated, isAdmin, isLoading, requireAdmin, router]);

  // Show loading state or fallback while checking auth
  if (isLoading) {
    return fallback || <div className="flex items-center justify-center p-8">Loading...</div>;
  }

  // Not authenticated and not admin (when required)
  if (!isAuthenticated || (requireAdmin && !isAdmin)) {
    return fallback || <div className="flex items-center justify-center p-8">Access Denied</div>;
  }

  // Render protected content
  return <>{children}</>;
};
