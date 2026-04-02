"""Input validation middleware with size limits and strict validation."""

import os
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Size limits
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_JSON_DEPTH = 10
MAX_STRING_LENGTH = 100000  # 100 KB per string field
MAX_ARRAY_LENGTH = 10000
MAX_PARAMS_SIZE = 5 * 1024 * 1024  # 5 MB for action params

# Strict validation mode (reject instead of sanitize)
VALIDATE_STRICT = os.getenv("EDON_VALIDATE_STRICT", "true").lower() == "true"

# Dangerous patterns to reject (in strict mode)
DANGEROUS_PATTERNS = [
    (r"<script[^>]*>.*?</script>", "Script tags not allowed"),
    (r"javascript:", "JavaScript protocol not allowed"),
    (r"on\w+\s*=", "Event handlers not allowed"),
]


def check_dangerous_patterns(value: str) -> tuple[bool, str]:
    """Check for dangerous patterns in string.
    
    Args:
        value: String to check
        
    Returns:
        Tuple of (is_safe, error_message)
    """
    import re
    
    for pattern, error_msg in DANGEROUS_PATTERNS:
        if re.search(pattern, value, flags=re.IGNORECASE | re.DOTALL):
            return False, error_msg
    
    return True, ""


def validate_json_structure(data: Any, depth: int = 0, path: str = "") -> tuple[bool, str]:
    """Recursively validate JSON structure without mutation.
    
    Args:
        data: Data to validate
        depth: Current recursion depth
        path: Current path in JSON structure (for error messages)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if depth > MAX_JSON_DEPTH:
        return False, f"JSON depth exceeds maximum of {MAX_JSON_DEPTH} at path: {path}"
    
    if isinstance(data, dict):
        # Validate keys and values
        for key, value in data.items():
            if not isinstance(key, str):
                return False, f"Invalid key type at path: {path}. Keys must be strings."
            
            if len(key) > MAX_STRING_LENGTH:
                return False, f"Key length exceeds maximum of {MAX_STRING_LENGTH} at path: {path}.{key}"
            
            # Check dangerous patterns in keys
            if VALIDATE_STRICT:
                is_safe, error_msg = check_dangerous_patterns(key)
                if not is_safe:
                    return False, f"{error_msg} in key at path: {path}.{key}"
            
            # Recursively validate value
            new_path = f"{path}.{key}" if path else key
            is_valid, error_msg = validate_json_structure(value, depth + 1, new_path)
            if not is_valid:
                return False, error_msg
        
        return True, ""
    
    elif isinstance(data, list):
        if len(data) > MAX_ARRAY_LENGTH:
            return False, f"Array length exceeds maximum of {MAX_ARRAY_LENGTH} at path: {path}"
        
        # Validate each item
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]"
            is_valid, error_msg = validate_json_structure(item, depth + 1, new_path)
            if not is_valid:
                return False, error_msg
        
        return True, ""
    
    elif isinstance(data, str):
        if len(data) > MAX_STRING_LENGTH:
            return False, f"String length exceeds maximum of {MAX_STRING_LENGTH} at path: {path}"
        
        # Check dangerous patterns in strict mode
        if VALIDATE_STRICT:
            is_safe, error_msg = check_dangerous_patterns(data)
            if not is_safe:
                return False, f"{error_msg} at path: {path}"
        
        return True, ""
    
    else:
        # Other types (int, float, bool, None) are valid
        return True, ""


def validate_action_params(params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate action parameters without mutation.
    
    Args:
        params: Action parameters dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check size
    params_str = json.dumps(params)
    if len(params_str) > MAX_PARAMS_SIZE:
        return False, f"Action parameters exceed maximum size of {MAX_PARAMS_SIZE} bytes"
    
    # Validate structure (reject if invalid, don't mutate)
    is_valid, error_msg = validate_json_structure(params, path="action.params")
    if not is_valid:
        return False, f"Invalid action parameters: {error_msg}"
    
    return True, None


def normalize_whitespace(value: str) -> str:
    """Normalize whitespace (only for specific fields that need it).
    
    This is a narrow normalization - only trim leading/trailing whitespace.
    Used only for specific fields that explicitly need normalization.
    
    Args:
        value: String to normalize
        
    Returns:
        Normalized string
    """
    return value.strip()


class ValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate request inputs (reject invalid, don't mutate)."""
    
    # Endpoints that don't need validation
    EXCLUDED_ENDPOINTS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc"
    }
    
    async def dispatch(self, request: Request, call_next):
        """Process request and validate inputs."""
        # Skip validation for excluded endpoints
        if request.url.path in self.EXCLUDED_ENDPOINTS:
            return await call_next(request)
        
        # Check request size BEFORE reading body (DoS protection)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > MAX_REQUEST_SIZE:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={"detail": f"Request size exceeds maximum of {MAX_REQUEST_SIZE} bytes"}
                    )
            except ValueError:
                pass
        
        # Validate JSON body for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.json()
                
                # Validate structure (reject if invalid)
                is_valid, error_msg = validate_json_structure(body)
                if not is_valid:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": f"Invalid request body: {error_msg}"}
                    )
                
                # Special validation for /execute endpoint
                if request.url.path == "/execute":
                    if "action" in body and "params" in body.get("action", {}):
                        is_valid, error_msg = validate_action_params(body["action"]["params"])
                        if not is_valid:
                            return JSONResponse(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                content={"detail": error_msg}
                            )
                
                # Store original body (no mutation) - only normalize specific fields if needed
                # For now, we keep the original body as-is
                async def receive():
                    return {
                        "type": "http.request",
                        "body": json.dumps(body).encode()
                    }
                
                request._receive = receive
                
            except json.JSONDecodeError:
                # Invalid JSON - let FastAPI handle it
                pass
            except HTTPException as e:
                # Re-raise HTTPException as JSONResponse for consistency
                return JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail},
                    headers=e.headers if hasattr(e, 'headers') else {}
                )
            except Exception as e:
                logger.error(f"Validation error: {str(e)}")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": f"Validation error: {str(e)}"}
                )
        
        return await call_next(request)
