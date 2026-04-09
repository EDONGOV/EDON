"""Rate limiting middleware using database counters."""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from datetime import datetime, UTC
from typing import Optional, Dict, Any
import logging
import os
import json

from ..persistence import get_db
from ..config import config

logger = logging.getLogger(__name__)

# ---- Redis backend (optional) ----
# If REDIS_URL is set, rate limiting counters are stored in Redis (fast, atomic, auto-expiring).
# If not set, falls back to the existing PostgreSQL/SQLite counter table.
_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_redis_client = None

if _REDIS_URL:
    try:
        import redis as _redis_lib
        _redis_client = _redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_timeout=1)
        _redis_client.ping()
        logging.getLogger(__name__).info(f"Rate limiter: Redis backend active ({_REDIS_URL[:30]}...)")
    except Exception as _e:
        logging.getLogger(__name__).warning(f"Rate limiter: Redis unavailable ({_e}), using DB backend")
        _redis_client = None

# Check if we're in development mode
ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("EDON_ENV", "production")).lower()
IS_DEVELOPMENT = ENVIRONMENT in ["development", "dev", "local"]

# Rate limit configuration - always enabled in production regardless of ENVIRONMENT.
# Only an explicit EDON_RATE_LIMIT_ENABLED=false can disable rate limiting, and only
# when the environment is also a recognized non-production value.
rate_limit_setting = os.getenv("EDON_RATE_LIMIT_ENABLED", "").lower()
if rate_limit_setting:
    RATE_LIMIT_ENABLED = rate_limit_setting == "true"
else:
    # Check multiple env indicators for production
    env = os.getenv("ENVIRONMENT", "").lower()
    RATE_LIMIT_ENABLED = env not in ("development", "dev", "local", "test")

# Default limits (per agent_id) - updated to specification: 10,000 requests/min
DEFAULT_LIMITS = {
    "per_minute": 10000,      # 10,000/min per specification
    "per_hour": 300000,       # 300,000/hour (proportional: 10k * 30)
    "per_day": 20000000,      # 20,000,000/day (supports 20M decisions/day across 100 systems)
}

# Enterprise ceiling (absolute maximum for any customer)
ENTERPRISE_CEILING = {
    "per_minute": 1000000,    # 1M/min maximum
    "per_hour": 10000000,     # 10M/hour maximum
    "per_day": 100000000,     # 100M/day maximum
}

# Anonymous request limits (much stricter - track by IP)
ANONYMOUS_LIMITS = {
    "per_minute": 60 if IS_DEVELOPMENT else 10,       # 60/min in dev, 10/min in prod
    "per_hour": 1000 if IS_DEVELOPMENT else 100,      # 1000/hour in dev, 100/hour in prod
    "per_day": 5000 if IS_DEVELOPMENT else 500,       # 5000/day in dev, 500/day in prod
}

# Higher limits for polling endpoints (dashboard/analytics)
POLLING_ENDPOINT_LIMITS = {
    "per_minute": 600,    # 600/min — dashboard fires 8+ requests per load/refresh
    "per_hour": 10000,
    "per_day": 100000,
}


def get_rate_limit_key(agent_id: str, window: str) -> str:
    """Generate rate limit counter key.
    
    Args:
        agent_id: Agent identifier
        window: Time window (minute, hour, day)
        
    Returns:
        Counter key string
    """
    now = datetime.now(UTC)
    
    if window == "minute":
        time_key = now.strftime("%Y%m%d%H%M")
    elif window == "hour":
        time_key = now.strftime("%Y%m%d%H")
    elif window == "day":
        time_key = now.strftime("%Y%m%d")
    else:
        raise ValueError(f"Invalid window: {window}")
    
    return f"rate_limit:{agent_id}:{window}:{time_key}"


def _redis_get_counter(key: str) -> int:
    """Get counter value from Redis. Returns 0 on error or if Redis not available."""
    if not _redis_client:
        return 0
    try:
        val = _redis_client.get(key)  # type: ignore[union-attr]
        return int(val) if val else 0
    except Exception:
        return 0


