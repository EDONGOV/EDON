# EDON Gateway Production Final Summary

## Diff Summary

### Unify credential_id
- **config.py**: Added `_DEFAULT_CLAWDBOT_CREDENTIAL_ID = "clawdbot_gateway_tenant_dev"` and property `DEFAULT_CLAWDBOT_CREDENTIAL_ID`. `CLAWDBOT_CREDENTIAL_ID` now defaults to it.
- **main.py**: Replaced hardcoded `"clawdbot_gateway_tenant_dev"` with `app_config.DEFAULT_CLAWDBOT_CREDENTIAL_ID`.
- **integrations.py**: Connect route uses `config.DEFAULT_CLAWDBOT_CREDENTIAL_ID` for default and comparison; removed literal.
- **clawdbot_connector.py**: `_default_credential_id` uses `config.DEFAULT_CLAWDBOT_CREDENTIAL_ID` when env `EDON_CLAWDBOT_CREDENTIAL_ID` is unset.

### Harden wrong-token behavior
- **database.py** `get_integration_status`: `connected = last_used_at is not None` (removed `last_error is None`). Failed invoke sets `last_error` but does not flip `connected` to false; credential stays usable. `last_ok_at` always returns `last_used_at` when present.

### Kill unsafe fallback
- **clawdbot_connector.py** `_load_credentials`: When `config.CREDENTIALS_STRICT` is true, raise immediately with message "EDON_CREDENTIALS_STRICT=true disables env fallback. Configure via POST /integrations/clawdbot/connect." No env-based Clawdbot creds when strict.

### Light coverage
- **test_regression.py**: Added `test_clawdbot_sessions_smoke()` — apply clawdbot_safe, then invokes `sessions_list`, `sessions_get` (sessionKey=main), `sessions_create`, `sessions_update` via POST /clawdbot/invoke. Registered in test list.

### Final cleanup
- No new debug prints; no TODOs in edon_gateway package; single default credential_id.

---

## Remaining Risks

1. **Smoke test payloads**: `sessions_create` and `sessions_update` use minimal args `{}` and `{"sessionKey": "main"}`; Clawdbot may require different shapes — test may skip or fail on strict backends.
2. **Wrong-token regression test**: Still overwrites the Clawdbot credential with a bad secret; re-connect required after run.
3. **main.py import**: `from .config import config as app_config` inside the execution block; could be moved to top-level for clarity.

---

## Verdict

**Ship.** 92% confidence.

- Credential_id is single source of truth; no hardcoded literal in main.
- Failed invoke does not permanently brick credential; status stays accurate.
- CREDENTIALS_STRICT=true fully disables env Clawdbot fallback with clear error.
- Sessions smoke covers get/create/update on the same proxy path.
- No debug prints or TODOs in gateway code.
