/**
 * Regression tests for the production-blocker auth bug.
 *
 * Original symptom: login with wrong credentials triggered the apiClient's
 * 401-handler, which (1) fired the unauthorized callback (clearing user state
 * + redirecting to /login), and (2) returned the error string
 * "Authentication failed. Please log in again.". The user perceived this as
 * a failed login that simultaneously logged them out.
 *
 * After the fix, /auth/* endpoints bubble 401 as a regular error WITHOUT
 * touching the unauthorized handler or stored tokens.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient, formatApiErrorMessage } from './client';

const ACCESS_KEY = 'lexiai.user.access_token';
const REFRESH_KEY = 'lexiai.user.refresh_token';

describe('apiClient — 401 handling', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    apiClient.clearUnauthorizedHandler();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('does NOT trigger the unauthorized handler when /auth/login/ returns 401', async () => {
    const unauthorizedSpy = vi.fn();
    apiClient.setUnauthorizedHandler(unauthorizedSpy);

    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'No active account found with the given credentials' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      })
    ) as unknown as typeof fetch;

    const res = await apiClient.post('/auth/login/', { email: 'x@y.z', password: 'wrong' });

    expect(res.status).toBe(401);
    expect(res.error).toContain('No active account');
    // The CRITICAL assertion — the regression we're guarding against:
    expect(unauthorizedSpy).not.toHaveBeenCalled();
    // And the apiClient must NOT have emitted the misleading
    // "Authentication failed. Please log in again." string for a login 401.
    expect(res.error).not.toBe('Authentication failed. Please log in again.');
  });

  it('does NOT attempt token refresh on /auth/login/ 401', async () => {
    localStorage.setItem(REFRESH_KEY, 'stale-but-present-refresh');

    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'No active account found with the given credentials' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      })
    );
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    await apiClient.post('/auth/login/', { email: 'x@y.z', password: 'wrong' });

    // Only the login call — no follow-up POST to /auth/refresh/.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls.every((u) => !u.includes('/auth/refresh/'))).toBe(true);
  });

  it('DOES trigger refresh + unauthorized handler when a PROTECTED endpoint returns 401', async () => {
    localStorage.setItem(ACCESS_KEY, 'dead-access-token');
    // No refresh token → refresh will fail → unauthorized handler must fire.

    const unauthorizedSpy = vi.fn();
    apiClient.setUnauthorizedHandler(unauthorizedSpy);

    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'token expired' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      })
    ) as unknown as typeof fetch;

    const res = await apiClient.get('/conversations/');

    expect(res.status).toBe(401);
    expect(res.error).toBe('Authentication failed. Please log in again.');
    expect(unauthorizedSpy).toHaveBeenCalledTimes(1);
    // Tokens should have been cleared.
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
  });

  it('attaches Authorization header from localStorage on every request', async () => {
    localStorage.setItem(ACCESS_KEY, 'fresh-access-token');

    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200, headers: { 'content-type': 'application/json' } })
    );
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    await apiClient.get('/auth/profile/');

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer fresh-access-token');
    expect(headers['Accept']).toBe('application/json');
  });

  it('persists access + refresh tokens via setAuthTokens', () => {
    apiClient.setAuthTokens('access-xyz', 'refresh-xyz', 'user');
    expect(localStorage.getItem(ACCESS_KEY)).toBe('access-xyz');
    expect(localStorage.getItem(REFRESH_KEY)).toBe('refresh-xyz');
    expect(apiClient.hasToken()).toBe(true);
    expect(apiClient.getRefreshToken()).toBe('refresh-xyz');
  });

  it('migrates legacy sessionStorage tokens on first read', () => {
    sessionStorage.setItem('access_token', 'legacy-access');
    sessionStorage.setItem('refresh_token', 'legacy-refresh');

    // Force a fresh client construction by re-invoking migrate via a getter.
    // The singleton already migrated at module load, so just verify legacy
    // tokens are present in the new namespace when they were the only ones.
    // (Re-running migration is idempotent.)
    // @ts-expect-error -- access private method for test coverage
    apiClient.migrateLegacyStorage?.();

    expect(localStorage.getItem(ACCESS_KEY)).toBe('legacy-access');
    expect(localStorage.getItem(REFRESH_KEY)).toBe('legacy-refresh');
    expect(sessionStorage.getItem('access_token')).toBeNull();
  });
});

describe('formatApiErrorMessage', () => {
  it('flattens DRF field errors without object stringification', () => {
    const s = formatApiErrorMessage({ email: ['A user with that email already exists.'] });
    expect(s).toContain('email:');
    expect(s).toContain('already exists');
    expect(s).not.toContain('[object Object]');
  });

  it('handles nested detail object via JSON', () => {
    const s = formatApiErrorMessage({ detail: { code: 'invalid' } });
    expect(s.length).toBeGreaterThan(0);
  });
});
