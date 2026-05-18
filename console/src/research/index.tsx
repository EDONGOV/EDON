import { CheckCircle2, Microscope, Radio } from 'lucide-react'
import { EnterpriseHeader } from '../shared/enterprise'

export function ResearchExperimentsTab() {
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={Microscope} title="Experiment Workspace" subtitle="Research systems can be tested under governed data and action constraints." />
      <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr_0.8fr]">
        <div className="glass-card p-4 space-y-2">
          <p className="text-sm font-semibold">Dataset / Cohort Access</p>
          {['EHR cohort', 'survivorship cohort', 'imaging sets', 'genomic subsets'].map(item => <div key={item} className="text-xs px-2 py-2 rounded border border-border bg-muted/30">{item}</div>)}
        </div>
        <div className="glass-card p-4">
          <p className="text-sm font-semibold mb-3">Pipeline Configuration</p>
          <div className="h-44 rounded-lg border border-dashed border-border bg-muted/20 flex items-center justify-center text-xs text-muted-foreground">
            Model builder, feature selection, and training logs
          </div>
        </div>
        <div className="glass-card p-4 space-y-2">
          <p className="text-sm font-semibold">Governance Status</p>
          {['Data access: APPROVED', 'PHI scope: MASKED', 'No autonomous writeback', 'No uncontrolled PHI export'].map(item => <div key={item} className="text-xs text-emerald-400">{item}</div>)}
        </div>
      </div>
    </div>
  )
}

export function ShadowSimulationTab() {
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={Radio} title="Shadow Simulation" subtitle="Run governed simulations against historical and counterfactual trajectories." />
      <div className="glass-card p-4 grid gap-4 md:grid-cols-4">
        {[
          ['Trajectories', '200,000'],
          ['Sensitivity', '91.4%'],
          ['Specificity', '87.2%'],
          ['Drift risk', 'Medium'],
        ].map(([label, value]) => (
          <div key={label}>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-xl font-semibold mt-1">{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ReadinessTab() {
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={CheckCircle2} title="Deployment Readiness Score" subtitle="Evidence summary for research, security, IRB, and governance review." />
      <div className="grid gap-4 md:grid-cols-3">
        {[
          ['Safety Score', '82/100', 'text-amber-400'],
          ['Governance Score', '91/100', 'text-emerald-400'],
          ['Recommendation', 'Shadow-approved only', 'text-blue-400'],
        ].map(([label, value, color]) => (
          <div key={label} className="glass-card p-4">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={`text-xl font-semibold mt-1 ${color}`}>{value}</p>
          </div>
        ))}
      </div>
      <div className="glass-card p-4 text-sm text-muted-foreground">
        Model fails under sparse imaging conditions. Escalation logic is too aggressive in pediatric subgroup. Policy compliance remains stable.
      </div>
    </div>
  )
}
