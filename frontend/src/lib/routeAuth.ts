/**
 * Pure redirects for `RouteMiddleware`. Rules match `UserRoute` / `AdminRoute`
 * in `src/components/routing/ProtectedRoute.tsx` (guest allowed on `/chat`).
 *
 * User and admin JWT sessions use separate storage keys; redirects must not
 * treat a user-session as admin access or vice versa.
 */

export interface SessionSnapshot {
  /** Signed-in user app session (non-guest). */
  isAuthenticated: boolean;
  isGuest: boolean;
  /** Admin SPA session (`lexiai.admin.*` tokens + staff profile). */
  isAdminAuthenticated: boolean;
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
    if (snap.isAdminAuthenticated) return '/admin';
    return null;
  }

  if (path.startsWith('/admin')) {
    if (!snap.isAdminAuthenticated) {
      return ADMIN_LOGIN;
    }
    return null;
  }

  if (path === '/login' || path === '/register') {
    if (snap.isAdminAuthenticated) return '/admin';
    if (!snap.isAuthenticated && !snap.isGuest) return null;
    if (snap.isGuest) return CHAT_PREFIX;
    return CHAT_PREFIX;
  }

  if (isChatPath(path)) {
    if (!snap.isAuthenticated && !snap.isGuest) return '/login';
    if (snap.isAdminAuthenticated && !snap.isAuthenticated && !snap.isGuest) {
      return '/login';
    }
    return null;
  }

  if (path === '/') {
    if (snap.isAdminAuthenticated) return '/admin';
    return null;
  }

  if (path === '/account' || path.startsWith('/account/')) {
    if (snap.isAdminAuthenticated && !snap.isAuthenticated && !snap.isGuest) {
      return '/login';
    }
    if (!snap.isAuthenticated && !snap.isGuest) return '/login';
    return null;
  }

  return null;
}
