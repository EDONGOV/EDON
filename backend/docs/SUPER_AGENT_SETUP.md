# Super-Agent Setup — Edonbot/Telegram + EDON

This guide wires **Brave Search**, **Gmail**, **Google Calendar**, **Gemini**, **ElevenLabs**, **GitHub**, **Polygon**, **FMP**, **NewsAPI**, and **Clawdbot Gateway** into the EDON Gateway so your Edonbot/Telegram bot can act as a super agent (research, email, calendar, images, voice, code, markets, news, browser, chat platforms).

---

## Architecture

- **Edonbot/Telegram** → user chats with the bot.
- **Bot** → sends actions to EDON Gateway `POST /execute` (with `X-EDON-TOKEN`).
- **EDON** → evaluates with governor, then runs the right connector (Brave Search, Gmail, etc.).
- **Credentials** → stored in EDON (DB or env); the bot never sees API keys.

**Base requirements (all services):**
- `TELEGRAM_BOT_TOKEN` for the Edonbot worker.
- `EDON_TELEGRAM_BOT_SECRET` for connect-code verification.
- `EDON_CONNECT_BASE_URL` for OAuth redirect URLs (Gmail/Calendar).

---

## 0. Clawdbot Gateway (browser + chat platforms)

Clawdbot Gateway is the access point for browser automation and other chat platforms (Slack/Discord/Signal/WhatsApp/Line, depending on your Clawdbot build). EDON never exposes these credentials to the bot; EDON calls Clawdbot on your behalf.

**Env (dev fallback):**
```bash
CLAWDBOT_GATEWAY_URL=https://your-clawdbot.example.com
CLAWDBOT_GATEWAY_TOKEN=your-clawdbot-token
```

**Or DB (recommended):** call `POST /integrations/clawdbot/connect` to store gateway credentials per tenant.

---

## 1. Brave Search (web research)

