# EDON Agent UI - Clawdbot Integration Complete

## Overview

The UI has been wired to support Path 1: Clawdbot Integration + Governance Visibility using the existing design system and layout.

## ✅ Implemented Features

### 1. API Client Updates (`src/lib/api.ts`)

Added methods for new endpoints:
- ✅ `connectClawdbot()` - POST /integrations/clawdbot/connect
- ✅ `getIntegrationStatus()` - GET /account/integrations
- ✅ `getPolicyPacks()` - GET /policy-packs
- ✅ `applyPolicyPack()` - POST /policy-packs/{pack}/apply

### 2. Integrations Page (`src/pages/Integrations.tsx`)

**New page** for connecting Clawdbot Gateway:
- ✅ Connection form with Base URL, Auth Mode, Secret fields
- ✅ "Test & Connect" button that validates and saves credentials
- ✅ Status display showing connection details
- ✅ Shows last_ok_at, last_error, active_policy_pack, default_intent_id
- ✅ Refresh button to update status
- ✅ Uses existing design system (glass-card, buttons, badges)

### 3. Policies Page Updated (`src/pages/Policies.tsx`)

**Refactored** to use real API endpoints:
- ✅ Fetches policy packs from `GET /policy-packs`
- ✅ Applies packs via `POST /policy-packs/{pack}/apply`
- ✅ Shows active policy pack from integration status
- ✅ Displays risk level, allowed/blocked tool counts
- ✅ Refresh button to reload packs
- ✅ Maintains existing card-based design

### 4. Navigation Updated (`src/components/TopNav.tsx`)

- ✅ Added "Integrations" link to navigation
- ✅ Uses Plug icon from lucide-react

### 5. Routing Updated (`src/App.tsx`)

- ✅ Added `/integrations` route
- ✅ Integrations page accessible from navigation

## Pages Overview

### A) Integrations Page (`/integrations`)

**Purpose:** Connect Clawdbot Gateway integration

**Fields:**
- Base URL (default: `http://127.0.0.1:18789`)
- Auth Mode dropdown: Password / Token
- Secret input (password field)
- "Test + Connect" button

**Displays:**
- Connection status (Connected/Not Connected badge)
- Base URL, Auth Mode
- Last OK timestamp
- Last error (if any)
- Active policy pack
- Default intent ID

**API Calls:**
- `POST /integrations/clawdbot/connect` - Connect
- `GET /account/integrations` - Status

### B) Policies Page (`/policies`)

**Purpose:** Apply policy packs

**Features:**
- Lists available policy packs from API
- Shows risk level, tool counts
- "Apply" button sets default intent and active preset
- Displays current active policy pack

**API Calls:**
- `GET /policy-packs` - List packs
- `POST /policy-packs/{pack}/apply` - Apply pack
- `GET /account/integrations` - Get active pack

### C) Decisions Page (`/decisions`)

**Purpose:** View decision stream

**Already Working:**
- ✅ Uses `GET /decisions/query` endpoint
- ✅ Filters by verdict, tool, agent_id
- ✅ Displays timestamp, tool, verdict, reason_code, latency_ms, explanation
- ✅ Expandable explanation via DecisionDrawer

**No Changes Needed**

### D) Audit Page (`/audit`)

**Purpose:** View audit log

**Already Working:**
- ✅ Uses `GET /audit/query` endpoint
- ✅ Filters by verdict, agent_id, intent_id
- ✅ Displays who, what tool, why, when

**No Changes Needed**

## Design System

All pages use the existing design system:
- ✅ `glass-card` styling
- ✅ Existing UI components (Button, Input, Badge, Select, etc.)
- ✅ Consistent spacing and layout
- ✅ Motion animations (framer-motion)
- ✅ Toast notifications for feedback

## Mock Mode Support

All new endpoints have mock handlers:
- ✅ `/policy-packs` - Returns mock packs
- ✅ `/policy-packs/{pack}/apply` - Returns mock response
- ✅ `/integrations/clawdbot/connect` - Returns mock success
- ✅ `/account/integrations` - Returns mock status

## User Flow

1. **Connect Clawdbot** (`/integrations`)
   - Enter Base URL, Auth Mode, Secret
   - Click "Test & Connect"
   - See connection status

2. **Apply Policy Pack** (`/policies`)
   - View available packs
   - Click "Apply" on desired pack
   - Pack becomes active (sets default intent)

3. **Monitor Decisions** (`/decisions`)
   - View real-time decision stream
   - Filter by verdict, tool, agent
   - Expand for details

4. **View Audit Log** (`/audit`)
   - See all governance events
   - Filter by verdict, agent, intent
   - Track what was blocked/allowed

## Files Created/Modified

### Created
- `src/pages/Integrations.tsx` - New integrations page

### Modified
- `src/lib/api.ts` - Added new API methods
- `src/pages/Policies.tsx` - Refactored to use real API
- `src/components/TopNav.tsx` - Added Integrations link
- `src/App.tsx` - Added Integrations route

## Testing

All endpoints are ready for testing:

1. **Connect:** Navigate to `/integrations`, fill form, click "Test & Connect"
2. **Apply Pack:** Navigate to `/policies`, click "Apply" on a pack
3. **View Status:** Check integration status on `/integrations` page
4. **Monitor:** View decisions on `/decisions` and audit on `/audit`

## Next Steps

The UI is now fully wired to support Clawdbot integration. Users can:
- ✅ Connect Clawdbot Gateway
- ✅ Apply policy packs (sets default intent)
- ✅ Monitor governance decisions
- ✅ View audit logs

All using the existing design system with no UI redesign.
