# Bypass Prevention Architecture

> **📘 Network Isolation Implementation**: See `NETWORK_ISOLATION_GUIDE.md` for detailed instructions on implementing Option B (network isolation) with Docker, firewall rules, or reverse proxy.

**Goal:** Prove "EDON is the only path to side effects."

---

## Architecture

```
┌─────────────┐
│  Clawdbot   │
│   (Agent)   │
└──────┬──────┘
       │
       │ ❌ Cannot import connectors
       │ ❌ No credentials
       │ ❌ No network access
       │
       │ ✅ Can only call POST /execute
       │
       ▼
┌─────────────────┐
│  EDON Gateway   │
│                 │
│  /execute       │ ← Only entry point
│                 │
│  Has:           │
│  - Connectors   │
│  - Credentials  │
│  - Network      │
└──────┬──────────┘
       │
       │ ✅ Only EDON can execute
       ▼
┌─────────────────┐
│  Tool Connectors│
│  (Sandboxed)    │
└─────────────────┘
```

---

## Bypass Prevention Mechanisms

### 1. Credential Containment

**What:** Tool credentials stored in EDON config, not accessible to agent.

**Example:**
- SMTP password in `edon_gateway/config/credentials.yaml`
- Agent process cannot read this file
- Only EDON Gateway process has access

**Production Implementation:**
```yaml
# edon_gateway/config/credentials.yaml
email:
  smtp_host: smtp.example.com
  smtp_user: edon@example.com
  smtp_password: ${EDON_SMTP_PASSWORD}  # From environment
```

### 2. Import Restriction

**What:** Agent cannot import EDON connector modules.

**Example:**
- Agent code runs in separate process/container
- EDON connectors not in agent's PYTHONPATH
- Agent gets `ImportError` if it tries to import

**Production Implementation:**
- Agent container: No EDON code
- EDON container: Has connectors + credentials
- Communication: HTTP API only

### 3. Network Isolation

**What:** Agent has no direct network access to external services.

**Example:**
- Agent cannot connect to SMTP servers
- Agent cannot connect to cloud storage APIs
- Only EDON Gateway has network access

**Production Implementation:**
- Agent container: Network policy blocks external connections
- EDON Gateway: Has network access to email/cloud services

### 4. Filesystem Sandbox

**What:** Filesystem operations restricted to sandbox directory.

**Example:**
- Path traversal prevented: `../../../etc/passwd` → Error
- Only `sandbox/` subdirectory writable
- Agent cannot write outside sandbox

**Production Implementation:**
```python
# FilesystemConnector enforces sandbox
if not str(file_path.resolve()).startswith(str(self.sandbox_dir.resolve())):
    raise ValueError(f"Path outside sandbox: {path}")
```

### 5. Execution Path

**What:** Only path to side effects is through EDON Gateway `/execute` endpoint.

**Example:**
- Agent must call `POST /execute`
- Cannot call tools directly
- All execution goes through governance

**Production Implementation:**
- Agent SDK only exposes `client.execute()` method
- No direct tool access
- All tool calls routed through gateway

---

## Test: Bypass Attempt

See `tests/test_bypass_attempt.py` for tests that verify:

1. ✅ Agent cannot import connectors directly
2. ✅ Agent cannot access credentials
3. ✅ Agent cannot write outside sandbox
4. ✅ Agent can only execute through EDON Gateway
5. ✅ EDON can execute (proves it's the only path)

---

## Production Truth Demo

**Scenario:** Agent tries to send email

**Without EDON (Blocked):**
```python
# Agent tries this (fails):
import smtplib
smtp = smtplib.SMTP('smtp.example.com')
smtp.login('user', 'password')  # ❌ No credentials
smtp.sendmail(...)  # ❌ No network access
```

**With EDON (Works):**
```python
# Agent does this (succeeds):
result = client.execute(
    tool="email",
    op="send",
    params={"recipients": [...], "subject": "...", "body": "..."}
)
# ✅ EDON has credentials
# ✅ EDON has network access
# ✅ Execution happens
```

---

## Sandboxed Connectors

### Email Connector

- **Sandbox:** `sandbox/emails/`
- **Draft:** Writes to `sandbox/emails/draft_{timestamp}.json`
- **Send:** Writes to `sandbox/emails/sent/{message_id}.json`
- **Production:** Would use SMTP/API with credentials from EDON config

### Filesystem Connector

- **Sandbox:** `sandbox/filesystem/`
- **Read/Write/Delete:** Only within sandbox directory
- **Path Traversal:** Prevented (raises ValueError)
- **Production:** Would use actual file system with permissions from EDON config

---

## Verification

Run bypass attempt tests:

```bash
pytest tests/test_bypass_attempt.py -v
```

Expected results:
- ✅ Agent cannot access connectors directly
- ✅ Agent cannot write outside sandbox
- ✅ Agent can only execute through EDON
- ✅ EDON can execute (proves it's the only path)
