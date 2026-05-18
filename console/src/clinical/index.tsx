import { ClipboardList, Eye, Stethoscope } from 'lucide-react'
import { EnterpriseHeader } from '../shared/enterprise'

export function ClinicalSummaryTab() {
  const sources = ['FHIR verified EHR', 'lab system', 'imaging summary', 'medication history']
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={Stethoscope} title="Patient AI Summary" subtitle="Clinical-facing AI output with governance status kept visible." />
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="glass-card p-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono px-2 py-1 rounded bg-muted/50 border border-border">Patient: PT-48A9</span>
            <span className="px-2 py-1 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400">Oncology survivorship</span>
            <span className="px-2 py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">2 active AI systems</span>
          </div>
          <div>
            <p className="text-xs uppercase text-muted-foreground font-semibold mb-2">AI-generated summary</p>
            <p className="text-sm leading-relaxed">
              Patient shows early indicators of cardiotoxicity risk based on longitudinal anthracycline exposure and troponin trend. Clinician review is required before any workflow action is routed.
            </p>
          </div>
          <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-300">
            Missing 6-month echo data. Suggested workflow action: verify manually or route an echo order request through policy-controlled approval.
          </div>
        </div>
        <div className="glass-card p-4 space-y-3">
          <p className="text-xs uppercase text-muted-foreground font-semibold">EDON Trust Layer</p>
          {[
            ['Confidence', '0.89'],
            ['Policy status', 'PASS'],
            ['PHI handling', 'COMPLIANT'],
            ['Model version', 'CardioRisk-v3.2 locked'],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between border-b border-border/40 pb-2 last:border-0">
              <span className="text-xs text-muted-foreground">{label}</span>
              <span className="text-xs font-semibold">{value}</span>
            </div>
          ))}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {sources.map(source => <span key={source} className="px-2 py-0.5 rounded border border-border bg-muted/40 text-[10px] text-muted-foreground">{source}</span>)}
          </div>
        </div>
      </div>
    </div>
  )
}

export function ClinicalExplainTab() {
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={Eye} title="Explain This Decision" subtitle="Traceable reasoning without exposing raw policy complexity by default." />
      <div className="grid gap-4 lg:grid-cols-3">
        {[
          ['Feature attribution', 'Troponin trend, anthracycline exposure, prior echo interval, age-adjusted baseline.'],
          ['Timeline', 'Risk increased after latest lab trend; imaging gap keeps action in review-required mode.'],
          ['Similar cases', 'De-identified historical cohort shows elevated monitoring yield under same pattern.'],
        ].map(([title, body]) => (
          <div key={title} className="glass-card p-4">
            <p className="text-sm font-semibold mb-2">{title}</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{body}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ClinicalActionsTab() {
  const actions = ['Recommend consult review', 'Suggest monitoring workflow', 'Prepare lab request', 'Escalate case']
  return (
    <div className="space-y-4">
      <EnterpriseHeader icon={ClipboardList} title="Governed Action Panel" subtitle="Clinicians see workflow options; EDON routes every action through policy before execution." />
      <div className="glass-card overflow-hidden">
        {actions.map(action => (
          <div key={action} className="flex flex-wrap items-center gap-3 border-b border-border/40 px-4 py-3 last:border-0">
            <span className="text-sm font-medium">{action}</span>
            <span className="ml-auto text-xs text-muted-foreground">Policy-controlled action</span>
            <button className="px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-semibold">Route</button>
          </div>
        ))}
      </div>
    </div>
  )
}
