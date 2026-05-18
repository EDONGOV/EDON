import { Link, useSearchParams } from 'react-router-dom'
import { Shield, CheckCircle, ArrowRight, Terminal } from 'lucide-react'

const CONSOLE_URL =
  (import.meta.env.VITE_AGENT_UI_URL as string | undefined) ??
  'https://console.edoncore.com'

export default function SignupSuccess() {
  const [params] = useSearchParams()
  // Stripe appends ?session_id=cs_... on success redirect
  const sessionId = params.get('session_id')

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border/50 py-4 px-6">
        <Link to="/" className="flex items-center gap-2 w-fit">
          <span className="h-6 w-6 rounded bg-primary flex items-center justify-center">
            <Shield className="h-3.5 w-3.5 text-primary-foreground" />
          </span>
          <span className="font-space text-lg font-semibold tracking-tight">EDON</span>
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-16">
        <div className="w-full max-w-lg text-center">
          <div className="mb-6 flex justify-center">
            <span className="h-16 w-16 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center">
              <CheckCircle className="h-8 w-8 text-primary" />
            </span>
          </div>

          <h1 className="font-space text-3xl font-bold mb-3">You're in.</h1>
          <p className="text-muted-foreground mb-8 max-w-sm mx-auto">
            Payment confirmed. Your EDON workspace is being activated — you'll receive an email
            with your API key within a few minutes.
          </p>

          <div className="rounded-lg border border-border bg-card p-5 text-left mb-8">
            <p className="text-sm font-medium mb-3">What happens next</p>
            <ol className="space-y-3">
              {[
                'Check your inbox — we\'ll send your API key and onboarding instructions.',
                'Install the EDON SDK: pip install edon-sdk',
                'Wrap your agent client and deploy. You\'re governed.',
              ].map((step, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-muted-foreground">
                  <span className="font-space text-primary font-bold shrink-0">{i + 1}.</span>
                  {step}
                </li>
              ))}
            </ol>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <a
              href={CONSOLE_URL}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Open console <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href="https://docs.edoncore.com/quickstart"
              className="inline-flex items-center justify-center gap-2 rounded-md border border-border px-5 py-2.5 text-sm font-medium hover:bg-secondary transition-colors"
            >
              <Terminal className="h-4 w-4" /> Quickstart guide
            </a>
          </div>

          {sessionId && (
            <p className="mt-8 text-xs text-muted-foreground/50">
              Session: {sessionId}
            </p>
          )}
        </div>
      </main>
    </div>
  )
}
