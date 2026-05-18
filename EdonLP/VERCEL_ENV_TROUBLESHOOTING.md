# Vercel Environment Variables Troubleshooting

## If you still see the error after adding the variable:

### 1. Verify Variable Name
Make sure it's **exactly**: `VITE_CLERK_PUBLISHABLE_KEY`
- ✅ Correct: `VITE_CLERK_PUBLISHABLE_KEY`
- ❌ Wrong: `CLERK_PUBLISHABLE_KEY` (missing `VITE_` prefix)
- ❌ Wrong: `VITE_CLERK_KEY` (wrong name)

### 2. Check Environment Scope
When adding the variable, make sure you select:
- ✅ **Production** (required)
- ✅ **Preview** (optional, for PR previews)
- ✅ **Development** (optional, for local dev)

**Important:** If you only selected "Preview", it won't work in Production!

### 3. Redeploy Required
After adding/changing environment variables:
- Vercel usually auto-redeploys
- If not, go to **Deployments** tab
- Click **"..."** on latest deployment → **"Redeploy"**
- Or push a new commit to trigger deployment

### 4. Verify Variable is Set
1. Go to **Settings** → **Environment Variables**
2. Find `VITE_CLERK_PUBLISHABLE_KEY`
3. Check:
   - ✅ Name is correct
   - ✅ Value is set (not empty)
   - ✅ Environment includes "Production"

### 5. Clear Browser Cache
Sometimes the browser caches the old build:
- Hard refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
- Or clear browser cache completely

### 6. Check Build Logs
1. Go to **Deployments** tab
2. Click on the latest deployment
3. Check **Build Logs**
4. Look for any errors about environment variables

### 7. Verify the Value
Make sure the value is:
- ✅ Your actual Clerk publishable key (starts with `pk_live_` or `pk_test_`)
- ❌ NOT the placeholder `YOUR_PUBLISHABLE_KEY`
- ❌ NOT empty

## Quick Checklist

- [ ] Variable name: `VITE_CLERK_PUBLISHABLE_KEY` (exact match)
- [ ] Value: Your actual Clerk key (starts with `pk_`)
- [ ] Environment: Includes "Production"
- [ ] Redeployed after adding variable
- [ ] Cleared browser cache
- [ ] Checked build logs for errors

## Still Not Working?

1. **Double-check the variable name** - must be exactly `VITE_CLERK_PUBLISHABLE_KEY`
2. **Delete and re-add** the variable (sometimes helps)
3. **Check Vercel build logs** for any errors
4. **Try a manual redeploy** from Deployments tab
