# Demo Mode Guide

## Enable Demo Mode

Demo mode bypasses subscription checks and allows testing without payment.

### 1. Set Environment Variable in Render

Go to Render Dashboard → `edon-gateway` service → Environment → Add:

```
EDON_DEMO_MODE=true
```

### 2. Get Demo Credentials

Once enabled, call:

```bash
GET https://edon-gateway.onrender.com/demo/credentials
```

Response:
```json
{
  "tenant_id": "demo_tenant_001",
  "api_key": "edon_demo_key_12345",
  "status": "active",
  "plan": "starter",
  "message": "Demo mode active - subscription checks bypassed"
}
```

### 3. Use Demo Credentials

**In Frontend (`Account.tsx`):**

```typescript
// Add demo mode check
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

// Fetch demo credentials if in demo mode
useEffect(() => {
  if (DEMO_MODE) {
    fetch(`${GATEWAY_URL}/demo/credentials`)
      .then(res => res.json())
      .then(data => {
        setTenantId(data.tenant_id);
        setApiKey(data.api_key);
        setStatus('active');
        setPlan('starter');
      });
  }
}, []);
```

### 4. Frontend Button Styling (Make Blue Buttons Rounded)

In `D:\dev\edon-sentinel-core\src\pages\Account.tsx`, update button styles:

```tsx
// Find the "Open Console" button and update className:
<Button 
  className="rounded-full px-6 py-3" // Add rounded-full for fully rounded
  // or
  className="rounded-xl px-6 py-3" // For less rounded (xl = 12px)
>
  Open Console
  <ExternalLink className="ml-2 h-4 w-4" />
</Button>

// For all blue buttons, add to your CSS or Tailwind:
.blue-button {
  border-radius: 9999px; /* Fully rounded */
  /* or */
  border-radius: 0.75rem; /* 12px rounded */
}
```

**Quick CSS Fix (add to your global CSS):**

```css
/* Make all primary/blue buttons rounded */
button[class*="bg-blue"], 
button[class*="bg-primary"],
.btn-primary {
  border-radius: 9999px !important; /* Fully rounded */
  padding: 0.75rem 1.5rem !important;
}
```

### 5. Test Console Access

With demo mode enabled:
- ✅ No payment required
- ✅ All endpoints work
- ✅ Status shows as "active"
- ✅ Console accessible

## Disable Demo Mode

Remove or set to `false`:
```
EDON_DEMO_MODE=false
```

**⚠️ Warning:** Demo mode should only be enabled for testing. Disable in production!
