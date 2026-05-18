/**
 * EDON SDK error hierarchy.
 *
 * Every error thrown by the SDK is a subclass of EdonError.
 * Catch the specific type you care about, or EdonError for everything.
 *
 *   import { AuthenticationError, RateLimitError, EdonError } from '@edon/sdk'
 *
 *   try {
 *     await client.evaluate(...)
 *   } catch (err) {
 *     if (err instanceof AuthenticationError) { // bad API key }
 *     if (err instanceof RateLimitError) { await sleep((err.retryAfter ?? 5) * 1000) }
 *     if (err instanceof EdonError) { // catch-all }
 *   }
 */

export class EdonError extends Error {
  constructor(message: string) {
    super(message)
    this.name = this.constructor.name
    Object.setPrototypeOf(this, new.target.prototype)
  }
}

export class APIError extends EdonError {
  readonly statusCode: number
  readonly requestId: string | null
  readonly body: Record<string, unknown>

  constructor(
    message: string,
    opts: {
      statusCode: number
      requestId?: string | null
      body?: Record<string, unknown>
    },
  ) {
    super(message)
    this.statusCode = opts.statusCode
    this.requestId = opts.requestId ?? null
    this.body = opts.body ?? {}
  }

  static fromResponse(
    statusCode: number,
    body: Record<string, unknown>,
    requestId: string | null,
  ): APIError {
    const raw =
      (body['detail'] as string | undefined) ??
      (body['message'] as string | undefined) ??
      (body['error'] as string | undefined) ??
      `HTTP ${statusCode}`
    const msg = typeof raw === 'object' ? JSON.stringify(raw) : String(raw)
    const opts = { statusCode, requestId, body }

    if (statusCode === 401) return new AuthenticationError(msg, opts)
    if (statusCode === 403) return new PermissionDeniedError(msg, opts)
    if (statusCode === 404) return new NotFoundError(msg, opts)
    if (statusCode === 422) return new UnprocessableEntityError(msg, opts)
    if (statusCode === 429) {
      const retryAfter = typeof body['retry_after'] === 'number' ? body['retry_after'] : null
      return new RateLimitError(msg, { ...opts, retryAfter })
    }
    if (statusCode >= 500) return new GatewayError(msg, opts)
    return new APIError(msg, opts)
  }
}

/** 401 — invalid or missing API key. Check EDON_API_KEY. */
export class AuthenticationError extends APIError {}

/** 403 — your API key does not have permission for this operation. */
export class PermissionDeniedError extends APIError {}

/** 404 — the requested resource does not exist. */
export class NotFoundError extends APIError {}

/** 422 — the request was well-formed but failed validation. */
export class UnprocessableEntityError extends APIError {}

/** 429 — you have sent too many requests. Back off before retrying. */
export class RateLimitError extends APIError {
  readonly retryAfter: number | null

  constructor(
    message: string,
    opts: {
      statusCode: number
      requestId?: string | null
      body?: Record<string, unknown>
      retryAfter?: number | null
    },
  ) {
    super(message, opts)
    this.retryAfter = opts.retryAfter ?? null
  }
}

/** 5xx — the EDON gateway returned a server-side error. Usually transient. */
export class GatewayError extends APIError {}

/** Could not reach the EDON gateway (DNS, refused connection, timeout). */
export class APIConnectionError extends EdonError {
  readonly cause: unknown
  constructor(message: string, cause?: unknown) {
    super(message)
    this.cause = cause
  }
}

/** The request to the EDON gateway timed out. Safe to retry — governance is idempotent. */
export class APITimeoutError extends APIConnectionError {}
