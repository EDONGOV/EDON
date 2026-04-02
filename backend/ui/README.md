# EDON Console UI Integration

This directory contains the React-based UI for EDON Gateway, sourced from:
https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git

---

## Setup Instructions

### Option 1: Development Mode (Recommended)

Run the React UI as a separate development server:

```bash
# Clone the UI repository
cd edon_gateway/ui
git clone https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git console-ui
cd console-ui

# Install dependencies
npm install

# Set API endpoint (create .env file)
echo "VITE_EDON_GATEWAY_URL=http://localhost:8000" > .env
echo "VITE_EDON_GATEWAY_TOKEN=your-token" >> .env

# Start development server
npm run dev
```

The UI will run on `http://localhost:5173` (or another port) and connect to EDON Gateway at `http://localhost:8000`.

### Option 2: Production Build (Serve from FastAPI)

Build the React app and serve it from FastAPI:

```bash
# Clone and build
cd edon_gateway/ui
git clone https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git console-ui
cd console-ui

# Install dependencies
npm install

# Set production API endpoint
echo "VITE_EDON_GATEWAY_URL=http://localhost:8000" > .env.production

# Build for production
npm run build

# Copy build output to ui directory
cp -r dist/* ../

# Or create a symlink
ln -s console-ui/dist ../dist
```

Then update `edon_gateway/main.py` to serve from the `dist` directory.

---

## API Configuration

The React UI needs to connect to EDON Gateway API. Configure the API endpoint:

**Environment Variables:**
- `VITE_EDON_GATEWAY_URL` - EDON Gateway URL (default: http://localhost:8000)
- `VITE_EDON_GATEWAY_TOKEN` - Optional token for authenticated requests

**API Endpoints Used:**
- `GET /intent/get` - Get current intent
- `GET /decisions/query` - Query decision stream
- `GET /benchmark/trust-spec` - Get trust metrics
- `GET /security/anti-bypass` - Get security status
- `GET /policy-packs` - List policy packs
- `POST /policy-packs/{pack_name}/apply` - Apply policy pack

---

## Integration with EDON Gateway

The React UI should call EDON Gateway endpoints. Make sure:

1. **CORS is enabled** - EDON Gateway already has CORS enabled for `*`
2. **Authentication** - If using tokens, include `X-EDON-TOKEN` header
3. **API Base URL** - Configure `VITE_EDON_GATEWAY_URL` in React app

---

## Development Workflow

1. **Start EDON Gateway:**
   ```bash
   python -m edon_gateway.main
   # Or
   docker compose up -d
   ```

2. **Start React UI:**
   ```bash
   cd edon_gateway/ui/console-ui
   npm run dev
   ```

3. **Access UI:**
   - React dev server: http://localhost:5173
   - EDON Gateway: http://localhost:8000

---

## Production Deployment

For production, build the React app and serve it from FastAPI or a web server:

```bash
# Build React app
cd edon_gateway/ui/console-ui
npm run build

# Serve from FastAPI (update main.py to serve dist/)
# Or serve from nginx/CDN
```

---

*Last Updated: 2025-01-27*
