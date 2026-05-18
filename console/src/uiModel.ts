export type ConsoleRole = 'admin' | 'research' | 'clinical'

export type LifecycleState =
  | 'Draft'
  | 'Research'
  | 'Shadow'
  | 'Review'
  | 'Approved'
  | 'Live'
  | 'Paused'
  | 'Blocked'
  | 'Retired'

export interface GovernedSystem {
  name: string
  owner: string
  department: string
  modelVersion: string
  dataClasses: string[]
  connectedTools: string[]
  deploymentMode: 'shadow' | 'enforced' | 'advisory'
  state: LifecycleState
  riskScore: number
  policyBundle: string
  lastShadowRun: string
  lastAuditVerification: string
}

export interface PolicyDiffRecord {
  version: string
  changedBy: string
  changedAt: string
  change: string
  affectedSystems: string[]
  expectedImpact: string
  shadowResult: string
}

export const ROLE_LABELS: Record<ConsoleRole, string> = {
  admin: 'Admin Control Tower',
  research: 'Research Console',
  clinical: 'Clinical View',
}

export const ROLE_DEFAULT_TAB: Record<ConsoleRole, string> = {
  admin: 'control_tower',
  research: 'research_experiments',
  clinical: 'clinical_summary',
}

export const SYSTEM_REGISTRY: GovernedSystem[] = [
  {
    name: 'CardioRisk Copilot',
    owner: 'Clinical AI Office',
    department: 'Oncology',
    modelVersion: 'CardioRisk-v3.2',
    dataClasses: ['PHI', 'labs', 'imaging summaries'],
    connectedTools: ['FHIR EHR', 'lab feed', 'echo scheduler'],
    deploymentMode: 'shadow',
    state: 'Review',
    riskScore: 0.31,
    policyBundle: 'healthcare-core-v12',
    lastShadowRun: '2026-05-09 21:14',
    lastAuditVerification: '2026-05-10 08:25',
  },
  {
    name: 'Ambient Note Guard',
    owner: 'CMIO',
    department: 'Emergency Medicine',
    modelVersion: 'AmbientNote-v2.8',
    dataClasses: ['PHI', 'voice transcript', 'clinical note'],
    connectedTools: ['scribe vendor', 'EHR draft note'],
    deploymentMode: 'enforced',
    state: 'Live',
    riskScore: 0.18,
    policyBundle: 'ambient-clinical-v5',
    lastShadowRun: '2026-05-08 17:40',
    lastAuditVerification: '2026-05-10 08:22',
  },
  {
    name: 'Trial Match Agent',
    owner: 'Research Ops',
    department: 'Clinical Research',
    modelVersion: 'TrialMatch-v1.9',
    dataClasses: ['PHI', 'genomics', 'cohort metadata'],
    connectedTools: ['FHIR EHR', 'trial registry', 'research warehouse'],
    deploymentMode: 'advisory',
    state: 'Shadow',
    riskScore: 0.44,
    policyBundle: 'research-shadow-v7',
    lastShadowRun: '2026-05-10 06:10',
    lastAuditVerification: '2026-05-10 08:20',
  },
]

export const POLICY_DIFFS: PolicyDiffRecord[] = [
  {
    version: 'healthcare-core-v12',
    changedBy: 'Policy Admin',
    changedAt: '2026-05-10 07:45',
    change: 'Added explicit PHI export invariant for external destinations.',
    affectedSystems: ['CardioRisk Copilot', 'Trial Match Agent'],
    expectedImpact: 'Blocks uncontrolled export attempts and routes approved research exports to review.',
    shadowResult: '0.8% additional escalations, no critical regressions.',
  },
  {
    version: 'ambient-clinical-v5',
    changedBy: 'CMIO',
    changedAt: '2026-05-09 16:30',
    change: 'Lowered confidence threshold for note finalization; final clinician attestation still required.',
    affectedSystems: ['Ambient Note Guard'],
    expectedImpact: 'More generated drafts reach clinician review, no direct order execution.',
    shadowResult: 'PASS: audit replay valid across 18,420 note events.',
  },
]
