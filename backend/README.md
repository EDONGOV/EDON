# EDON Gateway

**Purpose**: Backend API gateway that connects to clawdbots/agents and enforces security policies.

This is the **core backend component** that:
- Connects to user's clawdbots/AI agents
- Enforces security policies and governance
- Processes all agent actions through a security layer
- Provides audit logging and metrics
- Manages subscriptions and billing (Stripe webhooks)

## Architecture

```
Clawdbot/Agent → EDON Gateway → Tools/Connectors
```

Clawdbot/agents never call tools directly. All tool execution goes through `/execute` endpoint, which enforces security policies before allowing actions.

## Full Stack Context

This gateway is part of a three-component system:

1. **edon-sentinel-core** (`D:\dev\edon-sentinel-core`): Public website where users sign up and pay
2. **edon-agent-ui** (`C:\Users\cjbig\Desktop\edon-agent-ui`): Agent Console where users monitor their agents
3. **edon_gateway** (this): Backend API that processes agent actions

See `../STARTUP_GUIDE.md` for full stack startup instructions.

## UI

The EDON Gateway ships **API only**; it does not ship a user interface.

User-facing UI lives in a separate project:
- **edon-agent-ui**

The gateway exposes a JSON/HTTP API consumed by external UIs. The UI (edon-agent-ui) communicates with the gateway over HTTP using the same auth header (`X-EDON-TOKEN`).

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Gateway

```bash
python -m edon_gateway.main
```

Gateway will start on `http://localhost:8000`

### API Endpoints

**Core Endpoints:**
- `POST /execute` - Execute action through governance
- `POST /edon/invoke` - Drop-in replacement for Clawdbot's /tools/invoke (adoption milestone)
- `POST /intent/set` - Set intent contract
- `GET /intent/get` - Get intent contract
- `GET /audit/query` - Query audit logs
- `GET /health` - Health check (shows active policy preset)

**Policy Presets:**
- `GET /policies/presets` - List all available policy presets
- `POST /policies/apply` - Apply a policy preset (personal_safe, work_safe, ops_admin)

**Metrics:**
- `GET /metrics` - Prometheus metrics (for ops teams and standard tooling)
- `GET /stats` - JSON stats (for UI, demos, and quick debugging)

See `../edon_demo/CLAWDBOT_INTEGRATION.md` for full API specification.

## Real Connectors (Sandboxed)

### Email Connector

- **Location:** `edon_gateway/connectors/email_connector.py`
- **Sandbox:** `sandbox/emails/`
- **Operations:** `draft`, `send`
- **Proof:** Writes to files instead of actually sending (proves execution path)

### Filesystem Connector

- **Location:** `edon_gateway/connectors/filesystem_connector.py`
- **Sandbox:** `sandbox/filesystem/`
- **Operations:** `read_file`, `write_file`, `delete_file`
- **Security:** Path traversal prevented, only sandbox writable

## Bypass Prevention

See `BYPASS_PREVENTION.md` for architecture details.

**Key Point:** Agent cannot execute tools directly. Only EDON Gateway can execute through connectors.

## Testing

### Test Gateway

```bash
python edon_gateway/test_gateway.py
```

### Test Bypass Prevention

```bash
pytest tests/test_bypass_attempt.py -v
```

## Development Status

**Phase A (Current):** 
- ✅ Basic API structure
- ✅ Real email connector (sandboxed)
- ✅ Real filesystem connector (sandboxed)
- ✅ Bypass prevention tests

**Phase B (Next):** Persistence, authentication, security  
**Phase C (Future):** Observability, performance optimization

## Sandbox Directory Structure

```
sandbox/
  emails/
    draft_*.json       # Email drafts
    sent/
      msg_*.json      # Sent emails
  filesystem/
    *.txt             # Written files
```

All operations are sandboxed - no real side effects in Phase A.
