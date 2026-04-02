# EDON Agent Console

**Purpose**: Agent monitoring console where users monitor their clawdbot/AI agents working autonomously and watch EDON keep them secure.

This is the **paid user interface** that customers access after subscribing to EDON. Users can:
- Monitor real-time security decisions (allowed/blocked/confirm)
- View metrics and analytics (24h stats, latency, decision trends)
- Review audit logs and decision history
- Configure policy modes (Personal Safe, Work Safe, Ops/Admin)
- Track agent activity and EDON governance in action

## Architecture

This UI connects to **EDON Gateway** (`edon_gateway`) which is the backend API that:
- Connects to clawdbots/agents
- Enforces security policies
- Processes actions through governance layer
- Provides audit logging and metrics

```
User → Agent Console (this UI) → EDON Gateway → Clawdbot/Agent
```

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- EDON Gateway running (see `../edon-cav-engine/edon_gateway`)

### Installation

```bash
# Install dependencies
npm install

# Create .env file (optional - defaults to production mode)
echo "VITE_EDON_GATEWAY_URL=http://localhost:8000" > .env
echo "VITE_EDON_MOCK_MODE=false" >> .env

# Start development server
npm run dev
```

The console will start on `http://localhost:8080` (configured in vite.config.ts).

**Note:** Mock mode is now **disabled by default** for production readiness. The UI will automatically connect to EDON Gateway if available.

### Configuration

**Option 1: Environment Variables (.env)**

```env
VITE_EDON_GATEWAY_URL=http://localhost:8000
```

**Option 2: Browser localStorage (for quick testing)**

Open browser console and run:
```javascript
localStorage.setItem('edon_api_base', 'http://localhost:8000');
localStorage.setItem('edon_mock_mode', 'false');
location.reload();
```

## Features

- **Dashboard**: Overview with KPIs, decision stream, and charts
- **Decisions**: Filterable decision history with details
- **Audit**: Full audit trail with search and filtering
- **Policies**: Apply policy packs and configure security modes
- **Settings**: API configuration and security status

## API Endpoints Used

The console connects to these EDON Gateway endpoints:

- `GET /health` - Health check
- `GET /metrics` - System metrics (allowed/blocked counts, latency)
- `GET /decisions/query` - Decision stream with filtering
- `GET /audit/query` - Audit log query
- `GET /intent/get` - Current intent contract
- `POST /intent/set` - Set intent contract
- `GET /policy-packs` - List available policy packs
- `POST /policy-packs/{pack_name}/apply` - Apply policy pack

## Mock Mode

**Production Default:** Mock mode is **disabled by default**. The UI connects to EDON Gateway automatically.

**To enable mock mode** (for development/testing without gateway):
1. Set `localStorage.setItem('edon_mock_mode', 'true')`
2. Reload the page

**To configure gateway connection:**
1. Go to Settings page (`/settings`)
2. Enter Gateway URL and API token
3. Click "Test Connection" - mock mode will be automatically disabled on success
4. Or set environment variable: `VITE_EDON_GATEWAY_URL=http://localhost:8000`

## Development

```bash
# Start dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Production Deployment

Primary production domain for the console:

**Production URL**: https://agent.edoncore.com

### Render (recommended)

Use the `render.yaml` in this repo or create a Static Site manually:

- **Build command:** `npm ci && npm run build`
- **Publish directory:** `dist`
- **Env vars:** `VITE_EDON_GATEWAY_URL=https://edon-gateway.onrender.com`, `VITE_EDON_MOCK_MODE=false`
- **Custom domain:** `agent.edoncore.com`
- **SPA rewrite:** `/*` → `/index.html` (rewrite)

### Vercel / Netlify

Deploy as a static Vite app with output `dist`, then map the custom domain to
`agent.edoncore.com`.

## Related Components

- **edon-sentinel-core** (`D:\dev\edon-sentinel-core`): Public marketing website where users sign up and pay
- **edon_gateway** (`../edon-cav-engine/edon_gateway`): Backend API gateway

See `../edon-cav-engine/STARTUP_GUIDE.md` for full stack startup instructions.

## Technologies

- React 18
- TypeScript
- Vite
- shadcn-ui components
- Tailwind CSS
- Recharts (for charts)
- TanStack Query (for API calls)
