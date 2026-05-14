/**
 * Admin Login Page (/admin-login)
 *
 * Standalone form that ONLY admits Django staff / superusers into the SPA
 * admin dashboard. Intentionally isolated from the regular `/login` flow:
 *
 *  - Uses the SAME backend endpoint (`POST /api/v1/auth/login/`) and the SAME
 *    token-storage path (`AuthAPI.login` → `apiClient.setAuthTokens`), so
 *    there is no parallel auth system.
 *  - Re-fetches profile via `useAuth().refreshUser()` so AuthContext picks up
 *    the new user without us mutating its internals.
 *  - After successful token + profile fetch, gates the navigation on
 *    `is_staff || is_superuser`. A non-admin login is REVERSED (tokens
 *    cleared, no AuthContext state retained) so a regular user typing their
 *    credentials here cannot accidentally end up logged in via this page.
 *
 * The regular `/login` is untouched — non-admin users keep using it and land
 * on `/chat`.
 */

'use client';

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { AuthAPI } from '@/lib/api/auth';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Logo } from '@/components/icons/Logo';
import { AlertCircle, Eye, EyeOff, Loader2, ShieldCheck } from 'lucide-react';

const ACCESS_DENIED_MESSAGE = 'Access denied: Admin privileges required.';

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const { isAdmin, isAuthenticated, refreshUser, logout } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // If a staff user lands here while already signed in (e.g. they bookmarked
  // /admin-login), short-circuit straight to the dashboard. Non-admins who
  // were already authenticated stay on this page so they can either log out
  // or switch accounts — we don't auto-bounce them to /chat.
  useEffect(() => {
    if (isAuthenticated && isAdmin) {
      navigate('/admin', { replace: true });
    }
  }, [isAuthenticated, isAdmin, navigate]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError('');

    try {
      // Step 1: authenticate. `AuthAPI.login` already persists tokens via
      // apiClient.setAuthTokens, identical to the regular login path.
      const response = await AuthAPI.login({ email, password });

      if (!response.data?.access || !response.data?.user) {
        setError(
          response.error ||
            (response.status === 0
              ? 'Could not reach the server. Check your connection and try again.'
              : 'Invalid email or password.')
        );
        return;
      }

      const user = response.data.user;

      // Step 2: admin gate. We trust ONLY Django's canonical staff flags here;
      // a custom `role` field would let an attacker who controls a user
      // payload escalate themselves. The backend additionally enforces
      // `IsAdminUser` on every admin endpoint, so this is UI-only defence.
      if (!(user.is_staff || user.is_superuser)) {
        // Reverse the login: blacklist the refresh token, drop access/refresh
        // from storage, and clear the user mirror. Critically we DO NOT call
        // AuthContext.logout() because that navigates to "/" and clears guest
        // state we don't care about here — we want to stay on this page so
        // the user can re-try with an admin account.
        try {
          await AuthAPI.logout();
        } catch {
          /* best-effort — tokens are still cleared below */
        }
        apiClient.clearStoredUser();
        setError(ACCESS_DENIED_MESSAGE);
        return;
      }

      // Step 3: hydrate AuthContext. `refreshUser` re-fetches `/auth/profile/`
      // using the freshly-set bearer token, which triggers AuthContext's
      // internal `setUser` (the only sanctioned way to seed it from outside).
      apiClient.setStoredUser(user);
      await refreshUser();

      navigate('/admin', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignOut = async () => {
    setError('');
    await logout();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Logo size="lg" />
          <div className="mt-6 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
            <ShieldCheck className="h-3.5 w-3.5" />
            Admin Console
          </div>
          <h1 className="mt-3 text-3xl font-serif font-bold">Admin Sign In</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Staff and superusers only. Regular users should use the{' '}
            <button
              type="button"
              className="underline underline-offset-2 hover:text-foreground"
              onClick={() => navigate('/login')}
            >
              standard login
            </button>
            .
          </p>
        </div>

        <div className="bg-card border border-border rounded-lg shadow-sm p-8">
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="admin-email">Email Address</Label>
              <Input
                id="admin-email"
                type="email"
                autoComplete="email"
                placeholder="admin@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={isSubmitting}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="admin-password">Password</Label>
              <div className="relative">
                <Input
                  id="admin-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={isSubmitting}
                  required
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                  onClick={() => setShowPassword((value) => !value)}
                  disabled={isSubmitting}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button
              type="submit"
              className="w-full"
              size="lg"
              disabled={isSubmitting || !email || !password}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying admin access…
                </>
              ) : (
                'Sign in to Admin'
              )}
            </Button>
          </form>

          {isAuthenticated && !isAdmin && (
            <div className="mt-6 pt-6 border-t border-border text-center text-xs text-muted-foreground">
              <p>
                You're signed in as a regular user.{' '}
                <button
                  type="button"
                  className="underline underline-offset-2 hover:text-foreground"
                  onClick={handleSignOut}
                >
                  Sign out
                </button>{' '}
                to switch accounts.
              </p>
            </div>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          Looking for the model-CRUD admin?{' '}
          <a
            href="/admin/"
            className="underline underline-offset-2 hover:text-foreground"
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Django Admin
          </a>
        </p>
      </div>
    </div>
  );
}
