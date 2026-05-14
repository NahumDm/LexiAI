import React from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { AdminSidebar } from '@/components/admin/AdminSidebar';
import { useAuth } from '@/contexts/AuthContext';

export default function AdminLayout() {
  const { isAdmin, user, isLoading } = useAuth();

  if (isLoading) {
    return <div className="flex items-center justify-center p-8">Loading...</div>;
  }

  // Anyone hitting /admin/* without a session goes through the dedicated
  // admin login (NOT the user `/login`). This keeps the admin flow
  // self-contained — a non-staff user who lands here is invited to switch
  // accounts on the admin page rather than being silently redirected into
  // the user app.
  if (!user) {
    return <Navigate to="/admin-login" replace />;
  }

  if (!isAdmin) {
    return <Navigate to="/admin-login" replace />;
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
