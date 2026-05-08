import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Logo } from '@/components/icons/Logo';
import { useAuth } from '@/contexts/AuthContext';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuSeparator,
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { User, LogOut, Settings, LayoutDashboard } from 'lucide-react';

interface HeaderProps {
  onLoginClick?: () => void;
  onRegisterClick?: () => void;
  variant?: 'landing' | 'app';
}

export function Header({ onLoginClick, onRegisterClick, variant = 'landing' }: HeaderProps) {
  const { user, isAuthenticated, isGuest, isAdmin, logout } = useAuth();
  const displayName = user?.name?.trim() || user?.username || user?.email || 'User';
  const avatarInitial = displayName.charAt(0).toUpperCase();

  const isLanding = variant === 'landing';
  const headerBg = isLanding ? 'bg-transparent' : 'bg-card border-b border-border';

  return (
    <header className={`${headerBg} py-4 px-6 sticky top-0 z-50`}>
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link to="/" className="flex items-center">
          <Logo size="md" />
        </Link>

        <nav className="flex items-center gap-4">
          {isGuest && (
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-warning/10 border border-warning/30 rounded-full">
              <span className="text-sm text-warning font-medium">Guest Mode</span>
            </div>
          )}

          {!user && (
            <Button variant="ghost" onClick={onLoginClick}>
              Login
            </Button>
          )}

          {user && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center">
                    <span className="text-primary-foreground text-sm font-medium">
                      {avatarInitial}
                    </span>
                  </div>
                  <span className="hidden sm:inline text-foreground">{displayName}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="px-2 py-1.5">
                  <p className="text-sm font-medium">{displayName}</p>
                  <p className="text-xs text-muted-foreground">{user.email || 'Guest User'}</p>
                </div>
                <DropdownMenuSeparator />
                {isAdmin && (
                  <DropdownMenuItem asChild>
                    <Link to="/admin" className="cursor-pointer">
                      <LayoutDashboard className="mr-2 h-4 w-4" />
                      Admin Dashboard
                    </Link>
                  </DropdownMenuItem>
                )}
                {isAuthenticated && (
                  <DropdownMenuItem asChild>
                    <Link to="/chat" className="cursor-pointer">
                      <User className="mr-2 h-4 w-4" />
                      My Account
                    </Link>
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="text-destructive cursor-pointer">
                  <LogOut className="mr-2 h-4 w-4" />
                  {isGuest ? 'Exit Guest Mode' : 'Logout'}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </nav>
      </div>
    </header>
  );
}
