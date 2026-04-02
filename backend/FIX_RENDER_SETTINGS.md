# Fix Render Gateway Settings

## Current Issue
The gateway is running the CAV Engine instead of the Gateway because Render Docker settings need to be configured correctly.

## Fix in Render Dashboard

### Step 1: Set Dockerfile Path
1. Go to **Settings** → **Build & Deploy**
2. Find **"Dockerfile Path"** field
3. Set it to: `edon_gateway/Dockerfile`
   - This points to the Dockerfile we just created inside `edon_gateway/`

### Step 2: Set Docker Build Context
In **"Docker Build Context Directory"** field, set:
```
.
```
- This tells Docker to use the **repo root** as the build context (needed to access `requirements.gateway.txt`)

### Step 3: Docker Command (Optional)
You can leave **"Docker Command"** blank - the Dockerfile CMD will be used.
Or set it to:
```
python -m uvicorn edon_gateway.main:app --host 0.0.0.0 --port $PORT
```

### Step 4: Verify Root Directory
**Root Directory** should be: `edon_gateway` ✅ (already correct)

### Step 5: Enable Auto-Deploy
Turn **Auto-Deploy** to **On** so future commits auto-deploy

### Step 6: Save and Deploy
1. Click **Save Changes**
2. Click **Manual Deploy** → **Deploy latest commit**
3. Wait 2-3 minutes for build to complete

## After Deployment

You should see:
- ✅ "Starting EDON Gateway..." in logs (not "Starting EDON CAV Engine...")
- ✅ Title: "EDON Gateway" in `/docs` (not "EDON CAV Engine")
- ✅ `/auth/signup` endpoint available
- ✅ `/billing/checkout` endpoint available

## What We Fixed

Created a new `Dockerfile` inside `edon_gateway/` that:
- Copies `requirements.gateway.txt` from parent directory
- Copies the gateway code preserving package structure
- Runs `edon_gateway.main:app` to match the relative imports
