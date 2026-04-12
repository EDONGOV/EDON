/**
 * EDON Auth Utilities
 * Role-based access control + session timeout config
 */

export type UserRole = 'admin' | 'operator' | 'viewer';

const ROLE_LEVEL: Record<UserRole, number> = {
  viewer:   0,
  operator: 1,
  admin:    2,
};

const ROLE_KEY = 'edon_user_role';

export function getUserRole(): UserRole {
  const stored = localStorage.getItem(ROLE_KEY) as UserRole | null;
  if (stored && stored in ROLE_LEVEL) return stored;
  // Backwards compat
  if (localStorage.getItem('edon_is_admin') === 'true') return 'admin';
  return 'operator'; // safe default
}

export function setUserRole(role: UserRole): void {
  localStorage.setItem(ROLE_KEY, role);
  if (role === 'admin') localStorage.setItem('edon_is_admin', 'true');
  else localStorage.removeItem('edon_is_admin');
}

export function hasRole(required: UserRole): boolean {
  return ROLE_LEVEL[getUserRole()] >= ROLE_LEVEL[required];
}

export function getRoleLabel(role: UserRole): string {
  return { admin: 'Admin', operator: 'Operator', viewer: 'Viewer' }[role];
}

// ── Session timeout ──────────────────────────────────────────────────────────
export const SESSION_TIMEOUT_MS  = 15 * 60 * 1000;  // 15 min — auto sign-out
export const SESSION_WARN_MS     = 13 * 60 * 1000;  // 13 min — show warning

export function signOut(): void {
  ['edon_token', 'edon_api_key', 'edon_session_token',
   'edon_user_email', 'edon_plan', 'edon_user_role'].forEach(k => localStorage.removeItem(k));
  window.dispatchEvent(new Event('edon-auth-updated'));
  window.location.replace('/');
}
