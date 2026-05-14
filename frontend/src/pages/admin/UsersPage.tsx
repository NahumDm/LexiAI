/**
 * Admin → Users
 *
 * Wires `AdminAPI.getUsers({ search })` →
 * `GET /api/v1/accounts/users/?search=...`. Admin-only, returns every
 * account on the system. Search is server-side (icontains over email,
 * username, first/last name); the SPA passes the debounced query through
 * and renders whatever the backend matched. Refresh forces a fresh
 * round-trip; a 30s auto-refresh keeps the table live.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertCircle,
  Loader2,
  Mail,
  MoreVertical,
  RefreshCw,
  Search,
  Shield,
  User as UserIcon,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AdminAPI, type AdminUser } from '@/lib/api/admin';
import { useAdminAutoRefresh } from '@/hooks/use-admin-auto-refresh';
import { format, formatDistanceToNow } from 'date-fns';

const SEARCH_DEBOUNCE_MS = 350;

const formatLastActive = (iso: string | null | undefined): string => {
  if (!iso) return 'Never';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return formatDistanceToNow(date, { addSuffix: true });
};

const formatJoined = (iso: string | undefined | null): string => {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return format(date, 'MMM d, yyyy');
};

const roleLabel = (role: AdminUser['role']): string => {
  if (!role) return 'user';
  if (typeof role === 'string') return role;
  return role.code || role.name || 'user';
};

const displayName = (user: AdminUser): string => {
  const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim();
  if (fullName) return fullName;
  return user.username || user.email;
};

export default function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [stats, setStats] = useState({ total: 0, active: 0, staff: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [endpointMissing, setEndpointMissing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const fetchUsers = useCallback(
    async (mode: 'initial' | 'refresh' = 'initial', search?: string) => {
      if (mode === 'initial') {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);
      setEndpointMissing(false);

      const response = await AdminAPI.getUsers({ search, reload: mode === 'refresh' });
      if (response.data) {
        setUsers(response.data.results);
        setStats(response.data.stats);
      } else if (response.status === 404) {
        setEndpointMissing(true);
        setUsers([]);
        setStats({ total: 0, active: 0, staff: 0 });
      } else {
        setError(response.error || 'Could not load users.');
      }
      setIsLoading(false);
      setIsRefreshing(false);
    },
    []
  );

  useEffect(() => {
    // First load uses the spinner; debounced search-driven fetches don't,
    // to avoid table flicker on each keystroke.
    fetchUsers(users.length === 0 ? 'initial' : 'refresh', debouncedSearch || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, fetchUsers]);

  useAdminAutoRefresh(
    () => fetchUsers('refresh', debouncedSearch || undefined),
    { enabled: !isRefreshing && !endpointMissing },
  );

  // Server already filtered; render the array as-is.
  const filteredUsers = users;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground">Users</h1>
          <p className="text-muted-foreground mt-1">Manage registered users and view activity</p>
        </div>
        <Button
          variant="outline"
          onClick={() => fetchUsers('refresh', debouncedSearch || undefined)}
          disabled={isLoading || isRefreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading || isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {endpointMissing && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            The user list endpoint (<code>GET /api/v1/accounts/users/</code>) is not yet
            implemented on the backend. This page will populate automatically once it
            ships. See <code>frontend/src/lib/api/admin.ts</code> for the contract.
          </AlertDescription>
        </Alert>
      )}

      {error && !endpointMissing && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-sm text-muted-foreground">Total Users</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-success">{stats.active}</div>
            <p className="text-sm text-muted-foreground">Active</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{stats.staff}</div>
            <p className="text-sm text-muted-foreground">Staff / Admin</p>
          </CardContent>
        </Card>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search users..."
          className="pl-9"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
      </div>

      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Joined</TableHead>
              <TableHead>Last Active</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                  <Loader2 className="h-4 w-4 inline mr-2 animate-spin" />
                  Loading users…
                </TableCell>
              </TableRow>
            ) : filteredUsers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                  {endpointMissing
                    ? 'No users to display until the backend endpoint is available.'
                    : searchQuery
                      ? 'No users match your search.'
                      : 'No users found.'}
                </TableCell>
              </TableRow>
            ) : (
              filteredUsers.map((user) => {
                const isAdmin = user.is_staff || user.is_superuser;
                return (
                  <TableRow key={user.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
                          {isAdmin ? (
                            <Shield className="h-4 w-4 text-primary" />
                          ) : (
                            <UserIcon className="h-4 w-4 text-primary" />
                          )}
                        </div>
                        <div>
                          <p className="font-medium">{displayName(user)}</p>
                          <p className="text-sm text-muted-foreground">{user.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={isAdmin ? 'default' : 'secondary'}>
                        {isAdmin ? 'admin' : roleLabel(user.role)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.is_active ? 'default' : 'outline'}>
                        {user.is_active ? 'Active' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatJoined(user.date_joined ?? user.created_at)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatLastActive(user.last_login)}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <a href={`mailto:${user.email}`}>
                              <Mail className="h-4 w-4 mr-2" />
                              Email user
                            </a>
                          </DropdownMenuItem>
                          {/* Deactivate is intentionally left as a stub until the
                              accounts admin endpoint exists. */}
                          <DropdownMenuItem disabled>Deactivate (coming soon)</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
