import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { getNavigationRedirect } from '@/lib/routeAuth';

/**
 * Client-side equivalent of Next.js middleware: enforces redirects from
 * `getNavigationRedirect` before paint to avoid role-mixed flashes.
 */
export function RouteMiddleware({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, isGuest, isAdminAuthenticated, isLoading } = useAuth();
  const lastApplied = useRef<string | null>(null);

  useLayoutEffect(() => {
    if (isLoading) return;

    const snap = { isAuthenticated, isGuest, isAdminAuthenticated };
    const target = getNavigationRedirect(location.pathname, snap);
    if (!target) {
      lastApplied.current = null;
      return;
    }

    const key = `${location.pathname}→${target}`;
    if (lastApplied.current === key) return;
    lastApplied.current = key;
    navigate(target, { replace: true });
  }, [
    isAdminAuthenticated,
    isAuthenticated,
    isGuest,
    isLoading,
    location.pathname,
    navigate,
  ]);

  return <>{children}</>;
}
