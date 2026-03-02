"""Runtime settings persistence and application helpers."""

import sqlite3
from datetime import UTC, datetime
from typing import Any, Literal

from app.config import settings
from app.db.init import get_db_path

RuntimeSettingKey = Literal[
    "sse_max_connections",
    "alert_engine_enabled",
    "alert_poll_seconds",
    "restart_action_ttl_seconds",
    "restart_token_rate_limit_window_seconds",
    "restart_token_rate_limit_max_attempts",
    "audit_retention_days",
    "audit_retention_auto_enabled",
    "audit_retention_poll_seconds",
]
RuntimeSettingValue = int | bool

ALLOWED_RUNTIME_SETTINGS: tuple[RuntimeSettingKey, ...] = (
    "sse_max_connections",
    "alert_engine_enabled",
    "alert_poll_seconds",
    "restart_action_ttl_seconds",
    "restart_token_rate_limit_window_seconds",
    "restart_token_rate_limit_max_attempts",
    "audit_retention_days",
    "audit_retention_auto_enabled",
    "audit_retention_poll_seconds",
)

_BOOL_RUNTIME_SETTINGS = {
    "alert_engine_enabled",
    "audit_retention_auto_enabled",
}


def _serialize_value(*, key: RuntimeSettingKey, value: RuntimeSettingValue) -> str:
    if key in _BOOL_RUNTIME_SETTINGS:
        return "1" if bool(value) else "0"
    return str(int(value))


def _deserialize_value(*, key: RuntimeSettingKey, value: str) -> RuntimeSettingValue:
    if key in _BOOL_RUNTIME_SETTINGS:
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "on"}
    return int(value)


def list_runtime_settings() -> dict[str, RuntimeSettingValue]:
    """Return persisted runtime setting overrides."""
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT key, value FROM runtime_settings WHERE key IN ({placeholders})".format(
                placeholders=",".join("?" for _ in ALLOWED_RUNTIME_SETTINGS)
            ),
            ALLOWED_RUNTIME_SETTINGS,
        ).fetchall()
    parsed: dict[str, RuntimeSettingValue] = {}
    for row in rows:
        key = str(row["key"])
        if key not in ALLOWED_RUNTIME_SETTINGS:
            continue
        parsed[key] = _deserialize_value(key=key, value=str(row["value"]))
    return parsed


def upsert_runtime_settings(*, values: dict[RuntimeSettingKey, RuntimeSettingValue], actor: str) -> None:
    """Persist selected runtime settings with actor metadata."""
    if not values:
        return
    updated_at = datetime.now(UTC).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        conn.executemany(
            """
            INSERT INTO runtime_settings(key, value, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            [
                (key, _serialize_value(key=key, value=value), updated_at, actor)
                for key, value in values.items()
                if key in ALLOWED_RUNTIME_SETTINGS
            ],
        )


def apply_runtime_settings(*, overrides: dict[str, RuntimeSettingValue]) -> None:
    """Apply runtime setting overrides to in-memory settings object."""
    for key in ALLOWED_RUNTIME_SETTINGS:
        if key not in overrides:
            continue
        value = overrides[key]
        if key in _BOOL_RUNTIME_SETTINGS:
            setattr(settings, key, bool(value))
            continue
        setattr(settings, key, int(value))


def get_runtime_settings_view() -> dict[str, Any]:
    """Return runtime settings from active in-memory configuration."""
    return {
        "sse_max_connections": int(settings.sse_max_connections),
        "alert_engine_enabled": bool(settings.alert_engine_enabled),
        "alert_poll_seconds": int(settings.alert_poll_seconds),
        "restart_action_ttl_seconds": int(settings.restart_action_ttl_seconds),
        "restart_token_rate_limit_window_seconds": int(
            settings.restart_token_rate_limit_window_seconds
        ),
        "restart_token_rate_limit_max_attempts": int(
            settings.restart_token_rate_limit_max_attempts
        ),
        "audit_retention_days": int(settings.audit_retention_days),
        "audit_retention_auto_enabled": bool(settings.audit_retention_auto_enabled),
        "audit_retention_poll_seconds": int(settings.audit_retention_poll_seconds),
    }
