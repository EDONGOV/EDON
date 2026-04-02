# Production Fixes Required

## 🔴 Critical Issues

### 1. Frontend: Remove Console Logs

**Location:** `D:\dev\edon-sentinel-core\src`

**Files to fix:**
- `src/contexts/AuthContext.tsx` - Lines 71, 76, 101, 122, 175
- `src/pages/Account.tsx` - Lines 52, 70
- `src/pages/OnboardingSuccess.tsx` - Line 125
- `src/pages/OEMApply.tsx` - Line 35
- `src/pages/Download.tsx` - Line 85

**Fix:** Replace `console.log/error` with proper error handling or remove:

```typescript
// Instead of:
console.error("Error:", error);

// Use:
if (import.meta.env.DEV) {
  console.error("Error:", error); // Only in development
}
// Or use toast notifications for user-facing errors
toast.error("Failed to load data. Please try again.");
```

### 2. Backend: Implement Clerk Token Validation

**Location:** `edon_gateway/main.py` - Line 1272

**Current:** TODO placeholder
**Required:** Implement actual Clerk JWT validation

**Fix:**
```python
def validate_clerk_token(clerk_token: str) -> Optional[SessionClaims]:
    """Validate Clerk token and return standardized session claims."""
    import requests
    from .config import config
    
    try:
        # Verify token with Clerk API
        response = requests.get(
            f"https://api.clerk.com/v1/tokens/{clerk_token}/verify",
            headers={"Authorization": f"Bearer {config.CLERK_SECRET_KEY}"}
        )
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        clerk_user_id = data.get("sub")
        
        # Look up user in database
        db = get_db()
        user = db.get_user_by_auth("clerk", clerk_user_id)
        if not user:
            return None
            
        tenant = db.get_tenant_by_user_id(user["id"])
        if not tenant:
            return None
            
        return SessionClaims(
            user_id=user["id"],
            tenant_id=tenant["id"],
            email=user["email"],
            role=user.get("role", "user"),
            plan=tenant.get("plan", "starter"),
            status=tenant.get("status", "inactive")
        )
    except Exception as e:
        logger.error(f"Clerk token validation failed: {e}")
        return None
```

**Add to config.py:**
```python
CLERK_SECRET_KEY: Optional[str] = os.getenv("CLERK_SECRET_KEY")
```

### 3. Backend: Remove Localhost from CORS Defaults

**Location:** `edon_gateway/main.py` - Lines 68-69

**Current:** Includes `localhost:5173` and `localhost:3000` in defaults
**Fix:** Only use production domains in defaults, localhost only in development

```python
# In main.py, update CORS defaults:
if "*" in cors_origins:
    # Default to production origins only
    cors_origins = [
        "https://edoncore.com",
        "https://www.edoncore.com"
    ]
    # Add localhost only in development
    if os.getenv("ENVIRONMENT") != "production":
        cors_origins.extend([
            "http://localhost:5173",
            "http://localhost:3000"
        ])
```

## ⚠️ Important Issues

### 4. Frontend: Environment Variable Validation

**Location:** `D:\dev\edon-sentinel-core\src`

**Add validation on app startup:**

```typescript
// In main.tsx or App.tsx
if (!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY) {
  console.error("Missing VITE_CLERK_PUBLISHABLE_KEY");
  // Show error to user or redirect to setup page
}

if (!import.meta.env.VITE_GATEWAY_URL) {
  console.error("Missing VITE_GATEWAY_URL");
}
```

### 5. Backend: Add Clerk Secret Key to Config

**Location:** `edon_gateway/config.py`

**Add:**
```python
# Clerk Authentication
CLERK_SECRET_KEY: Optional[str] = os.getenv("CLERK_SECRET_KEY")
```

**Add to Render environment variables:**
```
CLERK_SECRET_KEY=sk_live_... (from Clerk Dashboard)
```

### 6. Frontend: Error Boundary

**Location:** `D:\dev\edon-sentinel-core\src`

**Add React Error Boundary to catch and handle errors gracefully:**

```typescript
// src/components/ErrorBoundary.tsx
import React from 'react';

class ErrorBoundary extends React.Component {
  // ... implementation
}
```

## ✅ Already Good

- ✅ Error handling doesn't leak tracebacks (production-safe)
- ✅ Tokens stored as hashes (never plaintext)
- ✅ CORS configuration exists (just needs localhost removal)
- ✅ Environment variables documented
- ✅ Health check endpoint exists
- ✅ Rate limiting enabled
- ✅ Authentication middleware in place

## Quick Fix Script

Run these commands to fix console logs in frontend:

```powershell
cd D:\dev\edon-sentinel-core

# Find all console.log/error statements
Get-ChildItem -Recurse -Filter *.tsx,*.ts | Select-String "console\.(log|error|warn)" | ForEach-Object {
    Write-Host "$($_.Filename):$($_.LineNumber) - $($_.Line)"
}
```

Then manually replace or wrap in `if (import.meta.env.DEV)` checks.
