# EDON Console UI - Integration Guide

**React UI from:** https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git

---

## Quick Setup

### Windows (PowerShell)

```powershell
cd edon_gateway\ui
.\setup_ui.ps1
```

### Linux/Mac (Bash)

```bash
cd edon_gateway/ui
chmod +x setup_ui.sh
./setup_ui.sh
```

---

## Development Mode

### 1. Start EDON Gateway

```bash
# Terminal 1: Start gateway
python -m edon_gateway.main
# Or
docker compose up -d
```

### 2. Start React UI

```bash
# Terminal 2: Start React dev server
cd edon_gateway/ui/console-ui
npm run dev
```

### 3. Access UI

- **React UI:** http://localhost:5173 (or port shown in terminal)
- **EDON Gateway API:** http://localhost:8000

---

## Production Build

### Build React App

```bash
cd edon_gateway/ui/console-ui

# Set production API URL
echo "VITE_EDON_GATEWAY_URL=http://localhost:8000" > .env.production

# Build
npm run build
```

### Serve from FastAPI

The built files in `console-ui/dist` will be automatically served by EDON Gateway when you start it.

**Access:** http://localhost:8000/

---

## API Configuration

The React UI needs to connect to EDON Gateway. Configure in `.env`:

```env
VITE_EDON_GATEWAY_URL=http://localhost:8000
VITE_EDON_GATEWAY_TOKEN=your-token  # Optional
```

### Required API Endpoints

The UI should call these EDON Gateway endpoints:

1. **Intent:**
   - `GET /intent/get` - Get current intent
   - `POST /intent/set` - Set intent

2. **Decisions:**
   - `GET /decisions/query?limit=10` - Get decision stream
   - `GET /decisions/{decision_id}` - Get specific decision

3. **Policy Packs:**
   - `GET /policy-packs` - List available packs
   - `POST /policy-packs/{pack_name}/apply` - Apply pack

4. **Security:**
   - `GET /security/anti-bypass` - Security status

5. **Benchmarking:**
   - `GET /benchmark/trust-spec` - Trust metrics
   - `GET /benchmark/report` - Full report

6. **Health:**
   - `GET /health` - Health check

---

## React App Updates

To update the React UI code:

```bash
cd edon_gateway/ui/console-ui
git pull
npm install  # If package.json changed
npm run dev  # For development
npm run build  # For production
```

---

## Docker Integration

For Docker deployments, you can either:

### Option 1: Build UI in Dockerfile

Add to `Dockerfile`:

```dockerfile
# Build React UI
RUN cd edon_gateway/ui && \
    git clone https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git console-ui && \
    cd console-ui && \
    npm install && \
    npm run build
```

### Option 2: Multi-stage Build

```dockerfile
# Stage 1: Build UI
FROM node:18 AS ui-builder
WORKDIR /app/ui
RUN git clone https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git console-ui
WORKDIR /app/ui/console-ui
RUN npm install && npm run build

# Stage 2: Python app
FROM python:3.11-slim
COPY --from=ui-builder /app/ui/console-ui/dist /app/edon_gateway/ui/console-ui/dist
# ... rest of Dockerfile
```

---

## Troubleshooting

### UI not loading

1. Check if `console-ui/dist` exists
2. Verify `index.html` is in dist folder
3. Check FastAPI logs for mounting errors

### API calls failing

1. Verify `VITE_EDON_GATEWAY_URL` in `.env`
2. Check CORS settings (should be enabled)
3. Verify EDON Gateway is running
4. Check browser console for errors

### Build errors

1. Ensure Node.js 18+ is installed
2. Run `npm install` to update dependencies
3. Check `package.json` for required scripts

---

## Features Expected in UI

The React UI should display:

1. **Intent Panel**
   - Current intent objective
   - Scope and constraints
   - Risk level

2. **Decision Stream**
   - Real-time decisions
   - Color-coded by verdict
   - Statistics

3. **Audit Trail**
   - Recent events
   - Export functionality

4. **Policy Packs**
   - List available packs
   - Apply packs

5. **Security Status**
   - Bypass resistance score
   - Security configuration

6. **Benchmarks**
   - Latency metrics
   - Block rate
   - Trust spec

---

*Last Updated: 2025-01-27*
