import { GitCompare } from 'lucide-react'
import { POLICY_DIFFS } from '../uiModel'
import { EnterpriseHeader } from '../shared/enterprise'

export function PolicyDiffViewerTab() {
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={GitCompare} title="Policy Diff Viewer" subtitle="Track policy changes, affected systems, expected decision impact, and rollback context." />
      <div className="space-y-3">
        {POLICY_DIFFS.map(diff => (
          <div key={diff.version} className="glass-card p-4 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-primary">{diff.version}</span>
              <span className="text-xs text-muted-foreground">{diff.changedAt} by {diff.changedBy}</span>
            </div>
            <p className="text-sm">{diff.change}</p>
            <p className="text-xs text-muted-foreground">Affected: {diff.affectedSystems.join(', ')}</p>
            <p className="text-xs text-emerald-400">{diff.shadowResult}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