def _redis_increment_counter(key: str, window: str):
    """Increment Redis counter with appropriate TTL."""
    if not _redis_client:
        return
    ttl_map = {"minute": 70, "hour": 3700, "day": 90000}
    ttl = ttl_map.get(window, 70)
    try:
        pipe = _redis_client.pipeline()  # type: ignore[union-attr]
        pipe.incr(key)
        pipe.expire(key, ttl)
        pipe.execute()
    except Exception as e:
        logger.warning(f"Redis increment failed: {e}")


def check_rate_limit(agent_id: str, limits: Optional[dict] = None) -> tuple[bool, Optional[str]]:
    """Check if agent has exceeded rate limits.

    Uses Redis if available, otherwise DB counters.

    Args:
        agent_id: Agent identifier
        limits: Custom limits dict (defaults to DEFAULT_LIMITS)

    Returns:
        Tuple of (allowed, error_message)
    """
    if not RATE_LIMIT_ENABLED:
        return True, None

    if limits is None:
        limits = DEFAULT_LIMITS

    for window, limit in limits.items():
        if not window.startswith("per_"):
            continue
        window_name = window.replace("per_", "")
        counter_key = get_rate_limit_key(agent_id, window_name)

        if _redis_client:
            current_count = _redis_get_counter(counter_key)
        else:
            db = get_db()
            current_count = db.get_counter(counter_key)

        if current_count >= limit:
            return False, f"Rate limit exceeded: {limit} requests per {window_name}"

    return True, None


