# Authentication Setup

The EDON Agent UI requires an API token to authenticate with the EDON Gateway.

## Quick Setup

### Option 1: Environment Variable (Recommended for Development)

Create a `.env` file in the `edon-agent-ui` directory:

```bash
VITE_EDON_GATEWAY_URL=http://localhost:8000
VITE_EDON_API_TOKEN=NEW_GATEWAY_TOKEN_12345
VITE_EDON_MOCK_MODE=false
```

**Note:** After creating/updating `.env`, restart your dev server (`npm run dev`).

### Option 2: Settings Page (Recommended for Production)

1. Open the EDON Agent UI in your browser
2. Navigate to **Settings** (gear icon in the top navigation)
3. Enter your API token in the "API Token" field
4. Click **Save Settings**

## Finding Your API Token

Your API token is configured in the EDON Gateway's `.env` file:

**Location:** `edon-cav-engine/edon_gateway/.env`

**Key:** `EDON_API_TOKEN`

**Default value (development):** `NEW_GATEWAY_TOKEN_12345`

⚠️ **Security Note:** Change this token in production!

## Troubleshooting

### 401 Unauthorized Errors

If you see `401 Unauthorized` errors in the browser console:

1. **Check your token:**
   - Verify the token matches `EDON_API_TOKEN` in the gateway's `.env`
   - Make sure there are no extra spaces or quotes

2. **Check Settings:**
   - Go to Settings page
   - Verify the token is saved (it will be masked)
   - Click "Test Connection" to verify

3. **Check Environment Variables:**
   - If using `.env`, ensure it's in the `edon-agent-ui` directory (not `edon-cav-engine`)
   - Restart the dev server after creating/updating `.env`

4. **Check Gateway Status:**
   - Ensure EDON Gateway is running on `http://localhost:8000`
   - Test with: `curl http://localhost:8000/health`

### Token Not Persisting

- Clear browser localStorage and re-enter token
- Check browser console for errors
- Ensure you're not in "Mock Mode" (Settings page)

## Production Deployment

For production:

1. **Never commit `.env` files** to version control
2. Use environment variables set by your hosting platform (Vercel, Render, etc.)
3. Use the Settings page for user-managed tokens
4. Consider using database-backed API keys for multi-tenant deployments
