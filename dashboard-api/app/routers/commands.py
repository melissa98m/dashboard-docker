"""Command center API (allowlisted specs + execution history)."""

import json
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import docker
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.db.audit import write_audit_log
from app.db.commands import (
    complete_execution,
    count_discovered_commands,
    create_execution,
    create_spec,
    get_discovered_command,
    get_execution,
    get_spec,
    get_spec_by_container_and_name,
    latest_discovered_at,
    list_discovered_commands,
    list_executions,
    list_specs,
    replace_discovered_commands,
)
from app.db.stream_tokens import consume_stream_token
from app.security import (
    create_execution_stream_token,
    require_read_access,
    require_write_access,
    verify_execution_stream_token,
)
from app.services.command_discovery import discover_commands

router = APIRouter()
_DISALLOWED_SHELLS = {"sh", "bash", "zsh", "ash", "dash", "ksh"}
_ALLOWED_BINARIES = {
    "npm",
    "pnpm",
    "yarn",
    "make",
    "poetry",
    "python",
    "python3",
    "pytest",
    "django-admin",
    "php",
    "composer",
}


def _docker_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


def _audit_command_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor: str,
    result: str,
    reason: str | None = None,
    extra: dict[str, str] | None = None,
) -> None:
    details: dict[str, str] = {"result": result}
    if reason:
        details["reason"] = reason
    if extra:
        details.update(extra)
    write_audit_log(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        triggered_by=actor,
        details=details,
    )


class CommandSpecCreate(BaseModel):
    container_id: str = Field(min_length=1, max_length=128)
    service_name: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    argv: list[str] = Field(min_length=1, max_length=30)
    cwd: str | None = Field(default=None, max_length=255)
    env_allowlist: list[str] = Field(default_factory=list, max_length=50)


class CommandSpecResponse(BaseModel):
    id: int
    container_id: str
    service_name: str
    name: str
    argv: list[str]
    cwd: str | None
    env_allowlist: list[str]
    discovered_at: str


class ExecuteRequest(BaseModel):
    spec_id: int
    container_id: str | None = Field(default=None, min_length=1, max_length=128)


class ExecuteResponse(BaseModel):
    execution_id: int
    status: str
    exit_code: int | None = None


class ExecutionItem(BaseModel):
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


class ExecutionDetail(ExecutionItem):
    stdout_tail: str
    stderr_tail: str


class StreamTokenResponse(BaseModel):
    execution_id: int
    token: str
    expires_in_seconds: int


class DiscoverRequest(BaseModel):
    container_id: str = Field(min_length=1, max_length=128)
    force: bool = False


class DiscoverResponse(BaseModel):
    container_id: str
    service_name: str
    discovered_count: int
    cached: bool = False
    cache_age_seconds: int | None = None


class DiscoveredCommandItem(BaseModel):
    id: int
    container_id: str
    service_name: str
    discovered_at: str
    name: str
    argv: list[str]
    cwd: str | None
    source: str