def increment_rate_limit(agent_id: str):
    """Increment rate limit counters for agent.

    Uses Redis if available (INCR + EXPIRE), otherwise DB counters.
    """
    if not RATE_LIMIT_ENABLED:
        return

    for window in ["minute", "hour", "day"]:
        counter_key = get_rate_limit_key(agent_id, window)
        if _redis_client:
            _redis_increment_counter(counter_key, window)
        else:
            db = get_db()
            db.increment_counter(counter_key, 1)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting per agent."""
    
    # Endpoints that don't count toward rate limits
    EXCLUDED_ENDPOINTS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/metrics",
        "/stats",
        # Auth/onboarding endpoints — protected by Clerk JWT; rate limiting here
        # would block new users from ever creating accounts.
        "/auth/signup",
        "/auth/session",
        "/billing/plans",
        "/billing/checkout",
        "/billing/webhook",
        "/admin/bootstrap-api-key",
    }
    
    # Endpoints that use polling (higher rate limits)
    POLLING_ENDPOINTS = {
        "/decisions/query",
        "/audit/query",
        "/timeseries",
        "/block-reasons",
        "/compliance/health",
        "/compliance/review/queue",
        "/api-keys/me",
        "/api-keys",
        "/agents",
        "/stats",
        "/health",
        "/settings/ip-allowlist",
    }

    # Only these count toward tenant usage (one governance decision per request)
    USAGE_COUNTED_ENDPOINTS = {
        ("POST", "/v1/action"),
        ("POST", "/execute"),
        ("POST", "/clawdbot/invoke"),
        ("POST", "/edon/invoke"),
        ("POST", "/agent/invoke"),
    }
    
    def __init__(self, app, limits: Optional[dict] = None):
        """Initialize rate limit middleware.
        
        Args:
            app: FastAPI application
            limits: Custom rate limits (defaults to DEFAULT_LIMITS)
        """
        super().__init__(app)
        self.limits = limits or DEFAULT_LIMITS
    
    async def dispatch(self, request: Request, call_next):
        """Process request and check rate limits.
        
        Rate limits are applied BEFORE reading the full body to prevent DoS.
        Anonymous requests (no agent_id) are heavily limited.
        """
        # Skip rate limiting for excluded endpoints
        if request.url.path in self.EXCLUDED_ENDPOINTS:
            return await call_next(request)
        
        # In demo mode, skip rate limits for Telegram traffic
        if config.DEMO_MODE:
            header_agent = request.headers.get("X-Agent-ID") or request.headers.get("X-EDON-Agent-ID")
            if header_agent and header_agent.startswith("telegram:"):
                return await call_next(request)

        # Skip rate limit check if disabled (still run call_next and usage counting below)
        if not RATE_LIMIT_ENABLED:
            response = await call_next(request)
            if 200 <= response.status_code < 300:
                path = request.url.path.rstrip("/")
                if (
                    hasattr(request.state, "tenant_id")
                    and (request.method, path) in self.USAGE_COUNTED_ENDPOINTS
                ):
                    from ..persistence import get_db
                    db = get_db()
                    tenant_id = request.state.tenant_id
                    try:
                        tenant_exists = True
                        if hasattr(db, "get_tenant"):
                            tenant_exists = bool(db.get_tenant(tenant_id))
                        if tenant_id and tenant_exists:
                            db.increment_tenant_usage(tenant_id, 1)
                    except Exception:
                        pass
            return response

        # Extract agent_id from headers/query params ONLY (no body read for DoS protection)
        agent_id = None

        # Try to get from query params first (doesn't require body read)
        agent_id = request.query_params.get("agent_id")

        # Try to get from headers
        if not agent_id:
            agent_id = request.headers.get("X-Agent-ID")
        if not agent_id:
            agent_id = request.headers.get("X-EDON-Agent-ID")

        # Fall back to the auth token itself as the rate limit key so that
        # authenticated users (API key or Clerk JWT) are never bucketed as
        # "anonymous" just because they omitted X-Agent-ID.
        auth_token_key = None
        if not agent_id:
            raw_token = (
                request.headers.get("X-EDON-TOKEN", "").strip()
                or (request.headers.get("Authorization", "")[7:].strip()
                    if request.headers.get("Authorization", "").startswith("Bearer ") else "")
            )
            if raw_token:
                # Use a short prefix of the token hash — uniquely identifies the
                # caller without exposing the full token in DB counter keys.
                import hashlib
                auth_token_key = "tok:" + hashlib.sha256(raw_token.encode()).hexdigest()[:16]

        # Determine which limits to use
        is_anonymous = agent_id is None and auth_token_key is None
        is_polling_endpoint = request.url.path in self.POLLING_ENDPOINTS

        # Use higher limits for polling endpoints
        if is_polling_endpoint:
            limits_to_use = POLLING_ENDPOINT_LIMITS
        elif is_anonymous:
            limits_to_use = ANONYMOUS_LIMITS
        else:
            limits_to_use = self.limits

        # Prefer explicit agent_id > token-derived key > "anonymous"
        rate_limit_key = agent_id or auth_token_key or "anonymous"
        
        # Check rate limit BEFORE processing request
        allowed, error_msg = check_rate_limit(rate_limit_key, limits_to_use)
        
        if not allowed:
            # For anonymous requests, provide more specific error
            if is_anonymous:
                error_msg = f"{error_msg}. Anonymous requests are heavily rate-limited. Provide agent_id in X-Agent-ID header or query parameter."
            
            # Calculate retry-after based on which limit was hit
            _err = error_msg or ""
            retry_after = "60"  # Default 60 seconds
            if "per_minute" in _err:
                retry_after = "60"    # Wait 1 minute
            elif "per_hour" in _err:
                retry_after = "3600"  # Wait 1 hour
            elif "per_day" in _err:
                retry_after = "86400" # Wait 1 day
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": error_msg},
                headers={"Retry-After": retry_after},
            )
        
        # Process request
        response = await call_next(request)
        
        # Increment counter only on successful requests (2xx status)
        if 200 <= response.status_code < 300:
            increment_rate_limit(rate_limit_key)
            # Only count tenant usage for governance decision endpoints (one decision per call)
            path = request.url.path.rstrip("/")
            if (
                hasattr(request.state, "tenant_id")
                and (request.method, path) in self.USAGE_COUNTED_ENDPOINTS
            ):
                from ..persistence import get_db
                db = get_db()
                tenant_id = request.state.tenant_id
                # Avoid 500s for legacy/dev env-token flows with no tenant record.
                try:
                    tenant_exists = True
                    if hasattr(db, "get_tenant"):
                        tenant_exists = bool(db.get_tenant(tenant_id))
                    if tenant_id and tenant_exists:
                        db.increment_tenant_usage(tenant_id, 1)
                except Exception:
                    # Usage metering must never break request path.
                    pass
        return response
