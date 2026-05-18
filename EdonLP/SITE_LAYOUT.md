# EDON Main Site Layout

## Overview

The EDON main site (`edon-sentinel-core`) is a React/TypeScript application built with Vite, serving as the marketing and documentation site for EDON. This document outlines the current structure and identifies integration points for the SaaS model.

---

## Technology Stack

- **Framework:** React 18.3.1 with TypeScript
- **Build Tool:** Vite 5.4.19
- **Routing:** React Router DOM 6.30.1
- **UI Components:** shadcn-ui (Radix UI primitives)
- **Styling:** Tailwind CSS 3.4.17
- **State Management:** TanStack Query (React Query)
- **Forms:** React Hook Form with Zod validation

---

## Site Structure

### Routes (`src/App.tsx`)

```
/                    → Index (Homepage)
/news                → News page
/standards           → Standards documentation
/about               → About page
/contact             → Contact page
/docs                → Documentation hub
/docs/api            → API documentation (same as /docs)
/platforms           → Platform-specific information
/product             → Product overview
/oem/apply           → OEM access request form
/request-access      → Alias for /oem/apply
/download            → Download page
/oem/confirmation    → Confirmation page after OEM application
/*                   → 404 Not Found page
```

### Navigation (`src/components/Navigation.tsx`)

**Desktop Navigation Links:**
- Product
- Platforms
- Docs
- Standards
- News
- About
- Contact

**CTA Button:** "REQUEST ACCESS" → Links to `/oem/apply`

**Mobile:** Sheet-based mobile menu with same links

---

## Page Components

### 1. Index (`src/pages/Index.tsx`)
**Homepage** - Composed of:
- `TacticalHero` - Hero section
- `TacticalMission` - Mission statement
- `TacticalTechnology` - Technology overview
- `TacticalArchitecture` - Architecture diagram
- `TacticalFounder` - Founder section
- `TacticalPartnerships` - Partnerships section
- `Footer` - Site footer

### 2. OEMApply (`src/pages/OEMApply.tsx`)
**OEM Access Request Form** - Current flow:
- Form fields: Company Name, Role, Use Case, Deployment Timeline, Region, Work Email
- Email validation (company emails only)
- Submits to `sendFormSubmission('oem', formData)` API
- Redirects to `/oem/confirmation` on success
- **Note:** Currently sends email, not integrated with tenant provisioning

### 3. Docs (`src/pages/Docs.tsx`)
**Documentation Hub** - Features:
- Authentication check (currently `isLoggedIn = false` - TODO)
- Protected content sections
- API documentation links
- Governance documentation
- SDK documentation

### 4. Other Pages
- **Product** - Product features and benefits
- **Platforms** - Platform-specific information (humanoids, drones, wearables, environments)
- **Standards** - EDON standards (Minimum Insurable Standard, EOA, RAO)
- **News** - News articles and updates
- **About** - Company information
- **Contact** - Contact form
- **Download** - Download page (evaluation bundles)

---

## Current Authentication Status

### ❌ Not Implemented

The site currently has **no authentication system**:

1. **No Signup Page** - Users cannot create accounts
2. **No Login Page** - No user authentication
3. **No Session Management** - No user sessions or cookies
4. **No Protected Routes** - All pages are publicly accessible
5. **OEM Apply** - Currently just sends email, doesn't provision tenants

### 🔍 Evidence

- `src/pages/Docs.tsx` line 12: `const [isLoggedIn] = useState(false); // TODO: Implement actual auth check`
- No authentication components found
- No login/signup routes
- No API integration with tenant provisioning

---

## Integration Points for SaaS Model

### Required Additions

#### 1. **Signup Page** (`/signup`)
**Purpose:** User account creation with Stripe payment

**Flow:**
```
User enters email → Creates tenant → Stripe checkout → Provisioning → Redirect to console
```

**Components Needed:**
- Signup form component
- Stripe Checkout integration
- API call to `/billing/signup` endpoint
- Success/confirmation page

#### 2. **Login Page** (`/login`)
**Purpose:** User authentication

**Options:**
- Email/Password
- Magic Link (passwordless)
- Google OAuth

**Components Needed:**
- Login form component
- Magic link component
- OAuth integration
- Session management

#### 3. **Console Link** (`/console` or external)
**Purpose:** Link to `https://console.edon.ai`

**Options:**
- External redirect to console.edon.ai
- Or embed console UI in iframe/subdomain

#### 4. **Account/Profile Page** (`/account`)
**Purpose:** User account management

**Features:**
- View subscription status
- View API tokens
- Manage API keys
- Billing information
- Usage metrics

#### 5. **Protected Routes**
**Purpose:** Restrict access to authenticated users

**Pages to Protect:**
- `/docs` (full or partial)
- `/account`
- `/download` (for approved users)

---

## API Integration Points

### Current API Usage

**Email Service** (`src/lib/emailService.ts`):
- Sends OEM application emails via Resend API
- No tenant provisioning

### Required API Integration

**Tenant Provisioning** (`POST /billing/signup`):
```typescript
// New signup flow
const signup = async (email: string) => {
  const response = await fetch('https://api.edon.ai/billing/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  const { tenant_id, checkout_url, api_key } = await response.json();
  // Handle Stripe checkout or direct success
};
```

