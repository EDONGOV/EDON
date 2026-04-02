# Deploy Agent UI to agent.edoncore.com & Test Token Setup

## 1. Deploy Agent UI to agent.edoncore.com

### Option A: Render (recommended – same as gateway)

**If the Agent UI is in its own Git repo:**

1. **Connect the repo to Render**
   - Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
   - Connect the Git repo that contains `edon-agent-ui` (and this `render.yaml`).
   - Render will detect `render.yaml` and create the static site.

2. **Or create the static site manually**
   - **New** → **Static Site**.
   - Connect the same repo, set:
     - **Build command:** `npm ci && npm run build`
     - **Publish directory:** `dist`
   - Under **Environment**, add:
     - `VITE_EDON_GATEWAY_URL` = `https://edon-gateway.onrender.com`
     - `VITE_EDON_MOCK_MODE` = `false`

3. **Custom domain**
   - In the static site → **Settings** → **Custom Domains** → **Add custom domain**.
   - Enter `agent.edoncore.com`.
   - In your DNS (where edoncore.com is managed), add:
     - **CNAME** `agent` → `&lt;your-static-site&gt;.onrender.com`  
     (Render shows the exact target after you add the domain.)

4. **SPA routing**
   - In **Settings** → **Redirects/Rewrites**, add a rewrite so all paths serve the app:
     - **Source:** `/*`
     - **Destination:** `/index.html`
     - Type: **Rewrite** (not redirect).

**If the Agent UI lives inside the `edon-cav-engine` monorepo:**

- In Render, create a **Static Site** and point it at the `edon-cav-engine` repo.
- Set **Root directory** to the folder that contains the Agent UI (e.g. `edon-agent-ui` if it’s inside the repo).
- Use the same build command, publish directory, env vars, and custom domain as above.

---

### Option B: Vercel

1. Import the project: [vercel.com/new](https://vercel.com/new) → import the Agent UI repo.
2. **Build settings:** Framework Preset = Vite; build command = `npm run build`; output = `dist`.
3. **Environment variables:**  
   `VITE_EDON_GATEWAY_URL` = `https://edon-gateway.onrender.com`,  
   `VITE_EDON_MOCK_MODE` = `false`.
4. **Custom domain:** Project → Settings → Domains → add `agent.edoncore.com` and set the DNS record Vercel shows (usually CNAME to `cname.vercel-dns.com`).

---

### Option C: Netlify

1. **New site from Git** → connect the Agent UI repo.
2. **Build settings:** Build command = `npm run build`, Publish directory = `dist`.
3. **Environment variables:** same as above (`VITE_EDON_GATEWAY_URL`, `VITE_EDON_MOCK_MODE`).
4. **SPA redirect:** Add `_redirects` in `public/` with:
   ```text
   /*    /index.html   200
   ```
5. **Custom domain:** Site → Domain management → Add custom domain → `agent.edoncore.com` → configure DNS as shown.

---

## 2. Test token for clean test runs

Integration tests call the real gateway and use **either** a token you set **or** localStorage. To run tests cleanly with a fixed token:

### Step 1: Pick a token that matches the gateway

- **Local gateway:** Use the same value as in `edon_gateway/.env`:
  ```env
  EDON_API_TOKEN=change-me
  ```
  So your test token can be `change-me` (or whatever you set there).

- **Production / Render gateway:** Use the same value as `EDON_API_TOKEN` set in the Render service env (e.g. the secret you configured in the Render dashboard).

### Step 2: Set env vars when running tests

**PowerShell (Windows):**

```powershell
$env:VITE_EDON_API_TOKEN = "change-me"
$env:VITE_EDON_GATEWAY_URL = "http://localhost:8000"   # optional; default is this for dev
npm test
```

**Bash (Linux/macOS):**

```bash
export VITE_EDON_API_TOKEN=change-me
export VITE_EDON_GATEWAY_URL=http://localhost:8000
npm test
```

The tests read:

- `VITE_EDON_API_TOKEN` or `VITE_EDON_GATEWAY_TOKEN` for the token.
- `VITE_EDON_GATEWAY_URL` for the gateway URL (default `http://localhost:8000`).

If the token is set, they inject it into `localStorage` as `edon_token` for the test run, so integration tests hit the gateway with auth.

### Step 3: Optional – `.env` for local dev and tests

To avoid typing the token every time:

1. Copy `.env.example` to `.env` in the Agent UI repo.
2. Set in `.env`:
   ```env
   VITE_EDON_GATEWAY_URL=http://localhost:8000
   VITE_EDON_API_TOKEN=change-me
   ```
3. Do **not** commit `.env` (it should be in `.gitignore`).
4. Run `npm test`; Vite/Vitest will expose `VITE_*` to the tests when they run.

### If the gateway has auth disabled

When `EDON_AUTH_ENABLED=false`, the gateway does not require a token. You can leave `VITE_EDON_API_TOKEN` unset and still run tests; they will pass without a token.

---

## Quick reference

| Goal | Action |
|------|--------|
| Deploy to agent.edoncore.com | Use Render (or Vercel/Netlify) with build `npm run build`, publish `dist`, custom domain, SPA rewrite. |
| Run integration tests with auth | Set `VITE_EDON_API_TOKEN` (and optionally `VITE_EDON_GATEWAY_URL`) then `npm test`. |
| Same token as gateway | Use the same value as `EDON_API_TOKEN` in `edon_gateway/.env` or in Render env. |
