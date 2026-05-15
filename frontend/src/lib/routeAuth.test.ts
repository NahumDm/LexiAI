import { describe, expect, it } from 'vitest';
import { getNavigationRedirect, type SessionSnapshot } from './routeAuth';

const guest: SessionSnapshot = {
  isAuthenticated: false,
  isGuest: true,
  isAdmin: false,
};
const user: SessionSnapshot = {
  isAuthenticated: true,
  isGuest: false,
  isAdmin: false,
};
const admin: SessionSnapshot = {
  isAuthenticated: true,
  isGuest: false,
  isAdmin: true,
};
const anon: SessionSnapshot = {
  isAuthenticated: false,
  isGuest: false,
  isAdmin: false,
};

describe('getNavigationRedirect', () => {
  it('maps legacy /admin-login to /admin/login', () => {
    expect(getNavigationRedirect('/admin-login', anon)).toBe('/admin/login');
  });

  it('admin login: admin goes to dashboard; others to home', () => {
    expect(getNavigationRedirect('/admin/login', admin)).toBe('/admin');
    expect(getNavigationRedirect('/admin/login', user)).toBe('/');
    expect(getNavigationRedirect('/admin/login', guest)).toBe('/');
    expect(getNavigationRedirect('/admin/login', anon)).toBe(null);
  });

  it('admin area: unauthenticated to login; non-admin with session to /', () => {
    expect(getNavigationRedirect('/admin', anon)).toBe('/admin/login');
    expect(getNavigationRedirect('/admin/documents', anon)).toBe('/admin/login');
    expect(getNavigationRedirect('/admin', user)).toBe('/');
    expect(getNavigationRedirect('/admin', guest)).toBe('/');
    expect(getNavigationRedirect('/admin', admin)).toBe(null);
  });

  it('user login: redirects by role', () => {
    expect(getNavigationRedirect('/login', anon)).toBe(null);
    expect(getNavigationRedirect('/login', guest)).toBe('/chat');
    expect(getNavigationRedirect('/login', user)).toBe('/chat');
    expect(getNavigationRedirect('/login', admin)).toBe('/admin');
  });

  it('chat: requires session; admin sent to admin app', () => {
    expect(getNavigationRedirect('/chat', anon)).toBe('/login');
    expect(getNavigationRedirect('/chat', user)).toBe(null);
    expect(getNavigationRedirect('/chat', guest)).toBe(null);
    expect(getNavigationRedirect('/chat', admin)).toBe('/admin');
  });

  it('landing: admin cannot stay on /', () => {
    expect(getNavigationRedirect('/', anon)).toBe(null);
    expect(getNavigationRedirect('/', admin)).toBe('/admin');
  });
});
