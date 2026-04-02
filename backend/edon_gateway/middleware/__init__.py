"""EDON Gateway middleware package."""

from .auth import (
    AuthMiddleware,
    verify_token,
    get_token_from_header,
    verify_clerk_token,
    resolve_tenant_for_clerk,
)
from .mag_validation import MagValidationMiddleware
from .rate_limit import RateLimitMiddleware, check_rate_limit, increment_rate_limit, ANONYMOUS_LIMITS
from .validation import ValidationMiddleware, validate_action_params, validate_json_structure

__all__ = [
    "AuthMiddleware",
    "verify_token",
    "get_token_from_header",
    "verify_clerk_token",
    "resolve_tenant_for_clerk",
    "MagValidationMiddleware",
    "RateLimitMiddleware",
    "check_rate_limit",
    "increment_rate_limit",
    "ANONYMOUS_LIMITS",
    "ValidationMiddleware",
    "validate_action_params",
    "validate_json_structure",
]
