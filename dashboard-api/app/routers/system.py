"""System and security status endpoints."""

import sqlite3
from typing import Any, cast

import docker
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import SETTINGS_LOADED_AT, settings
from app.db.audit import write_audit_log
from app.db.init import get_db_path
from app.db.runtime_settings import (
    RuntimeSettingKey,
    RuntimeSettingValue,
    apply_runtime_settings,
    get_runtime_settings_view,
    upsert_runtime_settings,
)
from app.routers.containers import get_log_redaction_preview
from app.security import require_read_access, require_write_access

router = APIRouter()


class SecurityStatusResponse(BaseModel):
    auth_enabled: bool
    write_auth_configured: bool
    read_auth_enforced: bool
    read_auth_configured: bool
    sse_max_connections: int
    alert_engine_enabled: bool
    alert_engine_running: bool
    alert_engine_last_cycle_at: str | None
    alert_engine_last_success_at: str | None
    alert_engine_consecutive_errors: int
    alert_engine_last_error_reason: str | None
    alert_engine_last_error_at: str | None
    alert_poll_seconds: int
    ntfy_configured: bool
    restart_action_enabled: bool
    restart_action_ttl_seconds: int
    restart_token_rate_limit_window_seconds: int
    restart_token_rate_limit_max_attempts: int
    auth_session_retention_auto_enabled: bool
    auth_session_retention_running: bool
    auth_session_retention_poll_seconds: int
    audit_retention_days: int
    audit_retention_auto_enabled: bool
    audit_retention_running: bool
    audit_retention_last_cycle_at: str | None
    audit_retention_last_success_at: str | None
    audit_retention_consecutive_errors: int
    audit_retention_last_error_reason: str | None
    audit_retention_last_error_at: str | None
    audit_retention_poll_seconds: int
    log_snapshot_redaction_enabled: bool
    log_snapshot_redaction_default_rules: list[str]
    log_snapshot_redaction_extra_rules_count: int
    runtime_config_loaded_at: str


class VersionResponse(BaseModel):
    api_version: str
    docker_host: str


class DependencyHealthItem(BaseModel):
    ok: bool
    detail: str


class DependenciesHealthResponse(BaseModel):
    ok: bool
    checks: dict[str, DependencyHealthItem]


class RuntimeSettingsResponse(BaseModel):
    sse_max_connections: int
    alert_engine_enabled: bool
    alert_poll_seconds: int
    restart_action_ttl_seconds: int
    restart_token_rate_limit_window_seconds: int
    restart_token_rate_limit_max_attempts: int
    audit_retention_days: int
    audit_retention_auto_enabled: bool
    audit_retention_poll_seconds: int


class RuntimeSettingsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sse_max_connections: int | None = Field(default=None, ge=1, le=500)
    alert_engine_enabled: bool | None = Field(default=None)
    alert_poll_seconds: int | None = Field(default=None, ge=1, le=300)
    restart_action_ttl_seconds: int | None = Field(default=None, ge=30, le=3600)
    restart_token_rate_limit_window_seconds: int | None = Field(default=None, ge=10, le=3600)
    restart_token_rate_limit_max_attempts: int | None = Field(default=None, ge=1, le=1000)
    audit_retention_days: int | None = Field(default=None, ge=1, le=3650)
    audit_retention_auto_enabled: bool | None = Field(default=None)
    audit_retention_poll_seconds: int | None = Field(default=None, ge=10, le=604800)


