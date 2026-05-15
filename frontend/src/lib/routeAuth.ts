/**
 * Pure redirects for `RouteMiddleware`. Rules match `UserRoute` / `AdminRoute`
 * in `src/components/routing/ProtectedRoute.tsx` (guest allowed on `/chat`).
 */

export interface SessionSnapshot {
  isAuthenticated: boolean;
  isGuest: boolean;
  /** Django staff/superuser, non-guest (same as AuthContext.isAdmin). */
  isAdmin: boolean;
}

const ADMIN_LOGIN = '/admin/login';
const CHAT_PREFIX = '/chat';

function stripQuery(pathname: string): string {
  return pathname.split('?')[0] || '/';
}

function normalizePath(pathname: string): string {
  const path = stripQuery(pathname);
  if (path === '/' || path === '') return '/';
  return path.replace(/\/+$/, '') || '/';
}

function isChatPath(path: string): boolean {
  return path === CHAT_PREFIX || path.startsWith(`${CHAT_PREFIX}/`);
}

/**
 * Returns a path to navigate to, or `null` if the current route is allowed.
 */
export function getNavigationRedirect(
  pathname: string,
  snap: SessionSnapshot,
): string | null {
  const path = normalizePath(pathname);

  if (path === '/admin-login') {
    return ADMIN_LOGIN;
  }

  if (path === ADMIN_LOGIN) {
    if (snap.isAdmin) return '/admin';
    if (snap.isAuthenticated || snap.isGuest) return '/';
    return null;
  }

  if (path.startsWith('/admin')) {
    if (!snap.isAdmin) {
      if (snap.isAuthenticated || snap.isGuest) return '/';
      return ADMIN_LOGIN;
    }
    return null;
  }

  if (path === '/login') {
    if (!snap.isAuthenticated && !snap.isGuest) return null;
    if (snap.isGuest) return CHAT_PREFIX;
    if (snap.isAdmin) return '/admin';
    return CHAT_PREFIX;
  }

  if (path === '/register') {
    if (!snap.isAuthenticated && !snap.isGuest) return null;
    if (snap.isGuest) return CHAT_PREFIX;
    if (snap.isAdmin) return '/admin';
    return CHAT_PREFIX;
  }

  if (isChatPath(path)) {
    if (!snap.isAuthenticated && !snap.isGuest) return '/login';
    if (snap.isAdmin) return '/admin';
    return null;
  }

  if (path === '/') {
    if (snap.isAdmin) return '/admin';
    return null;
  }

  if (path === '/account' || path.startsWith('/account/')) {
    if (snap.isAdmin) return '/admin';
    if (!snap.isAuthenticated && !snap.isGuest) return '/login';
    return null;
  }

  return null;
}
