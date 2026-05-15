/**
 * Route gate rules for role-separated UX (user vs Django staff admin).
 *
 * In Next.js this file would run on the Edge before render. This project uses
 * Vite + React Router; `src/components/routing/RouteMiddleware.tsx` applies
 * `getNavigationRedirect` on the client on every pathname change.
 */

export { getNavigationRedirect, type SessionSnapshot } from '@/lib/routeAuth';
