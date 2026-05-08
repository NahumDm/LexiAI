import React from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { AdminSidebar } from '@/components/admin/AdminSidebar';
import { useAuth } from '@/contexts/AuthContext';

export default function AdminLayout() {
  const { isAdmin, user, isLoading } = useAuth();

  if (isLoading) {
    return <div className="flex items-center justify-center p-8">Loading...</div>;
  }

  // Redirect non-admin users
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!isAdmin) {
    return <Navigate to="/chat" replace />;
  }

  return (
    <div className="flex h-screen bg-background">
      <AdminSidebar />
      <main className="flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
