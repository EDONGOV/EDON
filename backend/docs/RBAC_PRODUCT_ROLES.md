# EDON Product Roles

Canonical enterprise roles:

- `super_admin`
  - permissions: `*` (tenant setup, emergency controls, identity, billing)
- `governance_admin`
  - permissions: `read`, `write`, `action`, `audit`, `export`, `approvals`, `api_keys`
- `security_admin`
  - permissions: `read`, `audit`, `export`, `api_keys`, `incidents`
- `operator`
  - permissions: `read`, `write`, `action`, `audit`
- `auditor`
  - permissions: `read`, `audit`, `export`
- `developer`
  - permissions: `read`, `write`, `action`
- `viewer`
  - permissions: `read`

Compatibility roles (legacy):

- `admin` -> treated as `super_admin`
- `user` -> treated as `developer` or `operator` depending on tenant mapping
- `agent` -> treated as `developer`
- `read_only` -> `viewer`

## Key creation defaults

- New enterprise API keys default to `viewer` or the least-privilege role
  selected in the onboarding contract.
- Existing legacy keys are normalized to tenant-scoped roles during startup
  migrations.

## Why this model

- Keeps least privilege explicit for enterprise deployments.
- Separates governance, security, and operations authority.
- Preserves compatibility for older console/API key flows while steering new
  deployments toward the enterprise role model.