**Get key:** [Brave Search API](https://api.search.brave.com/) → create app → copy **API key**.

**Env (dev):**
```bash
BRAVE_SEARCH_API_KEY=your-brave-api-key
```

**Or store in DB** via your credentials API (tool_name: `brave_search`, credential_data: `{"api_key": "..."}`).

**Execute from Edonbot/agent:**
```json
{
  "action": {
    "tool": "brave_search",
    "op": "search",
    "params": {
      "q": "latest news on AI",
      "count": 10,
      "country": "US",
      "freshness": "pd"
    }
  },
  "agent_id": "edonbot-001"
}
```

**Ops:** `search` (params: `q`, `count`, `country`, `freshness`).

---

## 2. Gmail (inbox / send)

**Auth:** OAuth2 access token **or refresh token** (recommended for production).  
If you store `refresh_token` + `client_id` + `client_secret`, EDON will auto-refresh and persist `access_token` + `expires_at`.

**Env (dev):**
```bash
GMAIL_ACCESS_TOKEN=ya29....
GMAIL_REFRESH_TOKEN=1//...
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_TOKEN_URI=https://oauth2.googleapis.com/token
GMAIL_EXPIRES_AT=1710000000
```

**Or DB:** credential_data example (tool_name: `gmail`):
```json
{
  "access_token": "ya29....",
  "refresh_token": "1//...",
  "client_id": "your-client-id",
  "client_secret": "your-client-secret",
  "token_uri": "https://oauth2.googleapis.com/token",
  "expires_at": 1710000000
}
```

**Execute:**
- **List messages:** `op: "list_messages"`, params: `max_results`, `q` (Gmail query), `label_ids`.
- **Get message:** `op: "get_message"`, params: `message_id`, `format`.
- **Send:** `op: "send"`, params: `to` or `recipients`, `subject`, `body`.

---

## 3. Google Calendar (events)

**Auth:** Same as Gmail — OAuth2 access token or refresh token with Calendar API scope.

**Env (dev):**
```bash
GOOGLE_CALENDAR_ACCESS_TOKEN=ya29....
GOOGLE_CALENDAR_REFRESH_TOKEN=1//...
GOOGLE_CALENDAR_CLIENT_ID=your-client-id
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
GOOGLE_CALENDAR_TOKEN_URI=https://oauth2.googleapis.com/token
GOOGLE_CALENDAR_EXPIRES_AT=1710000000
```

**Or DB:** credential_data example (tool_name: `google_calendar`):
```json
{
  "access_token": "ya29....",
  "refresh_token": "1//...",
  "client_id": "your-client-id",
  "client_secret": "your-client-secret",
  "token_uri": "https://oauth2.googleapis.com/token",
  "expires_at": 1710000000,
  "calendar_id": "primary"
}
```

**Execute:**
- **List events:** `op: "list_events"`, params: `calendar_id`, `time_min`, `time_max`, `max_results`, `single_events`.
- **Create event:** `op: "create_event"`, params: `calendar_id`, `summary`, `description`, `start`, `end`, `location` (start/end in RFC3339 or date).

---

## 4. Gemini (image + voice)

**Get key:** Google AI Studio → create API key.

**Env (dev):**
```bash
GEMINI_API_KEY=your-google-ai-studio-key
```

**Or DB:** credential_data: `{"api_key": "..."}` (tool_name: `gemini`).

**Execute (image):**
```json
{
  "action": {
    "tool": "gemini",
    "op": "generate_image",
    "params": {
      "prompt": "A futuristic warehouse robot loading pallets",
      "sample_count": 1,
      "output_mime_type": "image/png"
    }
  }
}
```

**Execute (voice / TTS):**
```json
{
  "action": {
    "tool": "gemini",
    "op": "text_to_speech",
    "params": {
      "text": "Your order is confirmed.",
      "language_code": "en-US",
      "voice_name": "en-US-Standard-A",
      "audio_encoding": "MP3"
    }
  }
}
```

---

## 5. ElevenLabs (voice / TTS — optional)

**Get key:** [ElevenLabs](https://elevenlabs.io/) → Profile → API key.

**Env (dev):**
```bash
ELEVENLABS_API_KEY=your-xi-api-key
```

**Or DB:** credential_data: `{"api_key": "..."}` (tool_name: `elevenlabs`).

**Execute:**
- **Text-to-speech:** `op: "text_to_speech"`, params: `text`, `voice_id`, `model_id`, `voice_settings`.
- **List voices:** `op: "list_voices"`.

---

## 6. GitHub (repos, files, issues)

---

## 7. Polygon (market data)

**Get key:** polygon.io → API Keys.

**Env (dev):**
```bash
POLYGON_API_KEY=your-polygon-key
```

**Or DB:** credential_data: `{"api_key": "..."}` (tool_name: `polygon`).

**Execute (prev close):**
```json
{
  "action": {
    "tool": "polygon",
    "op": "prev_close",
    "params": {
      "ticker": "AAPL",
      "adjusted": true
    }
  }
}
```

**Execute (ticker details):**
```json
{
  "action": {
    "tool": "polygon",
    "op": "ticker_details",
    "params": {
      "ticker": "AAPL"
    }
  }
}
```

---

## 8. FMP (Financial Modeling Prep)

**Get key:** financialmodelingprep.com → API Keys.

**Env (dev):**
```bash
FMP_API_KEY=your-fmp-key
```

**Or DB:** credential_data: `{"api_key": "..."}` (tool_name: `fmp`).

**Execute (quote):**
```json
{
  "action": {
    "tool": "fmp",
    "op": "quote",
    "params": {
      "symbol": "AAPL"
    }
  }
}
```

**Execute (stock news):**
```json
{
  "action": {
    "tool": "fmp",
    "op": "stock_news",
    "params": {
      "tickers": "AAPL,MSFT",
      "limit": 10
    }
  }
}
```

---

## 9. NewsAPI (headlines + search)

**Get key:** newsapi.org → API Keys.

**Env (dev):**
```bash
NEWSAPI_KEY=your-newsapi-key
```

**Or DB:** credential_data: `{"api_key": "..."}` (tool_name: `newsapi`).

**Execute (search):**
```json
{
  "action": {
    "tool": "newsapi",
    "op": "search",
    "params": {
      "q": "AI regulation",
      "language": "en",
      "sort_by": "publishedAt",
      "page_size": 20
    }
  }
}
```

**Execute (top headlines):**
```json
{
  "action": {
    "tool": "newsapi",
    "op": "top_headlines",
    "params": {
      "country": "us",
      "category": "business",
      "page_size": 20
    }
  }
}
```

---

## 10. Home Assistant (smart home)

**Auth:** Long-lived access token (recommended), or OAuth2 if you run a public app.

**Env (dev):**
```bash
HOME_ASSISTANT_BASE_URL=https://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your-long-lived-access-token

# Optional OAuth
HOME_ASSISTANT_CLIENT_ID=your-client-id
HOME_ASSISTANT_CLIENT_SECRET=your-client-secret
```

**Or DB:** credential_data example (tool_name: `home_assistant`):
```json
{
  "base_url": "https://homeassistant.local:8123",
  "token": "your-long-lived-access-token",
  "access_token": "",
  "refresh_token": "",
  "client_id": "",
  "client_secret": "",
  "token_url": "",
  "expires_at": 0
}
```

**Execute:**
- **List entities:** `op: "list_entities"`
- **Get state:** `op: "get_state"`, params: `entity_id`
- **Call service:** `op: "call_service"`, params: `domain`, `service`, `entity_id`, `service_data`

**Get token:** GitHub → Settings → Developer settings → Personal access tokens (repo scope).

**Env (dev):**
```bash
GITHUB_TOKEN=ghp_....
```

**Or DB:** credential_data: `{"token": "..."}` (tool_name: `github`).

**Execute:**
- **List repos:** `op: "list_repos"`, params: `visibility`, `per_page`.
- **Get file:** `op: "get_file"`, params: `owner`, `repo`, `path`.
- **Create issue:** `op: "create_issue"`, params: `owner`, `repo`, `title`, `body`, `labels`.

---

## Intent scope (governor)

For the governor to **allow** these tools, the intent scope must include them. Example intent when setting up the session:

```json
{
  "objective": "Super agent: search, email, calendar, images, voice, github, markets, news",
  "scope": {
    "brave_search": ["search"],
    "gmail": ["list_messages", "get_message", "send"],
    "google_calendar": ["list_events", "create_event"],
    "gemini": ["generate_image", "text_to_speech"],
    "elevenlabs": ["text_to_speech", "list_voices"],
    "github": ["list_repos", "get_file", "create_issue"],
    "polygon": ["prev_close", "ticker_details"],
    "fmp": ["quote", "stock_news"],
    "newsapi": ["search", "top_headlines"]
  },
  "constraints": {},
  "risk_level": "medium",
  "approved_by_user": true
}
```

If you use **Edonbot** with `tool: "clawdbot"`, `op: "invoke"`, then the underlying bot gateway can expose its own tools; use `allowed_clawdbot_tools` in intent constraints to allowlist them. The connectors above are **native EDON tools** — the agent sends `tool: "brave_search"` (etc.) directly to EDON.

---

## Quick checklist

| Integration      | Env var                         | Get key / token from                    |
|------------------|----------------------------------|-----------------------------------------|
| Clawdbot Gateway | `CLAWDBOT_GATEWAY_TOKEN`         | your Clawdbot Gateway                    |
| Brave Search     | `BRAVE_SEARCH_API_KEY`          | api.search.brave.com                    |
| Gmail            | `GMAIL_ACCESS_TOKEN`            | Google OAuth2 (Gmail API)               |
| Google Calendar  | `GOOGLE_CALENDAR_ACCESS_TOKEN`  | Google OAuth2 (Calendar API)             |
| Gemini           | `GEMINI_API_KEY`                | Google AI Studio → API key               |
| ElevenLabs       | `ELEVENLABS_API_KEY`            | elevenlabs.io → API key                  |
| GitHub           | `GITHUB_TOKEN`                 | GitHub → Personal access token          |
| Home Assistant   | `HOME_ASSISTANT_TOKEN`          | Home Assistant profile → Long-lived token |

Set the env vars (or store credentials in the DB), then call `POST /execute` with the `action` objects above. Your Telegram/Edonbot bot uses your EDON token (`X-EDON-TOKEN`) so all usage is governed and audited.

---

## Optional: more integrations later

The same pattern works for:

- **Google Maps** — new connector + Tool enum + _execute_tool branch.
- **Notion / Todoist / Slack / Discord** — store token in EDON, add connector, wire in main.
- **Weather / News / Plaid** — same (env or DB credential, connector, tool enum, governor keywords).

Credentials stay in EDON; Edonbot/Telegram only sends high-level actions and never sees API keys.