def _service_running(service: Any) -> bool:
    checker = getattr(service, "is_running", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001
            return False
    thread = getattr(service, "_thread", None)
    return bool(thread and hasattr(thread, "is_alive") and thread.is_alive())


def _service_last_cycle_at(service: Any) -> str | None:
    getter = getattr(service, "get_last_cycle_at", None)
    if callable(getter):
        try:
            value = getter()
            return str(value) if isinstance(value, str) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _service_last_success_at(service: Any) -> str | None:
    getter = getattr(service, "get_last_success_at", None)
    if callable(getter):
        try:
            value = getter()
            return str(value) if isinstance(value, str) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _service_consecutive_errors(service: Any) -> int:
    getter = getattr(service, "get_consecutive_errors", None)
    if callable(getter):
        try:
            value = getter()
            if isinstance(value, int):
                return max(0, value)
        except Exception:  # noqa: BLE001
            return 0
    return 0


def _service_last_error_reason(service: Any) -> str | None:
    getter = getattr(service, "get_last_error_reason", None)
    if callable(getter):
        try:
            value = getter()
            if isinstance(value, str) and value.strip():
                return value.strip()[:80]
        except Exception:  # noqa: BLE001
            return None
    return None


def _service_last_error_at(service: Any) -> str | None:
    getter = getattr(service, "get_last_error_at", None)
    if callable(getter):
        try:
            value = getter()
            return str(value) if isinstance(value, str) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _sync_runtime_services(request: Request) -> None:
    alert_engine = getattr(request.app.state, "alert_engine", None)
    if alert_engine is not None:
        if settings.alert_engine_enabled:
            alert_engine.start()
        else:
            alert_engine.stop()
    audit_retention_service = getattr(request.app.state, "audit_retention_service", None)
    if audit_retention_service is not None:
        if settings.audit_retention_auto_enabled:
            audit_retention_service.start()
        else:
            audit_retention_service.stop()


def _check_docker_dependency() -> tuple[bool, str]:
    try:
        client = docker.DockerClient(base_url=settings.docker_host)
        client.ping()
        return True, "reachable"
    except docker.errors.DockerException:
        return False, "unreachable"


def _check_sqlite_dependency() -> tuple[bool, str]:
    db_path = get_db_path()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS __health_tmp(id INTEGER)")
            conn.execute("INSERT INTO __health_tmp(id) VALUES (1)")
            conn.execute("DELETE FROM __health_tmp")
        return True, "writable"
    except sqlite3.Error:
        return False, "not_writable"


@router.get("/version", response_model=VersionResponse)
def get_version(_actor: str = Depends(require_read_access)):
    """Expose API version and runtime Docker host."""
    return VersionResponse(
        api_version="0.1.0",
        docker_host=settings.docker_host,
    )


@router.get("/security-status", response_model=SecurityStatusResponse)
def get_security_status(request: Request, _actor: str = Depends(require_read_access)):
    """Expose non-sensitive security posture for operations."""
    redaction_preview = get_log_redaction_preview()
    alert_engine = getattr(request.app.state, "alert_engine", None)
    audit_retention_service = getattr(request.app.state, "audit_retention_service", None)
    auth_session_retention_service = getattr(
        request.app.state, "auth_session_retention_service", None
    )
    return SecurityStatusResponse(
        auth_enabled=settings.auth_enabled,
        write_auth_configured=settings.auth_enabled,
        read_auth_enforced=settings.auth_enabled,
        read_auth_configured=settings.auth_enabled,
        sse_max_connections=settings.sse_max_connections,
        alert_engine_enabled=settings.alert_engine_enabled,
        alert_engine_running=_service_running(alert_engine),
        alert_engine_last_cycle_at=_service_last_cycle_at(alert_engine),
        alert_engine_last_success_at=_service_last_success_at(alert_engine),
        alert_engine_consecutive_errors=_service_consecutive_errors(alert_engine),
        alert_engine_last_error_reason=_service_last_error_reason(alert_engine),
        alert_engine_last_error_at=_service_last_error_at(alert_engine),
        alert_poll_seconds=settings.alert_poll_seconds,
        ntfy_configured=bool(settings.ntfy_base_url and settings.ntfy_topic),
        restart_action_enabled=bool(settings.api_secret_key and settings.public_api_url),
        restart_action_ttl_seconds=settings.restart_action_ttl_seconds,
        restart_token_rate_limit_window_seconds=settings.restart_token_rate_limit_window_seconds,
        restart_token_rate_limit_max_attempts=settings.restart_token_rate_limit_max_attempts,
        auth_session_retention_auto_enabled=settings.auth_session_retention_auto_enabled,
        auth_session_retention_running=_service_running(auth_session_retention_service),
        auth_session_retention_poll_seconds=settings.auth_session_retention_poll_seconds,
        audit_retention_days=settings.audit_retention_days,
        audit_retention_auto_enabled=settings.audit_retention_auto_enabled,
        audit_retention_running=_service_running(audit_retention_service),
        audit_retention_last_cycle_at=_service_last_cycle_at(audit_retention_service),
        audit_retention_last_success_at=_service_last_success_at(audit_retention_service),
        audit_retention_consecutive_errors=_service_consecutive_errors(audit_retention_service),
        audit_retention_last_error_reason=_service_last_error_reason(audit_retention_service),
        audit_retention_last_error_at=_service_last_error_at(audit_retention_service),
        audit_retention_poll_seconds=settings.audit_retention_poll_seconds,
        log_snapshot_redaction_enabled=redaction_preview["enabled"],
        log_snapshot_redaction_default_rules=redaction_preview["default_rules"],
        log_snapshot_redaction_extra_rules_count=redaction_preview["extra_rules_count"],
        runtime_config_loaded_at=SETTINGS_LOADED_AT,
    )


@router.get("/health/deps", response_model=DependenciesHealthResponse)
def get_dependencies_health(_actor: str = Depends(require_read_access)):
    """Check critical dependencies for operational monitoring."""
    docker_ok, docker_detail = _check_docker_dependency()
    sqlite_ok, sqlite_detail = _check_sqlite_dependency()
    checks: dict[str, Any] = {
        "docker": DependencyHealthItem(ok=docker_ok, detail=docker_detail),
        "sqlite": DependencyHealthItem(ok=sqlite_ok, detail=sqlite_detail),
    }
    return DependenciesHealthResponse(ok=docker_ok and sqlite_ok, checks=checks)


@router.get("/runtime-settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings(_actor: str = Depends(require_read_access)):
    """Return runtime-editable settings from active config."""
    return RuntimeSettingsResponse(**get_runtime_settings_view())


@router.patch("/runtime-settings", response_model=RuntimeSettingsResponse)
def patch_runtime_settings(
    request: Request,
    payload: RuntimeSettingsPatchRequest,
    actor: str = Depends(require_write_access),
):
    """Update allowed runtime settings and persist overrides."""
    updates = payload.model_dump(exclude_unset=True)
    typed_updates: dict[RuntimeSettingKey, RuntimeSettingValue] = {}
    for key, value in updates.items():
        if value is None:
            continue
        runtime_key = cast(RuntimeSettingKey, key)
        if runtime_key in {"alert_engine_enabled", "audit_retention_auto_enabled"}:
            typed_updates[runtime_key] = bool(value)
            continue
        typed_updates[runtime_key] = int(value)
    if typed_updates:
        previous_values = {key: str(getattr(settings, key)) for key in typed_updates}
        upsert_runtime_settings(values=typed_updates, actor=actor)
        apply_runtime_settings(overrides=cast(dict[str, int | bool], typed_updates))
        _sync_runtime_services(request)
        new_values = {key: str(getattr(settings, key)) for key in typed_updates}
        write_audit_log(
            action="runtime_settings_update",
            resource_type="system_settings",
            resource_id=None,
            triggered_by=actor,
            details={
                "fields": ",".join(sorted(typed_updates.keys())),
                "previous_values": ",".join(
                    f"{key}:{value}" for key, value in sorted(previous_values.items())
                ),
                "new_values": ",".join(
                    f"{key}:{value}" for key, value in sorted(new_values.items())
                ),
            },
        )
    return RuntimeSettingsResponse(**get_runtime_settings_view())
