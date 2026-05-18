/**
 * Gateway client: when BFF is enabled, calls go to our /api/proxy which verifies Clerk
 * and forwards to the gateway. API key never sent from browser; token goes to BFF only.
 */

const USE_BFF = import.meta.env.VITE_USE_BFF !== "false";
const DIRECT_GATEWAY_URL =
  import.meta.env.VITE_GATEWAY_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  "https://edon-gateway.fly.dev";

/** Base URL for gateway requests (no trailing slash). When BFF is on, this is the proxy base. */
export function getGatewayBase(): string {
  if (USE_BFF && typeof window !== "undefined") {
    return window.location.origin;
  }
  return DIRECT_GATEWAY_URL.replace(/\/$/, "");
}

/** Full URL for a gateway path (e.g. /billing/status or /timeseries?days=7). */
export function getGatewayUrl(path: string): string {
  const base = getGatewayBase();
  if (USE_BFF && typeof window !== "undefined") {
    const fullPath = path.startsWith("/") ? path : `/${path}`;
    return `${base}/api/proxy?path=${encodeURIComponent(fullPath)}`;
  }
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Auth headers for gateway (or BFF) requests. Use the same token from Clerk or stored key. */
export function getGatewayAuthHeaders(token: string | null | undefined): Record<string, string> {
  const t = token && String(token).trim();
  if (!t) return {};
  if (USE_BFF) {
    return { Authorization: `Bearer ${t}` };
  }
  return { "X-EDON-TOKEN": t };
}

/** URL to show in UI (e.g. "your endpoint") — always the real gateway, not the proxy. */
export function getDisplayGatewayUrl(): string {
  return DIRECT_GATEWAY_URL.replace(/\/$/, "");
}

export { USE_BFF };
