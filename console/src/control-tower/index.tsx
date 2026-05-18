import { AlertCircle, Building2, CheckCircle2, FileDown, ServerCog } from 'lucide-react'
import { SYSTEM_REGISTRY } from '../uiModel'
import { downloadJson, EnterpriseHeader, LifecycleBadge } from '../shared/enterprise'

export function ControlTowerTab() {
  const live = SYSTEM_REGISTRY.filter(s => s.state === 'Live').length
  const shadow = SYSTEM_REGISTRY.filter(s => s.state === 'Shadow' || s.state === 'Review').length
  const blocked = SYSTEM_REGISTRY.filter(s => s.state === 'Blocked' || s.state === 'Paused').length
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={Building2} title="Hospital AI Control Tower" subtitle="System-wide state, risk, deployment readiness, and governance ownership." />
      <div className="grid gap-3 md:grid-cols-4">
        {[
          ['Active AI systems', SYSTEM_REGISTRY.length],
          ['Live clinical AI', live],
          ['Shadow / review', shadow],
          ['Blocked / paused', blocked],
        ].map(([label, value]) => (
          <div key={label} className="glass-card p-4">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold mt-1">{value}</p>
          </div>
        ))}
      </div>
      <SystemRegistryTable />
    </div>
  )
}

export function SystemRegistryTable() {
  return (
    <div className="glass-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border/50 flex items-center justify-between">
        <p className="text-sm font-semibold">AI System Registry</p>
        <button onClick={() => downloadJson('edon_system_registry.json', { systems: SYSTEM_REGISTRY })}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground">
          <FileDown size={12} /> Export
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/50 text-xs text-muted-foreground">
              <th className="text-left px-4 py-2.5">System</th>
              <th className="text-left px-4 py-2.5">Department</th>
              <th className="text-left px-4 py-2.5">State</th>
              <th className="text-left px-4 py-2.5">Mode</th>
              <th className="text-left px-4 py-2.5">Risk</th>
              <th className="text-left px-4 py-2.5">Policy Bundle</th>
            </tr>
          </thead>
          <tbody>
            {SYSTEM_REGISTRY.map(system => (
              <tr key={system.name} className="border-b border-border/30 last:border-0">
                <td className="px-4 py-3">
                  <p className="font-medium">{system.name}</p>
                  <p className="text-xs text-muted-foreground">{system.modelVersion} / {system.owner}</p>
                </td>
                <td className="px-4 py-3 text-xs">{system.department}</td>
                <td className="px-4 py-3"><LifecycleBadge state={system.state} /></td>
                <td className="px-4 py-3 text-xs capitalize">{system.deploymentMode}</td>
                <td className="px-4 py-3 font-mono text-xs">{system.riskScore.toFixed(2)}</td>
                <td className="px-4 py-3 font-mono text-xs">{system.policyBundle}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function DeploymentGatekeeperTab() {
  const checks = ['Shadow simulation passed', 'Bias evaluation complete', 'Drift within threshold', 'PHI compliance verified', 'Escalation tested', 'Audit replay valid', 'Policy bundle signed']
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={ServerCog} title="Deployment Gatekeeper" subtitle="Approve, deny, or extend shadow mode with evidence attached." />
      <div className="grid gap-4 lg:grid-cols-3">
        {SYSTEM_REGISTRY.map(system => (
          <div key={system.name} className="glass-card p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{system.name}</p>
                <p className="text-xs text-muted-foreground">{system.department} / {system.modelVersion}</p>
              </div>
              <LifecycleBadge state={system.state} />
            </div>
            <div className="space-y-1.5">
              {checks.map((check, idx) => (
                <div key={check} className="flex items-center gap-2 text-xs">
                  {idx < 5 || system.state === 'Live' ? <CheckCircle2 size={12} className="text-emerald-400" /> : <AlertCircle size={12} className="text-amber-400" />}
                  <span>{check}</span>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              {['Approve Go-Live', 'Deny', 'Extend Shadow', 'Export Packet'].map(action => (
                <button key={action} className="px-2 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40">
                  {action}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
