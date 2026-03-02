"""Containers API — list, inspect, start, stop, restart."""

import json
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import docker
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.db.action_tokens import consume_action_token
from app.db.audit import write_audit_log
from app.db.commands import list_discovered_commands, list_executions, list_specs
from app.security import (
    require_read_access,
    require_write_access,
    verify_restart_token,
)

router = APIRouter()
_SSE_SEMAPHORE = threading.BoundedSemaphore(value=settings.sse_max_connections)
_TOKEN_RATE_LIMIT_LOCK = threading.Lock()
_TOKEN_RATE_LIMIT_ATTEMPTS: dict[str, deque[float]] = {}
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


def _get_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


def _safe_container_name(raw_name: str) -> str:
    if raw_name.startswith("/"):
        return raw_name[1:]
    return raw_name


def _container_image_ref(container: Any) -> str:
    """Best-effort image reference fallback for missing image metadata."""
    try:
        if container.image.tags:
            return container.image.tags[0]
        return container.image.short_id
    except docker.errors.DockerException:
        attrs = getattr(container, "attrs", {}) or {}
        config = attrs.get("Config", {}) if isinstance(attrs, dict) else {}
        configured_image = config.get("Image")
        image_id = attrs.get("Image")
        if isinstance(configured_image, str) and configured_image.strip():
            return configured_image
        if isinstance(image_id, str) and image_id.strip():
            return image_id[:24]
        logger.warning("Container image metadata unavailable for %s", container.short_id)
        return "unknown"


def _uptime_seconds(attrs: dict) -> int | None:
    state = attrs.get("State", {})
    status = state.get("Status", "unknown")
    started = state.get("StartedAt")
    if not started or status != "running":
        return None
    try:
        started_at = datetime.fromisoformat(started.replace("Z", "+00:00"))
        return int((datetime.now(UTC) - started_at).total_seconds())
    except (ValueError, TypeError):
        return None


def _finished_at(state: dict[str, Any]) -> str | None:
    raw_finished = state.get("FinishedAt")
    if not isinstance(raw_finished, str) or not raw_finished.strip():
        return None
    # Docker uses the zero-value timestamp when container never stopped.
    if raw_finished.startswith("0001-01-01T00:00:00"):
        return None
    return raw_finished


def _last_down_reason(state: dict[str, Any]) -> str | None:
    status = state.get("Status", "unknown")
    if status == "running":
        return None

    if state.get("OOMKilled") is True:
        return "oom_killed"

    raw_error = state.get("Error")
    if isinstance(raw_error, str) and raw_error.strip():
        cleaned_error = " ".join(raw_error.split())
        return cleaned_error[:180]

    exit_code = state.get("ExitCode")
    if isinstance(exit_code, int):
        if exit_code != 0:
            return f"exit_code_{exit_code}"
        if status in {"exited", "dead"}:
            return status
    return status if isinstance(status, str) and status.strip() else None


def _snapshot_logs(container: Any, *, tail: int) -> list[str]:
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


def _compute_stats_payload(raw: dict[str, Any]) -> dict[str, float]:
    cpu_stats = raw.get("cpu_stats", {})
    precpu = raw.get("precpu_stats", {})
    cpu_usage = cpu_stats.get("cpu_usage", {})
    pre_cpu_usage = precpu.get("cpu_usage", {})

    cpu_total = float(cpu_usage.get("total_usage", 0))
    pre_cpu_total = float(pre_cpu_usage.get("total_usage", 0))
    system_total = float(cpu_stats.get("system_cpu_usage", 0))
    pre_system_total = float(precpu.get("system_cpu_usage", 0))
    cpu_delta = cpu_total - pre_cpu_total
    system_delta = system_total - pre_system_total
    online_cpus = cpu_stats.get("online_cpus")
    percpu_usage = cpu_usage.get("percpu_usage")
    if isinstance(online_cpus, int) and online_cpus > 0:
        cpu_count = online_cpus
    elif isinstance(percpu_usage, list) and len(percpu_usage) > 0:
        cpu_count = len(percpu_usage)
    else:
        cpu_count = 1

    cpu_percent = 0.0
    if cpu_delta > 0 and system_delta > 0:
        cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0

    memory = raw.get("memory_stats", {})
    memory_usage = float(memory.get("usage", 0))
    memory_limit = float(memory.get("limit", 0))
    memory_percent = (memory_usage / memory_limit * 100.0) if memory_limit > 0 else 0.0
    memory_mb = memory_usage / (1024 * 1024)

    return {
        "cpu_percent": round(cpu_percent, 2),
        "memory_mb": round(memory_mb, 2),
        "memory_percent": round(memory_percent, 2),
    }


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


