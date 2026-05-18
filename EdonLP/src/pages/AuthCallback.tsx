import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield } from 'lucide-react'
import { supabase } from '../lib/supabase'
import { toast } from 'sonner'

/**
 * Landing page for:
 *  - Google OAuth redirect
 *  - Magic link email clicks
 *
 * Supabase automatically exchanges the URL fragment / code for a session.
 * We just wait for onAuthStateChange to fire, then forward to /account.
 */
export default function AuthCallback() {
  const navigate = useNavigate()

  useEffect(() => {
    // Supabase processes the code/fragment in the URL automatically on createClient.
    // We listen for the SIGNED_IN event and then redirect.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_IN' && session) {
        subscription.unsubscribe()
        navigate('/account', { replace: true })
      } else if (event === 'SIGNED_OUT' || (!session && event !== 'INITIAL_SESSION')) {
        toast.error('Sign-in failed or link expired. Please try again.')
        navigate('/login', { replace: true })
      }
    })

    // Fallback: check for existing session (in case event already fired)
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) {
        subscription.unsubscribe()
        navigate('/account', { replace: true })
      }
    })

    return () => subscription.unsubscribe()
  }, [navigate])

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
      <div className="h-12 w-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center glow-primary-sm">
        <Shield className="h-6 w-6 text-primary" />
      </div>
      <div className="flex flex-col items-center gap-2">
        <div className="h-5 w-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <p className="text-sm text-muted-foreground">Completing sign-in…</p>
      </div>
    </div>
  )
}
