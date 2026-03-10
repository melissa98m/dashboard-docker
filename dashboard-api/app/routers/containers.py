"""Containers API — list, inspect, start, stop, restart."""

import json
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast

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
from app.services.container_logs import snapshot_container_logs

router = APIRouter()
_SSE_SEMAPHORE = threading.BoundedSemaphore(value=settings.sse_max_connections)
_TOKEN_RATE_LIMIT_LOCK = threading.Lock()
_TOKEN_RATE_LIMIT_ATTEMPTS: dict[str, deque[float]] = {}
logger = logging.getLogger(__name__)
_CONTAINER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _get_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


def _safe_container_name(raw_name: str) -> str:
    if raw_name.startswith("/"):
        return raw_name[1:]
    return raw_name


def _validate_container_id(container_id: str) -> str:
    candidate = container_id.strip()
    if not _CONTAINER_ID_PATTERN.fullmatch(candidate):
        raise HTTPException(status_code=422, detail="Invalid container ID format")
    return candidate


def _container_image_ref(container: Any) -> str:
    """Best-effort image reference fallback for missing image metadata."""
    try:
        if container.image.tags:
            return str(container.image.tags[0])
        return str(container.image.short_id)
    except docker.errors.DockerException:
        attrs = getattr(container, "attrs", {}) or {}
        config = attrs.get("Config", {}) if isinstance(attrs, dict) else {}
        configured_image = config.get("Image")
        image_id = attrs.get("Image")
        if isinstance(configured_image, str) and configured_image.strip():
            return str(configured_image)
        if isinstance(image_id, str) and image_id.strip():
            return str(image_id[:24])
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
        if status in {"exited", "dead"} and isinstance(status, str):
            return status
    if isinstance(status, str) and status.strip():
        return cast(str, status)
    return None


def _compute_stats_payload(raw: dict[str, Any]) -> dict[str, float]:
    def _to_float(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed != parsed:  # NaN guard
            return 0.0
        return parsed

    cpu_stats = raw.get("cpu_stats", {})
    precpu = raw.get("precpu_stats", {})
    cpu_usage = cpu_stats.get("cpu_usage", {})
    pre_cpu_usage = precpu.get("cpu_usage", {})

    cpu_total = _to_float(cpu_usage.get("total_usage", 0))
    pre_cpu_total = _to_float(pre_cpu_usage.get("total_usage", 0))
    system_total = _to_float(cpu_stats.get("system_cpu_usage", 0))
    pre_system_total = _to_float(precpu.get("system_cpu_usage", 0))
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
    memory_usage = max(_to_float(memory.get("usage", 0)), 0.0)
    memory_limit = max(_to_float(memory.get("limit", 0)), 0.0)
    memory_percent = (memory_usage / memory_limit * 100.0) if memory_limit > 0 else 0.0
    memory_percent = min(max(memory_percent, 0.0), 100.0)
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


class LinkedImage(BaseModel):
    id: str
    display_name: str
    tags: list[str]


class MountedVolume(BaseModel):
    type: str
    name: str | None
    source: str | None
    destination: str
    read_only: bool | None


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
    linked_images: list[LinkedImage]
    mounted_volumes: list[MountedVolume]


class TokenRestartRequest(BaseModel):
    token: str


def _linked_images(container: Any) -> list[LinkedImage]:
    """Return normalized image metadata for the current container."""
    tags: list[str] = []
    image_id = ""
    display_name = _container_image_ref(container)
    try:
        raw_tags = getattr(container.image, "tags", None) or []
        tags = [str(tag) for tag in raw_tags if isinstance(tag, str) and tag.strip()][:20]
        short_id = getattr(container.image, "short_id", "")
        if isinstance(short_id, str) and short_id.strip():
            image_id = short_id
    except docker.errors.DockerException:
        pass
    if not image_id:
        attrs = getattr(container, "attrs", {}) or {}
        raw_image_id = attrs.get("Image")
        if isinstance(raw_image_id, str) and raw_image_id.strip():
            image_id = raw_image_id[:24]
    if not image_id:
        image_id = display_name
    return [LinkedImage(id=image_id, display_name=display_name, tags=tags)]


def _mounted_volumes(attrs: dict[str, Any]) -> list[MountedVolume]:
    """Extract container mounts without extra Docker API calls."""
    mounts = attrs.get("Mounts")
    if not isinstance(mounts, list):
        return []
    items: list[MountedVolume] = []
    seen: set[tuple[str, str, str]] = set()
    for mount in mounts:
        if not isinstance(mount, dict):
            continue
        mount_type = str(mount.get("Type") or "unknown")
        destination = str(mount.get("Destination") or "").strip()
        if not destination:
            continue
        name = str(mount.get("Name") or "").strip()
        source = str(mount.get("Source") or "").strip()
        unique_key = (mount_type, name or source, destination)
        if unique_key in seen:
            continue
        seen.add(unique_key)
        rw = mount.get("RW")
        items.append(
            MountedVolume(
                type=mount_type,
                name=name or None,
                source=source or None,
                destination=destination,
                read_only=(not rw) if isinstance(rw, bool) else None,
            )
        )
    items.sort(key=lambda item: item.destination)
    return items


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


_BULK_MAX_IDS = 20


def _validate_container_ids(ids: list[str]) -> None:
    if len(ids) > _BULK_MAX_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {_BULK_MAX_IDS} container IDs per bulk request",
        )
    for cid in ids:
        if not isinstance(cid, str) or not cid or len(cid) > 64:
            raise HTTPException(status_code=422, detail="Invalid container ID")
        if not all(c.isalnum() or c in "-_" for c in cid):
            raise HTTPException(status_code=422, detail="Invalid container ID format")