class ContainerSummary(BaseModel):
    id: str
    name: str
    image: str
    status: str
    uptime_seconds: int | None
    finished_at: str | None
    last_down_reason: str | None


class ContainerActionResponse(BaseModel):
    ok: bool
    message: str


class ContainerDetail(BaseModel):
    id: str
    name: str
    image: str
    status: str
    uptime_seconds: int | None
    finished_at: str | None
    exit_code: int | None
    oom_killed: bool | None
    health_status: str | None
    last_down_reason: str | None
    last_logs: list[str]


class TokenRestartRequest(BaseModel):
    token: str


class ContainerCommandSpecItem(BaseModel):
    id: int
    container_id: str
    service_name: str
    name: str
    argv: list[str]
    cwd: str | None
    env_allowlist: list[str]
    discovered_at: str


class ContainerDiscoveredCommandItem(BaseModel):
    id: int
    container_id: str
    service_name: str
    discovered_at: str
    name: str
    argv: list[str]
    cwd: str | None
    source: str


class ContainerExecutionItem(BaseModel):
    id: int
    command_spec_id: int
    container_id: str
    status: str
    started_at: str
    finished_at: str | None
    exit_code: int | None
    duration_ms: int | None
    triggered_by: str
    stdout_path: str
    stderr_path: str


def _check_token_restart_rate_limit(client_key: str) -> None:
    window = max(settings.restart_token_rate_limit_window_seconds, 1)
    max_attempts = settings.restart_token_rate_limit_max_attempts
    if max_attempts <= 0:
        return
    now = time.monotonic()
    with _TOKEN_RATE_LIMIT_LOCK:
        attempts = _TOKEN_RATE_LIMIT_ATTEMPTS.setdefault(client_key, deque())
        while attempts and (now - attempts[0]) > window:
            attempts.popleft()
        if len(attempts) >= max_attempts:
            raise HTTPException(status_code=429, detail="Too many token restart attempts")
        attempts.append(now)


