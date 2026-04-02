"""Logging Filter that scrubs sensitive data from all log records."""

import logging
from .sensitive_patterns import scrub_string


class LogScrubberFilter(logging.Filter):
    """A logging.Filter that redacts sensitive values from every log record.

    Scrubs:
    - record.msg  (the format string or pre-formatted message)
    - record.args (tuple or dict of %-format arguments)

    Always returns True (passes all records through after scrubbing).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub the message string itself
        if isinstance(record.msg, str):
            record.msg = scrub_string(record.msg)

        # Scrub args (tuple or dict used with %-formatting)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    scrub_string(a) if isinstance(a, str) else a
                    for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: (scrub_string(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }

        return True  # always pass through after scrubbing
