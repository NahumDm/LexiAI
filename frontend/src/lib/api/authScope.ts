/**
 * Isolated JWT storage for the user app vs the admin SPA.
 * Same origin shares localStorage, but keys must not overlap.
 */
export type AuthScope = 'user' | 'admin';

export const AUTH_STORAGE_KEYS: Record<
  AuthScope,
  { access: string; refresh: string; profile: string }
> = {
  user: {
    access: 'lexiai.user.access_token',
    refresh: 'lexiai.user.refresh_token',
    profile: 'lexiai.user.profile',
  },
  admin: {
    access: 'lexiai.admin.access_token',
    refresh: 'lexiai.admin.refresh_token',
    profile: 'lexiai.admin.profile',
  },
};

/** Pre-scope-split keys — migrated into the user namespace only. */
export const LEGACY_AUTH_KEYS = {
  access: 'lexiai.access_token',
  refresh: 'lexiai.refresh_token',
  profile: 'lexiai.user',
} as const;