class BulkIdsRequest(BaseModel):
    ids: list[str]


class BulkDeleteRequest(BulkIdsRequest):
    force: bool = False
    volumes: bool = False


@router.get("", response_model=list[ContainerSummary])
def list_containers(
    status: str | None = Query(default=None, description="Filter: 'running' or 'exited'"),
):
    """List all containers (running + stopped). Optionally filter by status."""
    if status is not None and status not in ("running", "exited"):
        raise HTTPException(status_code=422, detail="status must be 'running' or 'exited'")
    try:
        client = _get_client()
        containers = client.containers.list(all=True)
        result = []
        for c in containers:
            attrs = c.attrs
            c_status = attrs.get("State", {}).get("Status", "unknown")
            if status is not None:
                if status == "running" and c_status != "running":
                    continue
                if status == "exited" and c_status == "running":
                    continue
            state = attrs.get("State", {})
            uptime = _uptime_seconds(attrs)
            name = _safe_container_name(c.name)
            image = _container_image_ref(c)
            result.append(
                ContainerSummary(
                    id=c.short_id,
                    name=name,
                    image=image,
                    status=c_status,
                    uptime_seconds=uptime,
                    finished_at=_finished_at(state),
                    last_down_reason=_last_down_reason(state),
                )
            )
        return result
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


class BulkActionResult(BaseModel):
    ok: bool
    succeeded: list[str]
    failed: list[dict[str, str]]


@router.post("/bulk/start", response_model=BulkActionResult)
def bulk_start_containers(
    body: BulkIdsRequest,
    actor: str = Depends(require_write_access),
):
    """Start multiple containers."""
    _validate_container_ids(body.ids)
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    client = _get_client()
    for cid in body.ids:
        try:
            c = client.containers.get(cid)
            c.start()
            succeeded.append(cid)
            _audit_container_action(
                action="container_start",
                container_id=cid,
                actor=actor,
                result="ok",
            )
        except docker.errors.NotFound:
            failed.append({"id": cid, "reason": "not_found"})
            _audit_container_action(
                action="container_start",
                container_id=cid,
                actor=actor,
                result="error",
                reason="not_found",
            )
        except docker.errors.DockerException:
            failed.append({"id": cid, "reason": "docker_error"})
            _audit_container_action(
                action="container_start",
                container_id=cid,
                actor=actor,
                result="error",
                reason="docker_error",
            )
    return BulkActionResult(ok=len(failed) == 0, succeeded=succeeded, failed=failed)


@router.post("/bulk/stop", response_model=BulkActionResult)
def bulk_stop_containers(
    body: BulkIdsRequest,
    actor: str = Depends(require_write_access),
):
    """Stop multiple containers."""
    _validate_container_ids(body.ids)
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    client = _get_client()
    for cid in body.ids:
        try:
            c = client.containers.get(cid)
            c.stop()
            succeeded.append(cid)
            _audit_container_action(
                action="container_stop",
                container_id=cid,
                actor=actor,
                result="ok",
            )
        except docker.errors.NotFound:
            failed.append({"id": cid, "reason": "not_found"})
            _audit_container_action(
                action="container_stop",
                container_id=cid,
                actor=actor,
                result="error",
                reason="not_found",
            )
        except docker.errors.DockerException:
            failed.append({"id": cid, "reason": "docker_error"})
            _audit_container_action(
                action="container_stop",
                container_id=cid,
                actor=actor,
                result="error",
                reason="docker_error",
            )
    return BulkActionResult(ok=len(failed) == 0, succeeded=succeeded, failed=failed)