**Authentication** (to be implemented):
```typescript
// Login endpoint (to be created)
const login = async (email: string, password: string) => {
  // Exchange credentials for session
};

// Session validation
const validateSession = async () => {
  // Check if user session is valid
};
```

---

## Navigation Updates Needed

### Current Navigation
```typescript
const navLinks = [
  { to: "/product", label: "Product" },
  { to: "/platforms", label: "Platforms" },
  { to: "/docs", label: "Docs" },
  { to: "/standards", label: "Standards" },
  { to: "/news", label: "News" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
];
```

### Updated Navigation (with auth)
```typescript
const navLinks = [
  { to: "/product", label: "Product" },
  { to: "/platforms", label: "Platforms" },
  { to: "/docs", label: "Docs" },
  { to: "/standards", label: "Standards" },
  { to: "/news", label: "News" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
];

// Conditional links based on auth state
{isLoggedIn && (
  <>
    <Link to="/console">Console</Link>
    <Link to="/account">Account</Link>
  </>
)}

// CTA button changes
{isLoggedIn ? (
  <Link to="/console">
    <Button>OPEN CONSOLE</Button>
  </Link>
) : (
  <Link to="/signup">
    <Button>GET STARTED</Button>
  </Link>
)}
```

---

## File Structure

```
edon-sentinel-core/
├── src/
│   ├── components/
│   │   ├── Navigation.tsx          # Main nav (needs auth state)
│   │   ├── Footer.tsx              # Site footer
│   │   ├── TacticalHero.tsx        # Homepage hero
│   │   ├── TacticalMission.tsx     # Mission section
│   │   ├── TacticalTechnology.tsx # Technology section
│   │   ├── TacticalArchitecture.tsx # Architecture section
│   │   ├── TacticalFounder.tsx     # Founder section
│   │   ├── TacticalPartnerships.tsx # Partnerships section
│   │   └── ui/                     # shadcn-ui components
│   ├── pages/
│   │   ├── Index.tsx               # Homepage
│   │   ├── OEMApply.tsx            # OEM form (needs tenant integration)
│   │   ├── Docs.tsx                # Docs (needs auth protection)
│   │   ├── Product.tsx             # Product page
│   │   ├── Platforms.tsx           # Platforms page
│   │   ├── Standards.tsx            # Standards page
│   │   ├── News.tsx                 # News page
│   │   ├── About.tsx                # About page
│   │   ├── Contact.tsx              # Contact page
│   │   ├── Download.tsx             # Download page
│   │   ├── OEMConfirmation.tsx      # Confirmation page
│   │   └── NotFound.tsx             # 404 page
│   ├── lib/
│   │   ├── emailService.ts          # Email sending (Resend)
│   │   ├── emailValidation.ts       # Email validation
│   │   └── utils.ts                 # Utilities
│   ├── hooks/
│   │   ├── use-mobile.tsx           # Mobile detection
│   │   └── use-toast.ts             # Toast notifications
│   ├── App.tsx                      # Main app (routing)
│   └── main.tsx                     # Entry point
├── api/
│   └── send-email.ts                # Vercel serverless function
├── public/                           # Static assets
├── index.html                        # HTML template
├── package.json                      # Dependencies
└── vite.config.ts                    # Vite configuration
```

---

## Implementation Checklist

### Phase 1: Authentication Foundation
- [ ] Create `/signup` page with Stripe integration
- [ ] Create `/login` page (email/password, magic link, Google OAuth)
- [ ] Implement session management (cookies/JWT)
- [ ] Add authentication context/provider
- [ ] Create protected route wrapper component

### Phase 2: API Integration
- [ ] Integrate with `/billing/signup` endpoint
- [ ] Integrate with Stripe Checkout
- [ ] Handle Stripe webhooks (subscription updates)
- [ ] Create session validation endpoint
- [ ] Create login/logout endpoints

### Phase 3: User Experience
- [ ] Add "Console" link to navigation (when logged in)
- [ ] Add "Account" page for profile/subscription management
- [ ] Update CTA buttons based on auth state
- [ ] Protect `/docs` route (full or partial)
- [ ] Show subscription status in account page

### Phase 4: OEM Flow Integration
- [ ] Update `/oem/apply` to optionally create tenant
- [ ] Link OEM approval to tenant provisioning
- [ ] Send API credentials after OEM approval

---

## Current State Summary

### ✅ What Exists
- Marketing site with all content pages
- OEM application form (email-based)
- Documentation structure
- Navigation and routing
- UI component library (shadcn-ui)
- Email service integration

### ❌ What's Missing
- User authentication system
- Signup/login pages
- Session management
- Tenant provisioning integration
- Console link/access
- Account management
- Protected routes
- Stripe payment integration
- API token management UI

---

## Next Steps

1. **Review SaaS Model Document** (`docs/SAAS_MODEL.md` in edon-cav-engine)
2. **Design Authentication Flow** - Choose auth method (email/password vs magic link vs OAuth)
3. **Create Signup Page** - Integrate with `/billing/signup` endpoint
4. **Create Login Page** - Implement chosen authentication method
5. **Add Session Management** - Cookies or JWT tokens
6. **Update Navigation** - Add conditional links based on auth state
7. **Protect Routes** - Add authentication checks to protected pages
8. **Integrate Console** - Link to console.edon.ai or embed console UI

---

*Last Updated: 2025-01-27*
