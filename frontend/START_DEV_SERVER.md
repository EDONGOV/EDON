# Start EDON Agent UI Dev Server

## Quick Start

```bash
cd C:\Users\cjbig\Desktop\edon-agent-ui

# Install dependencies (if not already installed)
npm install

# Start dev server
npm run dev
```

## Alternative: Using Bun (if installed)

```bash
cd C:\Users\cjbig\Desktop\edon-agent-ui

# Install dependencies
bun install

# Start dev server
bun run dev
```

## Access the UI

Once the server starts, you should see output like:
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:8080/
  ➜  Network: http://[::1]:8080/
```

Open your browser to: **http://localhost:8080**

## Troubleshooting

**Port 8080 already in use:**
- Kill the process: `netstat -ano | findstr :8080` then `taskkill /PID <pid> /F`
- Or change port in `vite.config.ts`: `port: 5173`

**Dependencies not installed:**
- Run `npm install` first
- Check for `node_modules` folder

**Connection refused:**
- Make sure the dev server is actually running
- Check terminal output for errors
- Verify Node.js is installed: `node --version`

## Configuration

To connect to EDON Gateway:
1. Go to Settings page (`/settings`)
2. Enter Gateway URL: `http://localhost:8000`
3. Enter your API token
4. Disable "Mock Mode"

Or use browser console:
```javascript
localStorage.setItem('edon_api_base', 'http://localhost:8000');
localStorage.setItem('edon_api_token', 'your-token');
localStorage.setItem('edon_mock_mode', 'false');
location.reload();
```