@router.post("/bulk/delete", response_model=BulkActionResult)
def bulk_delete_containers(
    body: BulkDeleteRequest,
    actor: str = Depends(require_write_access),
):
    """Stop and delete multiple containers."""
    _validate_container_ids(body.ids)
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    client = _get_client()
    for cid in body.ids:
        try:
            c = client.containers.get(cid)
            try:
                c.stop()
            except docker.errors.DockerException:
                pass
            c.remove(v=body.volumes, force=body.force)
            succeeded.append(cid)
            _audit_container_action(
                action="container_delete",
                container_id=cid,
                actor=actor,
                result="ok",
                extra={"force": body.force, "volumes": body.volumes},
            )
        except docker.errors.NotFound:
            failed.append({"id": cid, "reason": "not_found"})
            _audit_container_action(
                action="container_delete",
                container_id=cid,
                actor=actor,
                result="error",
                reason="not_found",
                extra={"force": body.force, "volumes": body.volumes},
            )
        except docker.errors.DockerException:
            failed.append({"id": cid, "reason": "docker_error"})
            _audit_container_action(
                action="container_delete",
                container_id=cid,
                actor=actor,
                result="error",
                reason="docker_error",
                extra={"force": body.force, "volumes": body.volumes},
            )
    return BulkActionResult(ok=len(failed) == 0, succeeded=succeeded, failed=failed)


@router.get("/{container_id}/commands/specs", response_model=list[ContainerCommandSpecItem])
def list_container_command_specs(
    container_id: str,
    _actor: str = Depends(require_read_access),
):
    container_id = _validate_container_id(container_id)
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
    container_id = _validate_container_id(container_id)
    rows = list_discovered_commands(container_id=container_id, limit=limit, offset=offset)
    return [ContainerDiscoveredCommandItem(**row) for row in rows]


@router.get("/{container_id}/commands/executions", response_model=list[ContainerExecutionItem])
def list_container_executions(
    container_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _actor: str = Depends(require_read_access),
):
    container_id = _validate_container_id(container_id)
    rows = list_executions(limit=limit, container_id=container_id)
    return [ContainerExecutionItem(**row) for row in rows]


@router.get("/{container_id}", response_model=ContainerDetail)
def get_container_detail(
    container_id: str,
    tail: int = Query(default=100, ge=1, le=1000),
    _actor: str = Depends(require_read_access),
):
    """Get container details, including last logs and failure hints."""
    container_id = _validate_container_id(container_id)
    try:
        client = _get_client()
        container = client.containers.get(container_id)
        attrs = container.attrs
        state = attrs.get("State", {})
        health = state.get("Health", {}) if isinstance(state.get("Health"), dict) else {}
        status = state.get("Status", "unknown")
        logs = snapshot_container_logs(container, tail=tail)
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
            linked_images=_linked_images(container),
            mounted_volumes=_mounted_volumes(attrs),
        )
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.get("/{container_id}/stats")
def stream_container_stats(
    container_id: str,
    max_events: int = Query(default=0, ge=0, le=500),
    interval_ms: int = Query(default=1000, ge=250, le=60000),
    _actor: str = Depends(require_read_access),
):
    """Stream live container stats as SSE events."""
    container_id = _validate_container_id(container_id)
    try:
        client = _get_client()
        container = client.containers.get(container_id)
        state = container.attrs.get("State", {}) if isinstance(container.attrs, dict) else {}
        status = state.get("Status", "unknown")
        if status != "running":
            raise HTTPException(status_code=409, detail="Container is not running")
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")

    if not _SSE_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Too many live streams")

    def event_stream() -> Iterator[str]:
        sent = 0
        last_sent_at = 0.0
        last_heartbeat_at = time.monotonic()
        heartbeat_interval_sec = 15.0
        try:
            for raw in container.stats(stream=True, decode=True):
                if not isinstance(raw, dict):
                    continue
                now = time.monotonic()
                if (now - last_heartbeat_at) >= heartbeat_interval_sec:
                    yield _sse_event("ping", {"ts": int(time.time())})
                    last_heartbeat_at = now
                if last_sent_at > 0 and ((now - last_sent_at) * 1000.0) < interval_ms:
                    continue
                payload = _compute_stats_payload(raw)
                yield _sse_event("stats", payload)
                last_sent_at = now
                sent += 1
                if max_events > 0 and sent >= max_events:
                    break
        except docker.errors.DockerException:
            yield _sse_event("error", {"message": "Stats stream interrupted"})
        finally:
            _SSE_SEMAPHORE.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{container_id}/logs")
def stream_container_logs(
    container_id: str,
    tail: int = Query(default=100, ge=1, le=1000),
    max_events: int = Query(default=0, ge=0, le=500),
    _actor: str = Depends(require_read_access),
):
    """Stream container logs as SSE events."""
    container_id = _validate_container_id(container_id)
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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{container_id}/start", response_model=ContainerActionResponse)
def start_container(
    container_id: str,
    actor: str = Depends(require_write_access),
):
    """Start a container."""
    container_id = _validate_container_id(container_id)
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
    container_id = _validate_container_id(container_id)
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
    container_id = _validate_container_id(container_id)
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
    container_id = _validate_container_id(container_id)
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
