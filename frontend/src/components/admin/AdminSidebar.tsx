import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Logo } from '@/components/icons/Logo';
import { Button } from '@/components/ui/button';
import { 
  LayoutDashboard, 
  FileText, 
  Users, 
  MessageSquare, 
  Activity,
  LogOut,
  ChevronLeft
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

const navItems = [
  { to: '/admin', icon: LayoutDashboard, label: 'Dashboard', exact: true },
  { to: '/admin/documents', icon: FileText, label: 'Documents' },
  { to: '/admin/users', icon: Users, label: 'Users' },
  { to: '/admin/feedback', icon: MessageSquare, label: 'Feedback' },
  { to: '/admin/logs', icon: Activity, label: 'System Logs' },
];

export function AdminSidebar() {
  const location = useLocation();
  const { logout } = useAuth();

  const isActive = (path: string, exact = false) => {
    if (exact) return location.pathname === path;
    return location.pathname.startsWith(path);
  };

  return (
    <div className="w-64 bg-sidebar border-r border-sidebar-border flex flex-col h-screen">
      <div className="p-4 border-b border-sidebar-border">
        <Logo className="text-sidebar-foreground" />
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {navItems.map(({ to, icon: Icon, label, exact }) => (
          <NavLink key={to} to={to} end={exact}>
            <Button
              variant={isActive(to, exact) ? 'sidebarActive' : 'sidebar'}
              className="w-full"
            >
              <Icon className="h-4 w-4 mr-3" />
              {label}
            </Button>
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-sidebar-border space-y-2">
        <NavLink to="/chat">
          <Button variant="sidebar" className="w-full">
            <ChevronLeft className="h-4 w-4 mr-3" />
            Back to Chat
          </Button>
        </NavLink>
        <Button variant="sidebar" className="w-full text-destructive" onClick={logout}>
          <LogOut className="h-4 w-4 mr-3" />
          Logout
        </Button>
      </div>
    </div>
  );
}
