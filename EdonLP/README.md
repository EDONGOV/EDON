# EDON Sentinel Core - Public Website

**Purpose**: Public marketing website and user portal where users sign up, pay for EDON subscriptions, and access their account.

This is the **entry point** for customers. Users can:
- Learn about EDON platform
- Sign up for accounts (via Clerk authentication)
- Subscribe to plans (via Stripe payments)
- Access their account dashboard
- Redirect to the Agent Console after payment

## Architecture

This website is the **public-facing component** that:
- Handles user authentication (Clerk)
- Processes payments (Stripe)
- Manages subscriptions
- Redirects paid users to the Agent Console

```
User → Public Website (this) → Sign Up/Payment → Agent Console → EDON Gateway → Clawdbot/Agent
```

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Clerk account (for authentication)
- Stripe account (for payments)

### Installation

```bash
# Install dependencies
npm install

# Create .env.local file
cp env.example .env.local

# Edit .env.local and add:
# - VITE_CLERK_PUBLISHABLE_KEY (from Clerk dashboard)
# - VITE_GATEWAY_URL (EDON Gateway URL)
# - VITE_API_BASE_URL (EDON API URL)
# - VITE_CONSOLE_URL (Agent Console URL)

# Start development server
npm run dev
```

The website will start on `http://localhost:5173` (or next available port).

### Environment Variables

Create `.env.local`:

```env
# Clerk Authentication
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...

# EDON API - CAV Engine (core functionality)
VITE_API_BASE_URL=https://api.edoncore.com

# EDON Gateway - SaaS/Billing endpoints
VITE_GATEWAY_URL=https://api.edoncore.com

# Agent Console URL (where users go after payment)
VITE_CONSOLE_URL=https://console.edon.ai
```

## Features

- **Homepage**: Marketing content and product information
- **Sign Up / Login**: User authentication via Clerk
- **Pricing**: Subscription plans and Stripe checkout
- **Account**: User dashboard and subscription management
- **Console Redirect**: After payment, redirects to Agent Console

## User Flow

1. User visits website → Signs up → Pays subscription
2. Stripe webhook → Provisions tenant in EDON Gateway
3. User redirected to Agent Console (`/console` route)
4. Agent Console connects to EDON Gateway API
5. User monitors their clawdbot/agent through EDON

## Development

```bash
# Start dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Production Deployment

Deploy to Vercel:

```bash
# Set environment variables in Vercel dashboard:
# - VITE_CLERK_PUBLISHABLE_KEY
# - VITE_GATEWAY_URL
# - VITE_API_BASE_URL
# - VITE_CONSOLE_URL

# Deploy
vercel deploy
```

**Production URL**: https://edoncore.com

## Related Components

- **edon-agent-ui** (`C:\Users\cjbig\Desktop\edon-agent-ui`): Agent Console where users monitor their agents
- **edon_gateway** (`C:\Users\cjbig\Desktop\EDON\edon-cav-engine\edon_gateway`): Backend API gateway

See `C:\Users\cjbig\Desktop\EDON\edon-cav-engine\STARTUP_GUIDE.md` for full stack startup instructions.

## Technologies

- React 18
- TypeScript
- Vite
- Clerk (authentication)
- Stripe (payments)
- shadcn-ui components
- Tailwind CSS
- React Router
