import { describe, expect, it } from 'vitest';
import { getNavigationRedirect, type SessionSnapshot } from './routeAuth';

const guest: SessionSnapshot = {
  isAuthenticated: false,
  isGuest: true,
  isAdminAuthenticated: false,
};
const user: SessionSnapshot = {
  isAuthenticated: true,
  isGuest: false,
  isAdminAuthenticated: false,
};
const adminOnly: SessionSnapshot = {
  isAuthenticated: false,
  isGuest: false,
  isAdminAuthenticated: true,
};
const userAndAdmin: SessionSnapshot = {
  isAuthenticated: true,
  isGuest: false,
  isAdminAuthenticated: true,
};
const anon: SessionSnapshot = {
  isAuthenticated: false,
  isGuest: false,
  isAdminAuthenticated: false,
};

describe('getNavigationRedirect', () => {
  it('maps legacy /admin-login to /admin/login', () => {
    expect(getNavigationRedirect('/admin-login', anon)).toBe('/admin/login');
  });

  it('admin login: only admin session redirects; user session may stay on form', () => {
    expect(getNavigationRedirect('/admin/login', adminOnly)).toBe('/admin');
    expect(getNavigationRedirect('/admin/login', userAndAdmin)).toBe('/admin');
    expect(getNavigationRedirect('/admin/login', user)).toBe(null);
    expect(getNavigationRedirect('/admin/login', guest)).toBe(null);
    expect(getNavigationRedirect('/admin/login', anon)).toBe(null);
  });

  it('admin area: requires admin session only', () => {
    expect(getNavigationRedirect('/admin', anon)).toBe('/admin/login');
    expect(getNavigationRedirect('/admin/documents', user)).toBe('/admin/login');
    expect(getNavigationRedirect('/admin', guest)).toBe('/admin/login');
    expect(getNavigationRedirect('/admin', adminOnly)).toBe(null);
    expect(getNavigationRedirect('/admin', userAndAdmin)).toBe(null);
  });

  it('user login: user goes to chat; admin session to admin app', () => {
    expect(getNavigationRedirect('/login', anon)).toBe(null);
    expect(getNavigationRedirect('/login', guest)).toBe('/chat');
    expect(getNavigationRedirect('/login', user)).toBe('/chat');
    expect(getNavigationRedirect('/login', adminOnly)).toBe('/admin');
  });

  it('chat: user or guest allowed; not admin-only session', () => {
    expect(getNavigationRedirect('/chat', anon)).toBe('/login');
    expect(getNavigationRedirect('/chat', user)).toBe(null);
    expect(getNavigationRedirect('/chat', guest)).toBe(null);
    expect(getNavigationRedirect('/chat', adminOnly)).toBe('/login');
    expect(getNavigationRedirect('/chat', userAndAdmin)).toBe(null);
  });

  it('landing: admin session goes to admin dashboard', () => {
    expect(getNavigationRedirect('/', anon)).toBe(null);
    expect(getNavigationRedirect('/', adminOnly)).toBe('/admin');
    expect(getNavigationRedirect('/', user)).toBe(null);
  });
});
