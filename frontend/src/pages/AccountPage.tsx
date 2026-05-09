'use client';

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AuthAPI } from '@/lib/api/auth';
import { useAuth } from '@/contexts/AuthContext';
import { Loader2, ArrowLeft, User as UserIcon } from 'lucide-react';

export default function AccountPage() {
  const { refreshUser } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await AuthAPI.getCurrentUser();
        if (cancelled) return;
        if (response.data) {
          setDisplayName(response.data.name || '');
          setEmail(response.data.email || '');
        } else {
          setError(response.error || 'Could not load profile');
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Could not load profile');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveMessage(null);
    setError(null);
    try {
      const response = await AuthAPI.updateProfile({ full_name: displayName.trim() });
      if (response.data) {
        await refreshUser();
        setSaveMessage('Your profile was updated.');
      } else {
        setError(response.error || 'Could not save changes');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save changes');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-background flex flex-col">
        <Header variant="app" />
        <main className="flex-1 max-w-xl mx-auto w-full px-4 py-8 space-y-6">
          <Link
            to="/chat"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to chat
          </Link>

          <Card>
            <CardHeader>
              <CardTitle>My account</CardTitle>
              <CardDescription>Manage your profile and preferences.</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <form onSubmit={handleSave} className="space-y-6">
                  {error && (
                    <Alert variant="destructive">
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  )}
                  {saveMessage && (
                    <Alert>
                      <AlertDescription>{saveMessage}</AlertDescription>
                    </Alert>
                  )}

                  <div className="flex flex-col items-center gap-2">
                    <div className="h-24 w-24 rounded-full bg-primary/10 border border-border flex items-center justify-center text-3xl font-semibold text-primary">
                      {(displayName || email || '?').charAt(0).toUpperCase()}
                    </div>
                    <p className="text-xs text-muted-foreground text-center">
                      Photo upload coming soon
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="name">Name</Label>
                    <Input
                      id="name"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="Your name"
                      autoComplete="name"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input id="email" type="email" value={email} readOnly disabled className="bg-muted" />
                  </div>

                  <Button type="submit" disabled={isSaving}>
                    {isSaving ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Saving…
                      </>
                    ) : (
                      'Save changes'
                    )}
                  </Button>

                  <div className="border-t pt-6 space-y-3">
                    <h3 className="text-sm font-medium flex items-center gap-2">
                      <UserIcon className="h-4 w-4" />
                      Password
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Password changes will be available in a future update.
                    </p>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </main>
      </div>
    </ProtectedRoute>
  );
}
