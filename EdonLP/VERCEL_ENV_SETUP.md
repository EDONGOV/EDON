# Vercel Environment Variables Setup

## Required Environment Variables

Set these in **Vercel Dashboard** → Your Project → Settings → Environment Variables:

### Production Environment

```
VITE_CLERK_PUBLISHABLE_KEY=pk_live_... (from Clerk Dashboard - Production)
VITE_GATEWAY_URL=https://api.edoncore.com
VITE_API_BASE_URL=https://api.edoncore.com
```

### Preview Environment (Optional - for PR previews)

```
VITE_CLERK_PUBLISHABLE_KEY=pk_test_... (from Clerk Dashboard - Development)
VITE_GATEWAY_URL=https://api.edoncore.com
VITE_API_BASE_URL=https://api.edoncore.com
```

## How to Set in Vercel

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Select your project (`edon-sentinel-core`)
3. Go to **Settings** → **Environment Variables**
4. Click **Add New**
5. For each variable:
   - **Key**: `VITE_CLERK_PUBLISHABLE_KEY`
   - **Value**: `pk_live_...` (your actual key)
   - **Environment**: Select **Production**, **Preview**, and **Development** (or just Production)
6. Click **Save**
7. **Redeploy** your site (Vercel will auto-redeploy after adding env vars)

## Get Your Clerk Keys

1. Go to [Clerk Dashboard](https://dashboard.clerk.com)
2. Select your application
3. Go to **API Keys**
4. Copy:
   - **Publishable Key** (starts with `pk_live_` for production)
   - **Secret Key** (starts with `sk_live_` for production) - needed for backend

## Important Notes

- ⚠️ **`.env.local` is only for local development** - Vercel doesn't use it
- ✅ **Environment variables in Vercel** are used for production builds
- 🔄 **Redeploy required** after adding/changing env vars
- 🔒 **Never commit `.env.local`** to git (it's in `.gitignore`)

## Verify Setup

After setting env vars and redeploying:
1. Visit your production site
2. Check browser console - should NOT see Clerk key error
3. Try signing up - should work
