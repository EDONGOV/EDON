## Telegram Connect Codes (Post-Payment Flow)

This gateway supports short-lived **Telegram connect codes** so paid users can link their Telegram account without a desktop.

### Flow Summary
1. After payment, call `POST /integrations/telegram/connect-code` (auth required) to generate a code.
2. User sends the code to the Telegram bot (e.g., `EDON-7F3P2`).
3. Bot calls `POST /integrations/telegram/verify-code` with the code and a bot secret.
4. Gateway returns a **channel token** tied to the tenant. The bot uses it as `X-EDON-TOKEN`.

### Endpoints

**Create code (auth required)**
```
POST /integrations/telegram/connect-code
Headers: X-EDON-TOKEN: <tenant token or Clerk session>
Body: { "channel": "telegram" }
```
Response:
```
{ "code": "EDON-7F3P2", "expires_at": "...", "ttl_minutes": 10 }
```

**Verify code (bot secret required)**
```
POST /integrations/telegram/verify-code
Headers: X-EDON-BOT-SECRET: <EDON_TELEGRAM_BOT_SECRET>
Body: { "code": "EDON-7F3P2", "user_id": "123", "chat_id": "456", "username": "alice" }
```
Response:
```
{ "tenant_id": "tenant_...", "token": "<channel token>", "channel": "telegram" }
```

### Required Env Vars

Gateway:
```
EDON_TELEGRAM_BOT_SECRET=your-shared-secret
EDON_TELEGRAM_CONNECT_TTL_MIN=10
```

Telegram bot process:
```
EDON_TELEGRAM_BOT_SECRET=your-shared-secret
```

### Bot Implementation

The bot should store the returned `token` and use it on every EDON request:
```
X-EDON-TOKEN: <channel token>
```

This token is tenant-scoped and works the same as an API key for auth.
