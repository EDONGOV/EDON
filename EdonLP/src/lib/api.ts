const GATEWAY_URL =
  (import.meta.env.VITE_GATEWAY_URL as string | undefined) ??
  'https://api.edoncore.com'

export interface SignupPayload {
  email: string
  company: string
  plan: string
  use_case?: string
}

export interface SignupResponse {
  tenant_id: string
  checkout_url: string
  plan: string
}

export async function postSignup(payload: SignupPayload): Promise<SignupResponse> {
  const res = await fetch(`${GATEWAY_URL}/billing/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Request failed (HTTP ${res.status})`)
  }
  return res.json() as Promise<SignupResponse>
}
