import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpen, CheckCircle, Loader2, Shield, Zap, Users, Headphones, Settings2, ChevronRight } from 'lucide-react'
import AccountLayout, { PageHeader, Spinner, EmptyState } from './AccountLayout'
import { gwPolicyPacks, gwApplyPack } from '../../lib/gateway'
import { toast } from 'sonner'

const PACK_ICONS: Record<string, typeof Shield> = {
  casual_user: Users,
  market_analyst: Zap,
  ops_commander: Settings2,
  founder_mode: ChevronRight,
  helpdesk: Headphones,
  autonomy_mode: Shield,
}

const RISK_COLORS: Record<string, string> = {
  low: 'text-status-active border-status-active/20 bg-status-active/5',
  medium: 'text-status-warning border-status-warning/20 bg-status-warning/5',
  high: 'text-destructive border-destructive/20 bg-destructive/5',
}

export default function Policies() {
  const qc = useQueryClient()
  const [applying, setApplying] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['policy-packs'],
    queryFn: gwPolicyPacks,
  })

  const applyMutation = useMutation({
    mutationFn: (name: string) => gwApplyPack(name),
    onMutate: (name) => setApplying(name),
    onSuccess: (_, name) => {
      toast.success(`Policy pack "${name}" applied.`)
      qc.invalidateQueries({ queryKey: ['policy-packs'] })
      setApplying(null)
    },
    onError: (err: Error) => {
      toast.error(err.message)
      setApplying(null)
    },
  })

  const packs = data?.packs ?? []

  return (
    <AccountLayout>
      <div className="p-6 max-w-5xl">
        <PageHeader
          title="Policy Packs"
          description="Apply a governance preset to your agent fleet instantly."
        />

        {isLoading ? (
          <Spinner />
        ) : packs.length === 0 ? (
          <div className="rounded-lg border border-border bg-card">
            <EmptyState message="No policy packs available. Check gateway connection." />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {packs.map((pack) => {
              const Icon = PACK_ICONS[pack.name] ?? BookOpen
              const isActive = pack.active
              const riskColor = RISK_COLORS[pack.risk_level ?? 'low'] ?? RISK_COLORS.low

              return (
                <div
                  key={pack.name}
                  className={`rounded-lg border bg-card p-5 flex flex-col transition-colors ${
                    isActive ? 'border-primary ring-1 ring-primary/30' : 'border-border hover:border-border/70'
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className={`h-9 w-9 rounded-lg flex items-center justify-center ${isActive ? 'bg-primary/20' : 'bg-secondary'}`}>
                      <Icon className={`h-4.5 w-4.5 ${isActive ? 'text-primary' : 'text-muted-foreground'}`} />
                    </div>
                    {isActive && (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-primary">
                        <CheckCircle className="h-3 w-3" /> Active
                      </span>
                    )}
                  </div>

                  <h3 className="font-space font-semibold text-sm mb-1">{pack.label || pack.name}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-3 flex-1">{pack.description}</p>

                  {pack.risk_level && (
                    <div className={`mb-3 self-start rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${riskColor}`}>
                      {pack.risk_level} risk
                    </div>
                  )}

                  <button
                    onClick={() => applyMutation.mutate(pack.name)}
                    disabled={isActive || applying === pack.name}
                    className={`w-full rounded-md px-3 py-2 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${
                      isActive
                        ? 'bg-primary/10 text-primary cursor-default'
                        : 'border border-border hover:bg-secondary disabled:opacity-50'
                    }`}
                  >
                    {applying === pack.name ? (
                      <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Applying…</>
                    ) : isActive ? (
                      <><CheckCircle className="h-3.5 w-3.5" /> Currently active</>
                    ) : (
                      'Apply pack'
                    )}
                  </button>
                </div>
              )
            })}
          </div>
        )}

        <div className="mt-8 rounded-lg border border-border/50 bg-card/50 p-5">
          <h3 className="font-space font-semibold text-sm mb-2 flex items-center gap-2">
            <Settings2 className="h-4 w-4 text-primary" /> Custom policy rules
          </h3>
          <p className="text-xs text-muted-foreground mb-3">
            Need custom allow/block rules beyond presets? Custom rules are available on the Pro plan.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-muted-foreground">
            {[
              'Block access to specific tools by name',
              'Rate limits per agent or time window',
              'Data exfiltration pattern detection',
              'Out-of-hours restrictions',
              'Require human approval for specific actions',
              'Custom anomaly thresholds',
            ].map((r) => (
              <div key={r} className="flex items-center gap-2">
                <CheckCircle className="h-3.5 w-3.5 text-primary shrink-0" />
                {r}
              </div>
            ))}
          </div>
          <a
            href="/account/billing"
            className="mt-4 inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            Upgrade for custom rules →
          </a>
        </div>
      </div>
    </AccountLayout>
  )
}
