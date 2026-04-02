# EDON Product Roles

Canonical product roles:

- `user` (default for console/API keys)
  - permissions: `read`, `write`, `action`, `audit`, `api_keys`
- `operator`
  - permissions: `read`, `write`, `action`, `audit`, `api_keys`
- `admin`
  - permissions: `*` (all)

Compatibility roles (legacy):

- `agent` -> treated as `user`
- `read_only` -> `read`, `audit`

## Key creation defaults

- New API keys default to role `user` in both SQLite and PostgreSQL backends.
- Existing legacy keys with role `agent` are normalized to `user` during startup migrations.

## Why this model

- Keeps console users fully functional by default (`audit` + controlled writes).
- Preserves existing integrations still using legacy `agent`.
- Provides clean operator/admin escalation when needed.
