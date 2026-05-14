#!/usr/bin/env node
/**
 * Auth flow smoke test against a running backend.
 *
 *   Pre-reqs: backend at http://127.0.0.1:8000 with a real user.
 *   Usage:    node scripts/auth-smoke-test.mjs
 *
 * Verifies:
 *  1. Login with correct credentials → 200 + tokens
 *  2. Profile fetch with access token → 200
 *  3. Conversations fetch with access token → 200
 *  4. Refresh token rotation → 200
 *  5. Login with WRONG credentials → 401 with detail, NOT a forced redirect/clear
 *  6. Logout with refresh token → 200/204
 *
 * Mirrors the request/response shapes that the frontend apiClient produces.
 */

const BASE = process.env.API_BASE || 'http://127.0.0.1:8000';
const PREFIX = `${BASE}/api/v1`;

const EMAIL = process.env.TEST_EMAIL || 'testbug@example.com';
const PASSWORD = process.env.TEST_PASSWORD || 'Pass12345!';

const log = (...a) => console.log('[smoke]', ...a);
const fail = (msg) => { console.error('[smoke] FAIL:', msg); process.exit(1); };

async function req(method, path, { body, token } = {}) {
  const headers = { Accept: 'application/json', 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${PREFIX}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    try { data = await res.json(); } catch { /* empty */ }
  }
  return { status: res.status, data };
}

(async () => {
  // 1. Login (happy path)
  let r = await req('POST', '/auth/login/', { body: { email: EMAIL, password: PASSWORD } });
  if (r.status !== 200) fail(`login expected 200, got ${r.status}: ${JSON.stringify(r.data)}`);
  if (!r.data?.access || !r.data?.refresh || !r.data?.user) {
    fail(`login response missing fields: ${JSON.stringify(r.data)}`);
  }
  log('1. login OK', { user: r.data.user.email });
  const access = r.data.access;
  const refresh = r.data.refresh;

  // 2. Profile with bearer
  r = await req('GET', '/auth/profile/', { token: access });
  if (r.status !== 200) fail(`profile expected 200, got ${r.status}: ${JSON.stringify(r.data)}`);
  log('2. profile OK', { email: r.data.email });

  // 3. Conversations with bearer
  r = await req('GET', '/conversations/', { token: access });
  if (r.status !== 200) fail(`conversations expected 200, got ${r.status}: ${JSON.stringify(r.data)}`);
  log('3. conversations OK', { count: r.data.count });

  // 4. Refresh rotation
  r = await req('POST', '/auth/refresh/', { body: { refresh } });
  if (r.status !== 200) fail(`refresh expected 200, got ${r.status}: ${JSON.stringify(r.data)}`);
  if (!r.data?.access) fail(`refresh response missing access: ${JSON.stringify(r.data)}`);
  log('4. refresh OK', { gotNewAccess: !!r.data.access, gotNewRefresh: !!r.data.refresh });
  const rotatedRefresh = r.data.refresh || refresh;

  // 5. Login with WRONG password
  r = await req('POST', '/auth/login/', { body: { email: EMAIL, password: 'definitely-wrong' } });
  if (r.status !== 401) fail(`wrong-creds login expected 401, got ${r.status}`);
  if (!r.data?.detail) fail(`wrong-creds login expected 'detail' message, got ${JSON.stringify(r.data)}`);
  log('5. wrong-creds login → 401 with detail OK', { detail: r.data.detail });

  // 6. Logout with refresh
  r = await req('POST', '/auth/logout/', { body: { refresh: rotatedRefresh }, token: r.data?.access || access });
  // TokenBlacklistView returns 200 with empty body
  if (r.status >= 400) fail(`logout expected 2xx, got ${r.status}: ${JSON.stringify(r.data)}`);
  log('6. logout OK', { status: r.status });

  log('ALL OK ✓');
})().catch((err) => { console.error(err); process.exit(2); });
