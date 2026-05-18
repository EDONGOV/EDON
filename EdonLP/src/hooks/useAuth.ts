import { useAuthContext } from '../contexts/AuthContext'

/**
 * Thin convenience hook — reads from AuthContext.
 * Use this everywhere in the app instead of directly consuming AuthContext.
 */
export function useAuth() {
  const { user, session, loading, edonToken, signOut } = useAuthContext()

  return {
    user,
    session,
    loading,
    /** The EDON API key for gateway calls */
    token: edonToken,
    isLoggedIn: !!session,
    logout: signOut,
    // Legacy compat — kept so existing components don't break
    login: (_token: string, _base?: string) => {
      console.warn('[useAuth] login() is no longer used — auth is handled by Supabase')
    },
  }
}