class AllowlistResponse(BaseModel):
    discovered_id: int
    spec_id: int
    already_exists: bool = False


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _safe_env_from_allowlist(allowlist: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in allowlist:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


def _read_tail(path: str, max_chars: int = 10000) -> str:
    if not Path(path).exists():
        return ""
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    if len(content) <= max_chars:
        return content
    return content[-max_chars:]


def _new_execution_log_paths(spec_id: int) -> tuple[str, str]:
    log_dir = Path("/data/executions")
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    stdout_path = str(log_dir / f"exec-{spec_id}-{stamp}-stdout.log")
    stderr_path = str(log_dir / f"exec-{spec_id}-{stamp}-stderr.log")
    return stdout_path, stderr_path


def _append_log(path: str, chunk: bytes) -> None:
    if not chunk:
        return
    text = chunk.decode("utf-8", errors="replace")
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(text)


def _is_allowed_argv(argv: list[str]) -> bool:
    if not argv:
        return False
    normalized = [arg.strip() for arg in argv]
    if any(not token or len(token) > 255 for token in normalized):
        return False
    if any(token == "-c" for token in normalized):
        return False
    if normalized[0] in _DISALLOWED_SHELLS:
        return False
    if normalized[0] not in _ALLOWED_BINARIES:
        return False
    return True


def _execute_worker(
    *,
    execution_id: int,
    spec: dict,
    stdout_path: str,
    stderr_path: str,
    actor: str,
) -> None:
    exit_code = 1
    started_monotonic = time.monotonic()
    # Create files immediately so live stream can attach early.
    Path(stdout_path).write_text("", encoding="utf-8")
    Path(stderr_path).write_text("", encoding="utf-8")
    try:
        client = _docker_client()
        container = client.containers.get(str(spec["container_id"]))
        env = _safe_env_from_allowlist(list(spec.get("env_allowlist", [])))
        api = getattr(client, "api", None)
        if api is not None and hasattr(api, "exec_create"):
            exec_created = api.exec_create(
                container.id,
                cmd=list(spec["argv"]),
                workdir=spec.get("cwd"),
                environment=env,
            )
            exec_id = (
                str(exec_created.get("Id")) if isinstance(exec_created, dict) else str(exec_created)
            )
            stream = api.exec_start(exec_id, stream=True, demux=True)
            for chunk in stream:
                if isinstance(chunk, tuple):
                    stdout_chunk, stderr_chunk = chunk
                else:
                    stdout_chunk, stderr_chunk = chunk, None
                if stdout_chunk:
                    _append_log(stdout_path, stdout_chunk)
                if stderr_chunk:
                    _append_log(stderr_path, stderr_chunk)
            inspected = api.exec_inspect(exec_id)
            raw_exit = inspected.get("ExitCode") if isinstance(inspected, dict) else None
            exit_code = int(raw_exit if raw_exit is not None else 1)
        else:
            # Fallback for test doubles or older client APIs.
            result = container.exec_run(
                cmd=list(spec["argv"]),
                workdir=spec.get("cwd"),
                environment=env,
                demux=True,
            )
            stdout_bytes, stderr_bytes = result.output if result.output else (b"", b"")
            if stdout_bytes:
                _append_log(stdout_path, stdout_bytes)
            if stderr_bytes:
                _append_log(stderr_path, stderr_bytes)
            exit_code = int(result.exit_code if result.exit_code is not None else 1)
    except docker.errors.DockerException:
        _append_log(stderr_path, b"Command execution failed\n")
        exit_code = 1
    finally:
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        complete_execution(execution_id=execution_id, exit_code=exit_code, duration_ms=duration_ms)
        write_audit_log(
            action="command_execute_finished",
            resource_type="execution",
            resource_id=str(execution_id),
            triggered_by=actor,
            details={
                "spec_id": str(spec["id"]),
                "container_id": str(spec["container_id"]),
                "exit_code": str(exit_code),
                "duration_ms": str(duration_ms),
            },
        )


def _spawn_execution(
    *,
    execution_id: int,
    spec: dict,
    stdout_path: str,
    stderr_path: str,
    actor: str,
) -> None:
    thread = threading.Thread(
        target=_execute_worker,
        kwargs={
            "execution_id": execution_id,
            "spec": spec,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "actor": actor,
        },
        daemon=True,
    )
    thread.start()


@router.get("/specs", response_model=list[CommandSpecResponse])
def get_specs(_actor: str = Depends(require_read_access)):
    return [CommandSpecResponse(**row) for row in list_specs()]


@router.post("/specs", response_model=CommandSpecResponse)
def post_spec(payload: CommandSpecCreate, actor: str = Depends(require_write_access)):
    if not _is_allowed_argv(payload.argv):
        _audit_command_event(
            action="command_spec_create",
            resource_type="command_spec",
            resource_id=None,
            actor=actor,
            result="error",
            reason="invalid_argv",
            extra={"service_name": payload.service_name},
        )
        raise HTTPException(status_code=422, detail="Invalid argv entry")
    try:
        created = create_spec(
            container_id=payload.container_id,
            service_name=payload.service_name,
            name=payload.name,
            argv=payload.argv,
            cwd=payload.cwd,
            env_allowlist=payload.env_allowlist,
        )
    except sqlite3.IntegrityError:
        _audit_command_event(
            action="command_spec_create",
            resource_type="command_spec",
            resource_id=None,
            actor=actor,
            result="error",
            reason="already_exists",
            extra={"service_name": payload.service_name},
        )
        raise HTTPException(status_code=409, detail="Spec already exists")
    _audit_command_event(
        action="command_spec_create",
        resource_type="command_spec",
        resource_id=str(created["id"]),
        actor=actor,
        result="ok",
        extra={"service_name": payload.service_name},
    )
    return CommandSpecResponse(**created)


@router.post("/execute", response_model=ExecuteResponse)
def execute_command(payload: ExecuteRequest, actor: str = Depends(require_write_access)):
    spec = get_spec(payload.spec_id)
    if spec is None:
        _audit_command_event(
            action="command_execute_started",
            resource_type="execution",
            resource_id=None,
            actor=actor,
            result="error",
            reason="spec_not_found",
            extra={"spec_id": str(payload.spec_id)},
        )
        raise HTTPException(status_code=404, detail="Command spec not found")
    if payload.container_id is not None and payload.container_id != str(spec["container_id"]):
        _audit_command_event(
            action="command_execute_started",
            resource_type="execution",
            resource_id=None,
            actor=actor,
            result="error",
            reason="spec_container_mismatch",
            extra={
                "spec_id": str(spec["id"]),
                "expected_container_id": str(spec["container_id"]),
                "requested_container_id": payload.container_id,
            },
        )
        raise HTTPException(status_code=409, detail="Spec/container mismatch")

    stdout_path, stderr_path = _new_execution_log_paths(payload.spec_id)

    execution_id = create_execution(
        command_spec_id=int(spec["id"]),
        container_id=str(spec["container_id"]),
        triggered_by=actor,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    _audit_command_event(
        action="command_execute_started",
        resource_type="execution",
        resource_id=str(execution_id),
        actor=actor,
        result="ok",
        extra={"spec_id": str(spec["id"]), "container_id": str(spec["container_id"])},
    )

    _spawn_execution(
        execution_id=execution_id,
        spec=spec,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        actor=actor,
    )
    return ExecuteResponse(execution_id=execution_id, status="started")


@router.post("/discover", response_model=DiscoverResponse)
def discover_container_commands(
    payload: DiscoverRequest, actor: str = Depends(require_write_access)
):
    latest = latest_discovered_at(payload.container_id)
    if not payload.force and latest is not None:
        try:
            discovered_at = datetime.fromisoformat(latest)
            now = datetime.now(UTC)
            age_seconds = int(max((now - discovered_at).total_seconds(), 0))
            ttl_seconds = max(settings.command_discovery_cache_ttl_seconds, 0)
            if age_seconds <= ttl_seconds:
                cached_count = count_discovered_commands(payload.container_id)
                _audit_command_event(
                    action="command_discover_cached",
                    resource_type="container",
                    resource_id=payload.container_id,
                    actor=actor,
                    result="ok",
                    extra={
                        "discovered_count": str(cached_count),
                        "cache_age_seconds": str(age_seconds),
                    },
                )
                return DiscoverResponse(
                    container_id=payload.container_id,
                    service_name="cached",
                    discovered_count=cached_count,
                    cached=True,
                    cache_age_seconds=age_seconds,
                )
        except ValueError:
            pass

    try:
        client = _docker_client()
        container = client.containers.get(payload.container_id)
        service_name, commands = discover_commands(container)
    except docker.errors.NotFound:
        _audit_command_event(
            action="command_discover",
            resource_type="container",
            resource_id=payload.container_id,
            actor=actor,
            result="error",
            reason="container_not_found",
        )
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        _audit_command_event(
            action="command_discover",
            resource_type="container",
            resource_id=payload.container_id,
            actor=actor,
            result="error",
            reason="docker_unavailable",
        )
        raise HTTPException(status_code=503, detail="Docker engine unavailable")

    discovered_count = replace_discovered_commands(
        container_id=payload.container_id,
        service_name=service_name,
        commands=commands,
    )
    _audit_command_event(
        action="command_discover",
        resource_type="container",
        resource_id=payload.container_id,
        actor=actor,
        result="ok",
        extra={"discovered_count": str(discovered_count)},
    )
    return DiscoverResponse(
        container_id=payload.container_id,
        service_name=service_name,
        discovered_count=discovered_count,
        cached=False,
        cache_age_seconds=0,
    )


@router.get("/discovered", response_model=list[DiscoveredCommandItem])
def get_discovered(
    container_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _actor: str = Depends(require_read_access),
):
    rows = list_discovered_commands(container_id=container_id, limit=limit, offset=offset)
    return [DiscoveredCommandItem(**row) for row in rows]


@router.post("/discovered/{discovered_id}/allowlist", response_model=AllowlistResponse)
def allowlist_discovered(discovered_id: int, actor: str = Depends(require_write_access)):
    discovered = get_discovered_command(discovered_id)
    if discovered is None:
        _audit_command_event(
            action="command_discovered_allowlist",
            resource_type="discovered_command",
            resource_id=str(discovered_id),
            actor=actor,
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Discovered command not found")
    argv = list(discovered.get("argv", []))
    if not _is_allowed_argv(argv):
        _audit_command_event(
            action="command_discovered_allowlist",
            resource_type="discovered_command",
            resource_id=str(discovered_id),
            actor=actor,
            result="error",
            reason="invalid_argv",
        )
        raise HTTPException(status_code=422, detail="Discovered command has invalid argv")
    try:
        spec = create_spec(
            container_id=str(discovered["container_id"]),
            service_name=str(discovered["service_name"]),
            name=str(discovered["name"]),
            argv=argv,
            cwd=discovered.get("cwd"),
            env_allowlist=[],
        )
        already_exists = False
    except sqlite3.IntegrityError:
        existing = get_spec_by_container_and_name(
            container_id=str(discovered["container_id"]),
            name=str(discovered["name"]),
        )
        if existing is None:
            _audit_command_event(
                action="command_discovered_allowlist",
                resource_type="discovered_command",
                resource_id=str(discovered_id),
                actor=actor,
                result="error",
                reason="already_exists_but_missing_spec",
            )
            raise HTTPException(status_code=409, detail="Spec already exists")
        spec = existing
        already_exists = True
    _audit_command_event(
        action="command_discovered_allowlist",
        resource_type="discovered_command",
        resource_id=str(discovered_id),
        actor=actor,
        result="ok",
        extra={"spec_id": str(spec["id"]), "source": str(discovered.get("source", "unknown"))},
    )
    return AllowlistResponse(
        discovered_id=discovered_id,
        spec_id=int(spec["id"]),
        already_exists=already_exists,
    )


@router.get("/executions", response_model=list[ExecutionItem])
def get_executions(
    limit: int = Query(default=100, ge=1, le=500),
    _actor: str = Depends(require_read_access),
):
    return [ExecutionItem(**row) for row in list_executions(limit=limit)]


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
def get_execution_detail(execution_id: int, _actor: str = Depends(require_read_access)):
    row = get_execution(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return ExecutionDetail(
        **row,
        stdout_tail=_read_tail(row["stdout_path"]),
        stderr_tail=_read_tail(row["stderr_path"]),
    )


@router.get("/executions/{execution_id}/stream-token", response_model=StreamTokenResponse)
def get_execution_stream_token(
    execution_id: int,
    _actor: str = Depends(require_read_access),
):
    row = get_execution(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    try:
        token = create_execution_stream_token(execution_id=execution_id)
    except ValueError:
        raise HTTPException(status_code=503, detail="Stream token misconfigured")
    return StreamTokenResponse(
        execution_id=execution_id,
        token=token,
        expires_in_seconds=settings.execution_stream_token_ttl_seconds,
    )


@router.get("/executions/{execution_id}/stream")
def stream_execution_output(
    execution_id: int,
    request: Request,
    poll_ms: int = Query(default=500, ge=100, le=5000),
    max_events: int = Query(default=0, ge=0, le=5000),
    token: str | None = Query(default=None, min_length=10),
):
    if token is not None:
        try:
            token_execution_id = verify_execution_stream_token(token)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid stream token")
        if token_execution_id != execution_id:
            raise HTTPException(status_code=401, detail="Stream token mismatch")
        if not consume_stream_token(token=token, execution_id=execution_id):
            raise HTTPException(status_code=409, detail="Stream token already used")
    else:
        require_read_access(
            request=request,
            x_csrf_token=request.headers.get("x-csrf-token"),
        )

    row = get_execution(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    def event_stream():
        stdout_path = row["stdout_path"]
        stderr_path = row["stderr_path"]
        out_pos = 0
        err_pos = 0
        sent = 0

        while True:
            current = get_execution(execution_id)
            if current is None:
                yield _sse_event("error", {"message": "Execution not found"})
                break

            for label, path, pos in (
                ("stdout", stdout_path, out_pos),
                ("stderr", stderr_path, err_pos),
            ):
                file_path = Path(path)
                if not file_path.exists():
                    continue
                with file_path.open("rb") as fh:
                    fh.seek(pos)
                    chunk = fh.read()
                    new_pos = fh.tell()
                if label == "stdout":
                    out_pos = new_pos
                else:
                    err_pos = new_pos
                if not chunk:
                    continue
                text = chunk.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    if not line:
                        continue
                    yield _sse_event(label, {"line": line})
                    sent += 1
                    if max_events > 0 and sent >= max_events:
                        return

            if current["finished_at"] is not None:
                yield _sse_event("done", {"exit_code": current["exit_code"]})
                return

            time.sleep(poll_ms / 1000)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
