# Connect Flow — Telegram Bot Integration

How the Telegram bot should use the backend so users can connect Gmail, Brave, GitHub, Calendar, and ElevenLabs from `/connect`.

**Running the bot on Cloudflare:** To receive Telegram updates at the edge, set the webhook to your edon-agent Worker and have the Worker call this gateway. See [Connect Edonbot to Cloudflare](../../docs/EDONBOT_CLOUDFLARE.md) (repo root `docs/EDONBOT_CLOUDFLARE.md`).

---

## 1. Show buttons when user sends `/connect`

1. **GET** `{GATEWAY_URL}/integrations/connect/buttons` (no auth).
2. Use `response.telegram_inline_keyboard` as Telegram inline keyboard:
   - `reply_markup = { "inline_keyboard": response["telegram_inline_keyboard"] }`.
3. Send a message like: “Choose a service to connect:” with that keyboard.

---

## 2. When user taps a button (callback_data)

You receive a callback with `callback_data` = `connect_gmail` | `connect_google_calendar` | `connect_brave_search` | `connect_github` | `connect_elevenlabs` | `connect_gemini` | `connect_polygon` | `connect_fmp` | `connect_newsapi`.

1. Resolve the user to a **tenant** (e.g. from your stored binding: Telegram `user_id` → tenant_id) and get their **EDON token** for that tenant.
2. **POST** `{GATEWAY_URL}/integrations/connect/link`  
   - **Headers:** `X-EDON-TOKEN: <tenant token>`  
   - **Body:** `{ "service": "gmail", "chat_id": "123456" }`  
  - `service` = one of: `gmail`, `google_calendar`, `brave_search`, `github`, `elevenlabs`, `gemini`, `polygon`, `fmp`, `newsapi` (match callback_data: strip `connect_` prefix).  
     - `chat_id` = optional; use if you want to notify this chat later (e.g. “Gmail connected”).
3. Response: `{ "url": "https://...", "code": "EDON-...", "expires_in": 600 }`.
4. **Send the URL to the user** in Telegram (e.g. “Open this link to connect Gmail: {url}”). Optionally answer the callback query so the button stops loading.

---

## 3. Optional: `/connections` command

1. **GET** `{GATEWAY_URL}/integrations/connect/status`  
   - **Headers:** `X-EDON-TOKEN: <tenant token>`.
2. Response: `{ "services": { "gmail": true, "google_calendar": false, "brave_search": false, ... } }`.
3. Send a message like: “Gmail ✓, Calendar ✗, Brave ✗, GitHub ✗, ElevenLabs ✗, Gemini ✗, Polygon ✗, FMP ✗, NewsAPI ✗”.

---

## 4. Environment (backend)

- **EDON_CONNECT_BASE_URL** — Base URL for connect pages (e.g. `https://your-gateway.com` or `https://edoncore.com` if connect pages are on another host). If unset, the gateway uses the request base URL.
- **GOOGLE_CLIENT_ID** / **GOOGLE_CLIENT_SECRET** — Required for Gmail and Google Calendar OAuth. In Google Cloud Console, add redirect URIs:
  - `{EDON_CONNECT_BASE_URL}/integrations/connect/gmail/callback`
  - `{EDON_CONNECT_BASE_URL}/integrations/connect/google_calendar/callback`

---

## 5. Summary

| Bot action              | Backend call                                      |
|-------------------------|---------------------------------------------------|
| User sends `/connect`   | GET /integrations/connect/buttons → show keyboard |
| User taps a service     | POST /integrations/connect/link (with token)     |
| Bot sends user          | Message with `response.url`                       |
| User sends `/connections` | GET /integrations/connect/status (with token)  |
