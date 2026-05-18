import { useQuery } from '@tanstack/react-query'
import { CreditCard, Zap, ArrowRight, CheckCircle, AlertTriangle } from 'lucide-react'
import AccountLayout, { PageHeader, Spinner } from './AccountLayout'
import { gwBillingStatus } from '../../lib/gateway'

const PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  scale: 'Scale — $150/mo',
  pro: 'Pro — $600/mo',
  trial: 'Trial',
  hospital: 'Hospital',
}

const PLAN_FEATURES: Record<string, string[]> = {
  free: ['50K decisions/mo', '3 agents', '7-day audit retention'],
  trial: ['50K decisions/mo', '3 agents', '7-day audit retention', 'Full feature access during trial'],
  scale: ['5M decisions/mo', '100 agents', '90-day audit retention', 'Slack & Telegram alerts'],
  pro: ['25M decisions/mo', '1,000 agents', '365-day audit retention', 'Compliance suite (HIPAA / SOC 2)', 'Custom policy rules'],
  hospital: ['Unlimited decisions', 'Unlimited agents', '365-day retention', 'HIPAA BAA', 'Priority support'],
}

export default function Billing() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['billing-status'],
    queryFn: gwBillingStatus,
  })

  const plan = data?.plan ?? 'free'
  const used = data?.decisions_used ?? 0
  const limit = data?.decisions_limit ?? 50_000
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
  const status = data?.status ?? 'unknown'

  const statusColor =
    status === 'active' ? 'text-status-active' :
    status === 'trial' ? 'text-status-warning' :
    status === 'past_due' ? 'text-destructive' :
    'text-muted-foreground'

  return (
    <AccountLayout>
      <div className="p-6 max-w-3xl">
        <PageHeader
          title="Billing & Subscription"
          description="Manage your plan, usage, and payment details."
        />

        {isLoading ? (
          <Spinner />
        ) : error ? (
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            Could not load billing status. Check your gateway connection.
          </div>
        ) : (
          <div className="space-y-5">
            {/* Current plan card */}
            <div className="rounded-lg border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <CreditCard className="h-4 w-4 text-primary" />
                    <span className="font-space font-semibold">{PLAN_LABELS[plan] ?? plan}</span>
                  </div>
                  <p className={`text-xs capitalize ${statusColor}`}>
                    Status: {status}
                    {status === 'past_due' && ' — payment required'}
                  </p>
                </div>
                {data?.stripe_portal_url && (
                  <a
                    href={data.stripe_portal_url}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-secondary transition-colors"
                  >
                    Manage billing <ArrowRight className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>

              {/* Usage bar */}
              <div className="mb-4">
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="text-muted-foreground">Decisions used this period</span>
                  <span className={pct > 90 ? 'text-destructive font-medium' : pct > 70 ? 'text-status-warning' : 'text-muted-foreground'}>
                    {used.toLocaleString()} / {limit === -1 ? 'unlimited' : limit.toLocaleString()}
                  </span>
                </div>
                {limit !== -1 && (
                  <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${pct > 90 ? 'bg-destructive' : pct > 70 ? 'bg-status-warning' : 'bg-primary'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                )}
                {pct > 90 && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Approaching decision limit. Upgrade to avoid disruption.
                  </div>
                )}
              </div>

              {/* Plan features */}
              <div className="grid grid-cols-2 gap-y-2">
                {(PLAN_FEATURES[plan] ?? PLAN_FEATURES.free).map((f) => (
                  <div key={f} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle className="h-3.5 w-3.5 text-primary shrink-0" />
                    {f}
                  </div>
                ))}
              </div>

              {data?.billing_period_end && (
                <p className="mt-4 text-xs text-muted-foreground border-t border-border pt-3">
                  Period ends: {new Date(data.billing_period_end).toLocaleDateString()}
                </p>
              )}
            </div>

            {/* Upgrade CTAs (only show if not on pro) */}
            {plan !== 'pro' && plan !== 'hospital' && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-5">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="h-4 w-4 text-primary" />
                  <h3 className="font-space font-semibold text-sm">
                    {plan === 'free' || plan === 'trial' ? 'Upgrade to Scale' : 'Upgrade to Pro'}
                  </h3>
                </div>
                <p className="text-xs text-muted-foreground mb-4">
                  {plan === 'free' || plan === 'trial'
                    ? 'Get 5M decisions/month, 100 agents, and 90-day audit retention.'
                    : 'Get 25M decisions, HIPAA/SOC 2 compliance suite, and custom policy rules.'}
                </p>
                <a
                  href="/signup"
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  Upgrade plan <ArrowRight className="h-3.5 w-3.5" />
                </a>
              </div>
            )}

            {/* Invoice / support */}
            <div className="rounded-lg border border-border bg-card p-4 text-sm">
              <p className="font-medium mb-1">Need a custom invoice or enterprise pricing?</p>
              <p className="text-xs text-muted-foreground mb-2">
                For physical AI, drone fleets, or on-prem deployments — contact us directly.
              </p>
              <a href="mailto:hello@edoncore.com" className="text-xs text-primary hover:underline">
                hello@edoncore.com →
              </a>
            </div>
          </div>
        )}
      </div>
    </AccountLayout>
  )
}
