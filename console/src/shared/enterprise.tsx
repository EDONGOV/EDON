import type { LucideIcon } from 'lucide-react'
import type { GovernedSystem } from '../uiModel'

export function downloadJson(name: string, payload: Record<string, unknown>) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export function LifecycleBadge({ state }: { state: GovernedSystem['state'] }) {
  const tone = state === 'Live' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
    : state === 'Blocked' || state === 'Paused' ? 'text-red-400 border-red-500/30 bg-red-500/10'
    : state === 'Review' || state === 'Shadow' ? 'text-amber-400 border-amber-500/30 bg-amber-500/10'
    : 'text-muted-foreground border-border bg-muted/30'
  return <span className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold ${tone}`}>{state}</span>
}

export function EnterpriseHeader({ icon: Icon, title, subtitle }: { icon: LucideIcon; title: string; subtitle: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg border border-primary/25 bg-primary/10 flex items-center justify-center">
          <Icon size={16} className="text-primary" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
      </div>
    </div>
  )
}
