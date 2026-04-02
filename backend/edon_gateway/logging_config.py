"""Structured logging configuration for EDON Gateway."""

import logging
import json
import sys
from datetime import datetime, UTC
from typing import Any, Dict
import os


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        # Add standard fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "agent_id"):
            log_data["agent_id"] = record.agent_id
        if hasattr(record, "intent_id"):
            log_data["intent_id"] = record.intent_id
        
        return json.dumps(log_data)


class StandardFormatter(logging.Formatter):
    """Standard formatter for human-readable logs."""
    
    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logging():
    """Setup logging configuration."""
    log_level = os.getenv("EDON_LOG_LEVEL", "INFO").upper()
    json_logging = os.getenv("EDON_JSON_LOGGING", "false").lower() == "true"
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Set formatter
    if json_logging:
        formatter = JSONFormatter()
    else:
        formatter = StandardFormatter()
    
    console_handler.setFormatter(formatter)

    # Attach log scrubber to redact sensitive data (API keys, tokens, passwords)
    try:
        from .security.log_scrubber import LogScrubberFilter
        console_handler.addFilter(LogScrubberFilter())
    except Exception:
        pass  # Never break logging setup

    root_logger.addHandler(console_handler)
    
    # Set levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
