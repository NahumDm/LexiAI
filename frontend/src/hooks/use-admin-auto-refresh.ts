/**
 * useAdminAutoRefresh — drives the admin dashboard's polling cadence.
 *
 * Every admin page has a "Refresh" button that re-fetches data from the
 * backend, AND optionally re-fetches on a fixed interval so admins watching
 * the page see live counts without manual interaction. This hook owns the
 * interval lifecycle so each page doesn't reinvent it (each implementation
 * would otherwise need to remember to clear on unmount, pause on tab hidden,
 * etc.).
 *
 * Behaviour:
 *   - Calls `callback` every `intervalMs` ms (default 30s) WHILE the tab is
 *     visible (we pause via `document.visibilityState` to avoid burning
 *     backend requests in background tabs).
 *   - On `enabled === false` the interval is torn down — useful for pausing
 *     during a long-running action (file upload, delete confirmation).
 *   - Always cleans up on unmount.
 *
 * The callback is read from a ref so consumers can pass an inline closure
 * without thrashing the effect; only `enabled` and `intervalMs` re-arm.
 */

import { useEffect, useRef } from 'react';

const DEFAULT_INTERVAL_MS = 30_000;

export const useAdminAutoRefresh = (
  callback: () => void | Promise<void>,
  options: { enabled?: boolean; intervalMs?: number } = {},
): void => {
  const { enabled = true, intervalMs = DEFAULT_INTERVAL_MS } = options;
  const callbackRef = useRef(callback);

  // Always invoke the LATEST callback closure without re-arming the timer.
  // Without this, every parent re-render would tear down and rebuild the
  // interval (and shift the polling phase by however long the parent took
  // to re-render — a sneaky source of "the interval drifts" bugs).
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return undefined;
    if (typeof window === 'undefined') return undefined;

    const tick = () => {
      // Skip tick when the tab is hidden. SPA admins frequently leave the
      // dashboard open in a background tab — refreshing every 30s in that
      // case would needlessly bill the backend's rate limit.
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      // Fire-and-forget; the callback handles its own error/loading state.
      try {
        const maybePromise = callbackRef.current();
        if (maybePromise && typeof (maybePromise as Promise<void>).catch === 'function') {
          (maybePromise as Promise<void>).catch(() => {
            /* swallow — page-level error handling owns the UI surface */
          });
        }
      } catch {
        /* swallow */
      }
    };

    const handle = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(handle);
  }, [enabled, intervalMs]);
};