def _audit_container_action(
    *,
    action: str,
    container_id: str | None,
    actor: str,
    result: str,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    details: dict[str, Any] = {"result": result}
    if reason:
        details["reason"] = reason
    if extra:
        details.update(extra)
    write_audit_log(
        action=action,
        resource_type="container",
        resource_id=container_id,
        triggered_by=actor,
        details={key: str(value) for key, value in details.items()},
    )


@router.get("", response_model=list[ContainerSummary])
def list_containers():
    """List all containers (running + stopped)."""
    try:
        client = _get_client()
        containers = client.containers.list(all=True)
        result = []
        for c in containers:
            attrs = c.attrs
            status = attrs.get("State", {}).get("Status", "unknown")
            state = attrs.get("State", {})
            uptime = _uptime_seconds(attrs)
            name = _safe_container_name(c.name)
            image = _container_image_ref(c)
            result.append(
                ContainerSummary(
                    id=c.short_id,
                    name=name,
                    image=image,
                    status=status,
                    uptime_seconds=uptime,
                    finished_at=_finished_at(state),
                    last_down_reason=_last_down_reason(state),
                )
            )
        return result
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.get("/{container_id}/commands/specs", response_model=list[ContainerCommandSpecItem])
def list_container_command_specs(
    container_id: str,
    _actor: str = Depends(require_read_access),
):
    return [ContainerCommandSpecItem(**row) for row in list_specs(container_id=container_id)]


@router.get(
    "/{container_id}/commands/discovered",
    response_model=list[ContainerDiscoveredCommandItem],
)
def list_container_discovered_commands(
    container_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _actor: str = Depends(require_read_access),
):
    rows = list_discovered_commands(container_id=container_id, limit=limit, offset=offset)
    return [ContainerDiscoveredCommandItem(**row) for row in rows]


@router.get("/{container_id}/commands/executions", response_model=list[ContainerExecutionItem])
def list_container_executions(
    container_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _actor: str = Depends(require_read_access),
):
    rows = list_executions(limit=limit, container_id=container_id)
    return [ContainerExecutionItem(**row) for row in rows]


@router.get("/{container_id}", response_model=ContainerDetail)
def get_container_detail(
    container_id: str,
    tail: int = Query(default=100, ge=1, le=1000),
    _actor: str = Depends(require_read_access),
):
    """Get container details, including last logs and failure hints."""
    try:
        client = _get_client()
        container = client.containers.get(container_id)
        attrs = container.attrs
        state = attrs.get("State", {})
        health = state.get("Health", {}) if isinstance(state.get("Health"), dict) else {}
        status = state.get("Status", "unknown")
        logs = _snapshot_logs(container, tail=tail)
        image = _container_image_ref(container)
        return ContainerDetail(
            id=container.short_id,
            name=_safe_container_name(container.name),
            image=image,
            status=status,
            uptime_seconds=_uptime_seconds(attrs),
            finished_at=_finished_at(state),
            exit_code=state.get("ExitCode"),
            oom_killed=state.get("OOMKilled"),
            health_status=health.get("Status"),
            last_down_reason=_last_down_reason(state),
            last_logs=logs,
        )
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.get("/{container_id}/stats")
def stream_container_stats(
    container_id: str,
    max_events: int = Query(default=0, ge=0, le=500),
    _actor: str = Depends(require_read_access),
):
    """Stream live container stats as SSE events."""
    try:
        client = _get_client()
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")

    if not _SSE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Too many live streams")

    def event_stream() -> Iterator[str]:
        sent = 0
        try:
            for raw in container.stats(stream=True, decode=True):
                if not isinstance(raw, dict):
                    continue
                payload = _compute_stats_payload(raw)
                yield _sse_event("stats", payload)
                sent += 1
                if max_events > 0 and sent >= max_events:
                    break
        except docker.errors.DockerException:
            yield _sse_event("error", {"message": "Stats stream interrupted"})
        finally:
            _SSE_SEMAPHORE.release()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{container_id}/logs")
def stream_container_logs(
    container_id: str,
    tail: int = Query(default=100, ge=1, le=1000),
    max_events: int = Query(default=0, ge=0, le=500),
    _actor: str = Depends(require_read_access),
):
    """Stream container logs as SSE events."""
    try:
        client = _get_client()
        container = client.containers.get(container_id)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")

    if not _SSE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Too many live streams")

    def event_stream() -> Iterator[str]:
        sent = 0
        try:
            for line in container.logs(stream=True, follow=True, tail=tail):
                decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                if decoded:
                    yield _sse_event("log", {"line": decoded})
                    sent += 1
                    if max_events > 0 and sent >= max_events:
                        break
        except docker.errors.DockerException:
            yield _sse_event("error", {"message": "Logs stream interrupted"})
        finally:
            _SSE_SEMAPHORE.release()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{container_id}/start", response_model=ContainerActionResponse)
def start_container(
    container_id: str,
    actor: str = Depends(require_write_access),
):
    """Start a container."""
    try:
        client = _get_client()
        c = client.containers.get(container_id)
        c.start()
        _audit_container_action(
            action="container_start",
            container_id=container_id,
            actor=actor,
            result="ok",
        )
        return ContainerActionResponse(ok=True, message="Container started")
    except docker.errors.NotFound:
        _audit_container_action(
            action="container_start",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        _audit_container_action(
            action="container_start",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="docker_error",
        )
        raise HTTPException(status_code=400, detail="Unable to start container")


@router.post("/{container_id}/stop", response_model=ContainerActionResponse)
def stop_container(
    container_id: str,
    actor: str = Depends(require_write_access),
):
    """Stop a container."""
    try:
        client = _get_client()
        c = client.containers.get(container_id)
        c.stop()
        _audit_container_action(
            action="container_stop",
            container_id=container_id,
            actor=actor,
            result="ok",
        )
        return ContainerActionResponse(ok=True, message="Container stopped")
    except docker.errors.NotFound:
        _audit_container_action(
            action="container_stop",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        _audit_container_action(
            action="container_stop",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="docker_error",
        )
        raise HTTPException(status_code=400, detail="Unable to stop container")


@router.post("/{container_id}/restart", response_model=ContainerActionResponse)
def restart_container(
    container_id: str,
    actor: str = Depends(require_write_access),
):
    """Restart a container."""
    try:
        client = _get_client()
        c = client.containers.get(container_id)
        c.restart()
        _audit_container_action(
            action="container_restart",
            container_id=container_id,
            actor=actor,
            result="ok",
        )
        return ContainerActionResponse(ok=True, message="Container restarted")
    except docker.errors.NotFound:
        _audit_container_action(
            action="container_restart",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        _audit_container_action(
            action="container_restart",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="docker_error",
        )
        raise HTTPException(status_code=400, detail="Unable to restart container")


@router.delete("/{container_id}", response_model=ContainerActionResponse)
def delete_container(
    container_id: str,
    force: bool = Query(default=False),
    volumes: bool = Query(default=False),
    actor: str = Depends(require_write_access),
):
    """Delete a container."""
    try:
        client = _get_client()
        c = client.containers.get(container_id)
        c.remove(v=volumes, force=force)
        _audit_container_action(
            action="container_delete",
            container_id=container_id,
            actor=actor,
            result="ok",
            extra={"force": force, "volumes": volumes},
        )
        return ContainerActionResponse(ok=True, message="Container deleted")
    except docker.errors.NotFound:
        _audit_container_action(
            action="container_delete",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="not_found",
            extra={"force": force, "volumes": volumes},
        )
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        _audit_container_action(
            action="container_delete",
            container_id=container_id,
            actor=actor,
            result="error",
            reason="docker_error",
            extra={"force": force, "volumes": volumes},
        )
        raise HTTPException(status_code=400, detail="Unable to delete container")


def _restart_by_signed_token(token: str) -> ContainerActionResponse:
    try:
        container_id = verify_restart_token(token)
    except ValueError as exc:
        _audit_container_action(
            action="container_restart_by_token",
            container_id=None,
            actor="token-action",
            result="error",
            reason="invalid_token",
        )
        raise HTTPException(status_code=401, detail="Invalid restart token") from exc

    if not consume_action_token(token=token, container_id=container_id):
        _audit_container_action(
            action="container_restart_by_token",
            container_id=container_id,
            actor="token-action",
            result="error",
            reason="token_replay",
        )
        raise HTTPException(status_code=409, detail="Restart token already used")

    try:
        client = _get_client()
        container = client.containers.get(container_id)
        container.restart()
        _audit_container_action(
            action="container_restart_by_token",
            container_id=container_id,
            actor="token-action",
            result="ok",
        )
        return ContainerActionResponse(ok=True, message="Container restarted")
    except docker.errors.NotFound:
        _audit_container_action(
            action="container_restart_by_token",
            container_id=container_id,
            actor="token-action",
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        _audit_container_action(
            action="container_restart_by_token",
            container_id=container_id,
            actor="token-action",
            result="error",
            reason="docker_error",
        )
        raise HTTPException(status_code=400, detail="Unable to restart container")


@router.post("/restart-by-token", response_model=ContainerActionResponse)
def restart_by_token(
    request: Request,
    payload: TokenRestartRequest | None = None,
    token: str | None = Query(default=None, min_length=10),
):
    """Restart container using a short-lived signed token."""
    client_ip = request.client.host if request.client is not None else "unknown"
    _check_token_restart_rate_limit(client_ip)
    final_token = payload.token if payload is not None else token
    if not final_token:
        raise HTTPException(status_code=422, detail="Token is required")
    return _restart_by_signed_token(final_token)
