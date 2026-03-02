"""Shared container log snapshot logic with redaction."""

import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)
_MAX_LOG_SNAPSHOT_LINES = 200
_REDACTED = "[REDACTED]"
_EMAIL_REDACTED = "[EMAIL_REDACTED]"

_DEFAULT_LOG_REDACTION_RULE_NAMES: tuple[str, ...] = (
    "authorization_bearer",
    "credential_key_values",
    "email_addresses",
)

_DEFAULT_LOG_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s]+)"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        _EMAIL_REDACTED,
    ),
)


def _load_extra_log_redaction_patterns() -> tuple[re.Pattern[str], ...]:
    raw = settings.log_snapshot_redaction_extra_patterns.strip()
    if not raw:
        return ()
    compiled: list[re.Pattern[str]] = []
    for chunk in raw.split("||"):
        candidate = chunk.strip()
        if not candidate:
            continue
        try:
            compiled.append(re.compile(candidate))
        except re.error:
            logger.warning(
                "Ignoring invalid LOG_SNAPSHOT_REDACTION_EXTRA_PATTERNS regex: %s",
                candidate,
            )
    return tuple(compiled)


def get_log_redaction_preview() -> dict[str, Any]:
    """Return non-sensitive metadata for settings UI."""
    extra_patterns = _load_extra_log_redaction_patterns()
    return {
        "enabled": settings.log_snapshot_redaction_enabled,
        "default_rules": list(_DEFAULT_LOG_REDACTION_RULE_NAMES),
        "extra_rules_count": len(extra_patterns),
    }


def snapshot_container_logs(container: Any, *, tail: int = 100) -> list[str]:
    """Fetch last N log lines from container with optional redaction."""
    safe_tail = max(1, min(tail, _MAX_LOG_SNAPSHOT_LINES))
    raw_logs = container.logs(tail=safe_tail).decode("utf-8", errors="replace")
    lines: list[str] = []
    for line in raw_logs.splitlines():
        if not line.strip():
            continue
        sanitized = line[:1000]
        if settings.log_snapshot_redaction_enabled:
            for pattern, replacement in _DEFAULT_LOG_REDACTION_PATTERNS:
                sanitized = pattern.sub(replacement, sanitized)
            for pattern in _load_extra_log_redaction_patterns():
                sanitized = pattern.sub(_REDACTED, sanitized)
        lines.append(sanitized)
    return lines
