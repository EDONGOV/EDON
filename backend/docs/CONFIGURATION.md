# EDON Gateway - Configuration Guide

Complete guide to configuring EDON Gateway for production use.

---

## Quick Start

1. Copy `edon_gateway/env.example` to `.env`
2. Update values for your environment
3. Start the gateway: `docker compose up -d`

---

## Environment Variables

### Authentication & Security

#### `EDON_AUTH_ENABLED`
- **Type:** Boolean
- **Default:** `true`
- **Description:** Enable authentication middleware
- **Production:** Must be `true`

#### `EDON_API_TOKEN`
- **Type:** String
- **Default:** `your-secret-token`
- **Description:** API token for authentication
- **Production:** **CHANGE THIS!** Use a strong, random token

#### `EDON_TOKEN_BINDING_ENABLED`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Bind tokens to agent IDs for audit
- **Production:** Recommended `true`

---

### Credentials & Security

#### `EDON_CREDENTIALS_STRICT`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Fail closed if credentials not in database
- **Production:** **MUST be `true`**

#### `EDON_TOKEN_HARDENING`
- **Type:** Boolean
- **Default:** `true`
- **Description:** Never expose tokens to agents
- **Production:** Recommended `true`

#### `EDON_NETWORK_GATING`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Restrict access to external services
- **Production:** Optional but recommended

---

### Validation & Input

#### `EDON_VALIDATE_STRICT`
- **Type:** Boolean
- **Default:** `true`
- **Description:** Reject invalid input instead of sanitizing
- **Production:** Recommended `true`

---

### Database

#### `EDON_DATABASE_PATH`
- **Type:** String (file path)
- **Default:** `edon_gateway.db`
- **Description:** Path to SQLite database file
- **Production:** Use absolute path, ensure backups

---

### Logging

#### `EDON_LOG_LEVEL`
- **Type:** String
- **Default:** `INFO`
- **Options:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Description:** Logging verbosity
- **Production:** `INFO` or `WARNING`

#### `EDON_JSON_LOGGING`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Use structured JSON logging
- **Production:** Recommended `true` for log aggregation

---

### Monitoring

#### `EDON_METRICS_ENABLED`
- **Type:** Boolean
- **Default:** `true`
- **Description:** Enable metrics endpoint
- **Production:** Recommended `true`

#### `EDON_METRICS_PORT`
- **Type:** Integer
- **Default:** `9090`
- **Description:** Prometheus metrics port
- **Production:** Configure if using Prometheus

---

### Rate Limiting

#### `EDON_RATE_LIMIT_ENABLED`
- **Type:** Boolean
- **Default:** `true`
- **Description:** Enable rate limiting
- **Production:** Recommended `true`

#### `EDON_RATE_LIMIT_PER_MINUTE`
- **Type:** Integer
- **Default:** `60`
- **Description:** Max actions per minute per agent
- **Production:** Adjust based on needs

#### `EDON_RATE_LIMIT_PER_HOUR`
- **Type:** Integer
- **Default:** `1000`
- **Description:** Max actions per hour per agent
- **Production:** Adjust based on needs

---

### CORS

#### `EDON_CORS_ORIGINS`
- **Type:** String (comma-separated)
- **Default:** `*`
- **Description:** Allowed CORS origins
- **Production:** **Restrict to specific domains!** Example: `https://app.example.com,https://admin.example.com`

---

### Server

#### `EDON_HOST`
- **Type:** String
- **Default:** `0.0.0.0`
- **Description:** Server bind address
- **Production:** Usually `0.0.0.0`

#### `EDON_PORT`
- **Type:** Integer
- **Default:** `8000`
- **Description:** Server port
- **Production:** Use reverse proxy (nginx/traefik) in front

#### `EDON_WORKERS`
- **Type:** Integer
- **Default:** `1`
- **Description:** Number of worker processes
- **Production:** Set to CPU count (e.g., `4`)

---

### React UI

#### `EDON_BUILD_UI`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Build React UI in Docker
- **Production:** Set to `true` if building in Docker

#### `EDON_UI_REPO_URL`
- **Type:** String
- **Default:** `https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git`
- **Description:** React UI repository URL
- **Production:** Usually default

---

### Clawdbot Gateway

#### `CLAWDBOT_GATEWAY_URL`
- **Type:** String (URL)
- **Default:** `http://127.0.0.1:18789`
- **Description:** Clawdbot Gateway URL
- **Production:** Store in database via `/credentials/set`, not env var

#### `CLAWDBOT_GATEWAY_TOKEN`
- **Type:** String
- **Default:** (empty)
- **Description:** Clawdbot Gateway token
- **Production:** **Store in database only!** Never use env var in production

---

## Production Configuration Example

```bash
# Authentication
EDON_AUTH_ENABLED=true
EDON_API_TOKEN=your-strong-random-token-here
EDON_TOKEN_BINDING_ENABLED=true

# Security (REQUIRED)
EDON_CREDENTIALS_STRICT=true
EDON_TOKEN_HARDENING=true
EDON_VALIDATE_STRICT=true

# Logging
EDON_LOG_LEVEL=INFO
EDON_JSON_LOGGING=true

# CORS (RESTRICT!)
EDON_CORS_ORIGINS=https://app.example.com,https://admin.example.com

# Server
EDON_WORKERS=4

# Monitoring
EDON_METRICS_ENABLED=true
```

---

## Configuration Validation

The gateway validates configuration on startup and logs warnings for:
- Using default API token in production
- CORS allowing all origins in production
- Token hardening without strict credentials
- Missing required settings

---

## Best Practices

1. **Never commit `.env` files** - Use `.env.example` as template
2. **Use secrets management** - AWS Secrets Manager, HashiCorp Vault, etc.
3. **Restrict CORS** - Never use `*` in production
4. **Enable strict mode** - Always use `EDON_CREDENTIALS_STRICT=true`
5. **Use structured logging** - Enable `EDON_JSON_LOGGING=true`
6. **Store credentials in database** - Never use env vars for production credentials
7. **Use reverse proxy** - Nginx/Traefik for HTTPS and load balancing
8. **Enable monitoring** - Set up Prometheus/Grafana or similar

---

## Troubleshooting

### Configuration warnings on startup

Check the startup logs for warnings. Common issues:
- Default API token → Change `EDON_API_TOKEN`
- CORS allows all → Restrict `EDON_CORS_ORIGINS`
- Missing strict mode → Set `EDON_CREDENTIALS_STRICT=true`

### Credentials not found

If `EDON_CREDENTIALS_STRICT=true`:
- Credentials must be in database (use `/credentials/set` endpoint)
- Environment variables are ignored
- Gateway returns 503 if credential missing

---

*Last Updated: 2025-01-27*
