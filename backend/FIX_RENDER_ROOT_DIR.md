# Fix Render Root Directory Error

## Error
```
Root directory "edon_gateway" does not exist. Verify the Root Directory configured in your service settings.
```

## Problem
Render is looking for `edon_gateway` directory in the cloned repo, but either:
1. The directory doesn't exist in GitHub
2. The Root Directory setting is incorrect

## Solution: Remove Root Directory Setting

Since the Dockerfile is at `edon_gateway/Dockerfile` relative to repo root, we should **NOT** set Root Directory.

### Fix in Render Dashboard

1. Go to **Settings** → **Build & Deploy**
2. Find **"Root Directory"** field
3. **Clear/Delete it** (leave blank)
   - This tells Render to use the repo root
4. **Dockerfile Path**: Set to `edon_gateway/Dockerfile`
5. **Docker Build Context**: Set to `.` (repo root)
6. **Save Changes**
7. **Manual Deploy**

## Alternative: If Root Directory Must Stay

If you need Root Directory set to `edon_gateway`:
1. **Verify `edon_gateway` exists in GitHub:**
   - Go to: https://github.com/GHOSTCODERRRRAHAHA/edon-cav-engine/tree/main
   - Check if `edon_gateway/` folder exists
2. **If missing, push it:**
   ```powershell
   cd c:\Users\cjbig\Desktop\EDON\edon-cav-engine
   git add edon_gateway/
   git commit -m "feat: Add gateway directory"
   git push origin main
   ```

## Recommended Settings (No Root Directory)

- **Root Directory**: (blank/empty)
- **Dockerfile Path**: `edon_gateway/Dockerfile`
- **Docker Build Context**: `.`
- **Docker Command**: (blank, uses Dockerfile CMD)

This way, Render clones the full repo and the Dockerfile can reference `edon_gateway/` from the root.
