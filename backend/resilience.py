"""TeacherOS Resilience and Error Handling Engine (Day 26).

Provides structured error categories, bounded retries with jitter, safe fallback execution,
and comprehensive sensitive data redaction for production logs and telemetry.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import random
import re
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Structured Error Categories
# ---------------------------------------------------------------------------

class TeacherOSError(Exception):
    """Base class for all structured TeacherOS operational errors."""
    def __init__(self, message: str, subsystem: str = "core", recommended_action: str = "retry"):
        super().__init__(message)
        self.message = message
        self.subsystem = subsystem
        self.recommended_action = recommended_action


class ProviderTimeoutError(TeacherOSError):
    """Raised when an external AI provider fails to respond within timeout limits."""
    def __init__(self, message: str = "AI Provider request timed out"):
        super().__init__(message, subsystem="ai_gateway", recommended_action="retry_with_backoff")


class ProviderInvalidResponseError(TeacherOSError):
    """Raised when an external AI provider returns invalid/malformed JSON or empty output."""
    def __init__(self, message: str = "AI Provider returned malformed or empty response"):
        super().__init__(message, subsystem="ai_gateway", recommended_action="regenerate")


class DatabaseLockError(TeacherOSError):
    """Raised when SQLite database is busy or locked beyond the timeout."""
    def __init__(self, message: str = "Database busy or write transaction locked"):
        super().__init__(message, subsystem="database", recommended_action="retry_with_jitter")


class DiskSpaceLowError(TeacherOSError):
    """Raised when remaining server disk space falls below safe threshold."""
    def __init__(self, message: str = "Disk space below minimum operational threshold"):
        super().__init__(message, subsystem="storage", recommended_action="rotate_logs_and_backups")


class ExportFailureError(TeacherOSError):
    """Raised when Word (.docx) or PDF (.pdf) rendering encounters a document error."""
    def __init__(self, message: str = "Document export rendering failed"):
        super().__init__(message, subsystem="exports", recommended_action="check_content_structure")


# ---------------------------------------------------------------------------
# Bounded Retry with Exponential Backoff and Jitter
# ---------------------------------------------------------------------------

def execute_with_retry(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 0.05,
    max_delay: float = 1.0,
    jitter: bool = True,
    retry_exceptions: tuple[type[Exception], ...] = (
        TimeoutError,
        ProviderTimeoutError,
        DatabaseLockError,
    ),
    **kwargs: Any,
) -> T:
    """Execute a synchronous function with bounded exponential backoff and jitter."""
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except retry_exceptions as exc:
            attempt += 1
            if attempt > max_retries:
                logger.error(
                    "Operation failed after %d retries. Subsystem: %s. Error: %s",
                    max_retries,
                    getattr(exc, "subsystem", "unknown"),
                    redact_sensitive_text(str(exc)),
                )
                raise

            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay += random.uniform(0, delay * 0.5)

            logger.warning(
                "Transient error on attempt %d/%d (backing off %.2fs): %s",
                attempt,
                max_retries,
                delay,
                redact_sensitive_text(str(exc)),
            )
            time.sleep(delay)


async def execute_with_retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 0.05,
    max_delay: float = 1.0,
    jitter: bool = True,
    retry_exceptions: tuple[type[Exception], ...] = (
        TimeoutError,
        ProviderTimeoutError,
        DatabaseLockError,
    ),
    **kwargs: Any,
) -> Any:
    """Execute an asynchronous coroutine with bounded exponential backoff and jitter."""
    attempt = 0
    while True:
        try:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except retry_exceptions as exc:
            attempt += 1
            if attempt > max_retries:
                logger.error(
                    "Async operation failed after %d retries. Error: %s",
                    max_retries,
                    redact_sensitive_text(str(exc)),
                )
                raise

            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay += random.uniform(0, delay * 0.5)

            logger.warning(
                "Transient async error on attempt %d/%d (backing off %.2fs): %s",
                attempt,
                max_retries,
                delay,
                redact_sensitive_text(str(exc)),
            )
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Sensitive Data Redaction
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS = [
    # OpenRouter API keys: sk-or-v1-...
    (re.compile(r"sk-or-v1-[a-zA-Z0-9]{16,}", re.IGNORECASE), "sk-or-v1-[REDACTED]"),
    # Telegram Bot tokens: 123456789:ABCdef...
    (re.compile(r"\b[0-9]{8,14}:[a-zA-Z0-9_-]{15,}\b"), "[BOT_TOKEN_REDACTED]"),
    # Generic Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE), "Bearer [REDACTED]"),
    # Email addresses: user@example.com -> u***@example.com
    (re.compile(r"\b([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b"), r"\1***@\2"),
    # Credit Card PANs (16 digits with optional dashes/spaces)
    (re.compile(r"\b(?:\d{4}[ -]?){3}(\d{4})\b"), r"****-****-****-\1"),
]


def redact_sensitive_text(text: str) -> str:
    """Redact API keys, tokens, emails, PANs, and sensitive credentials from log text."""
    if not isinstance(text, str):
        return str(text)

    redacted = text
    for pattern, replacement in _TOKEN_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
