import { Network, Shield } from 'lucide-react'
import { SYSTEM_REGISTRY } from '../uiModel'
import { EnterpriseHeader } from '../shared/enterprise'

export function ImpactCenterTab() {
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={Network} title="Impact Center" subtitle="Blast-radius simulation for compromise, policy failure, and data exposure scenarios." />
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="glass-card p-4">
          <p className="text-sm font-semibold mb-3">Blast Radius Map</p>
          <div className="grid grid-cols-3 gap-3 text-center text-xs">
            {SYSTEM_REGISTRY.map(system => (
              <div key={system.name} className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="font-semibold">{system.department}</p>
                <p className={system.riskScore > 0.4 ? 'text-amber-400' : 'text-emerald-400'}>Exposure {system.riskScore.toFixed(2)}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="glass-card p-4 space-y-3">
          <p className="text-sm font-semibold">Mitigation Proposals</p>
          {['Isolate research warehouse connector', 'Force shadow mode for external trial registry calls', 'Require signed PHI export destination', 'Reduce ambient note writeback scope'].map(item => (
            <div key={item} className="flex items-center gap-2 text-xs">
              <Shield size={12} className="text-primary" />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
