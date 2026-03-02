"""Container environment profile API."""

from __future__ import annotations

from pathlib import Path

import docker
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.db.audit import write_audit_log
from app.db.container_env_profiles import get_profile, touch_detect_result, upsert_profile
from app.security import require_write_access
from app.services.container_env import (
    detect_env_file,
    is_sensitive_key,
    load_runtime_env,
    merge_env,
    parse_env_file,
    recreate_container_with_env,
    write_env_file_atomic,
)

router = APIRouter()


def _docker_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


class EnvVarItem(BaseModel):
    key: str
    value: str
    sensitive: bool


class EnvProfileResponse(BaseModel):
    container_id: str
    source_mode: str
    detected_env_file: str | None
    writable: bool
    pending_apply: bool
    last_detect_status: str | None = None
    last_apply_status: str | None = None
    updated_at: str | None = None
    env: list[EnvVarItem]


class EnvProfileUpdateRequest(BaseModel):
    mode: str = Field(default="merge", pattern="^(merge|replace)$")
    set: dict[str, str] = Field(default_factory=dict)
    unset: list[str] = Field(default_factory=list)


class EnvDetectResponse(BaseModel):
    detected: bool
    source_mode: str
    selected_path: str | None
    candidate_paths: list[str]
    writable: bool
    reason: str


class EnvApplyRequest(BaseModel):
    dry_run: bool = False


class EnvApplyResponse(BaseModel):
    ok: bool
    strategy: str
    message: str
    old_container_id: str
    new_container_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


def _to_items(env: dict[str, str]) -> list[EnvVarItem]:
    return [
        EnvVarItem(key=key, value=value, sensitive=is_sensitive_key(key))
        for key, value in sorted(env.items(), key=lambda item: item[0])
    ]


def _load_env_state(container_id: str) -> tuple[dict[str, str], str, str | None, bool]:
    try:
        client = _docker_client()
        container = client.containers.get(container_id)
    except docker.errors.NotFound as exc:
        raise HTTPException(status_code=404, detail="Container not found") from exc
    except docker.errors.DockerException as exc:
        raise HTTPException(status_code=503, detail="Docker engine unavailable") from exc

    env_file, writable, _candidates = detect_env_file(container)
    runtime_env = load_runtime_env(container)
    source_mode = "db_fallback"
    detect_status = "db_fallback_no_env_file"
    final_env = runtime_env
    if env_file is not None:
        source_mode = "env_file"
        detect_status = "env_file_detected_writable" if writable else "env_file_detected_readonly"
        final_env = parse_env_file(Path(env_file)) if writable else runtime_env
    profile = get_profile(container_id)
    if profile is not None:
        profile_env = profile.get("env")
        if isinstance(profile_env, dict) and profile_env:
            final_env = {key: str(value) for key, value in profile_env.items()}
            source_mode = str(profile.get("source_mode") or source_mode)
    touch_detect_result(
        container_id=container_id,
        source_mode=source_mode,
        detected_env_file=env_file,
        last_detect_status=detect_status,
        updated_by="env-detect",
    )
    return final_env, source_mode, env_file, writable


@router.get("/{container_id}/env/profile", response_model=EnvProfileResponse)
def get_env_profile(container_id: str, _actor: str = Depends(require_write_access)):
    env, source_mode, env_file, writable = _load_env_state(container_id)
    profile = get_profile(container_id)
    return EnvProfileResponse(
        container_id=container_id,
        source_mode=source_mode,
        detected_env_file=env_file,
        writable=writable,
        pending_apply=bool(profile.get("pending_apply")) if profile else False,
        last_detect_status=(str(profile.get("last_detect_status")) if profile else None),
        last_apply_status=(str(profile.get("last_apply_status")) if profile else None),
        updated_at=(str(profile.get("updated_at")) if profile else None),
        env=_to_items(env),
    )


@router.post("/{container_id}/env/detect", response_model=EnvDetectResponse)
def detect_env_source(container_id: str, actor: str = Depends(require_write_access)):
    try:
        client = _docker_client()
        container = client.containers.get(container_id)
    except docker.errors.NotFound as exc:
        raise HTTPException(status_code=404, detail="Container not found") from exc
    except docker.errors.DockerException as exc:
        raise HTTPException(status_code=503, detail="Docker engine unavailable") from exc
    env_file, writable, candidates = detect_env_file(container)
    source_mode = "env_file" if env_file is not None else "db_fallback"
    reason = "env_file_detected" if env_file is not None else "env_file_not_found"
    touch_detect_result(
        container_id=container_id,
        source_mode=source_mode,
        detected_env_file=env_file,
        last_detect_status=reason,
        updated_by=actor,
    )
    write_audit_log(
        action="container_env_detect",
        resource_type="container",
        resource_id=container_id,
        triggered_by=actor,
        details={"source_mode": source_mode, "candidate_count": str(len(candidates))},
    )
    return EnvDetectResponse(
        detected=env_file is not None,
        source_mode=source_mode,
        selected_path=env_file,
        candidate_paths=candidates,
        writable=writable,
        reason=reason,
    )


@router.put("/{container_id}/env/profile", response_model=EnvProfileResponse)
def update_env_profile(
    container_id: str,
    payload: EnvProfileUpdateRequest,
    actor: str = Depends(require_write_access),
):
    current, source_mode, env_file, writable = _load_env_state(container_id)
    try:
        merged = merge_env(
            current=current,
            updates=payload.set,
            unset=payload.unset,
            mode=payload.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if env_file is not None and writable:
        try:
            write_env_file_atomic(Path(env_file), merged)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Unable to write env file: {exc}") from exc
        source_mode = "env_file"
    profile = upsert_profile(
        container_id=container_id,
        env=merged,
        source_mode=source_mode,
        detected_env_file=env_file,
        last_detect_status="env_updated",
        last_apply_status="pending",
        pending_apply=True,
        updated_by=actor,
    )
    write_audit_log(
        action="container_env_profile_update",
        resource_type="container",
        resource_id=container_id,
        triggered_by=actor,
        details={
            "set_count": str(len(payload.set)),
            "unset_count": str(len(payload.unset)),
            "mode": payload.mode,
            "keys": ",".join(sorted(payload.set.keys())),
        },
    )
    return EnvProfileResponse(
        container_id=container_id,
        source_mode=str(profile["source_mode"]),
        detected_env_file=(
            str(profile["detected_env_file"]) if profile.get("detected_env_file") else None
        ),
        writable=writable,
        pending_apply=bool(profile["pending_apply"]),
        last_detect_status=(
            str(profile["last_detect_status"]) if profile.get("last_detect_status") else None
        ),
        last_apply_status=(
            str(profile["last_apply_status"]) if profile.get("last_apply_status") else None
        ),
        updated_at=str(profile["updated_at"]) if profile.get("updated_at") else None,
        env=_to_items(merged),
    )


@router.post("/{container_id}/env/apply", response_model=EnvApplyResponse)
def apply_env_profile(
    container_id: str,
    payload: EnvApplyRequest,
    actor: str = Depends(require_write_access),
):
    profile = get_profile(container_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Env profile not found")
    env_payload = profile.get("env")
    env = (
        {key: str(value) for key, value in env_payload.items()}
        if isinstance(env_payload, dict)
        else {}
    )
    if payload.dry_run:
        return EnvApplyResponse(
            ok=True,
            strategy="recreate",
            message="Dry run completed",
            old_container_id=container_id,
            new_container_id=None,
            warnings=[],
        )
    try:
        client = _docker_client()
        container = client.containers.get(container_id)
        new_container_id, warnings = recreate_container_with_env(
            client=client,
            container=container,
            env=env,
        )
    except docker.errors.NotFound as exc:
        raise HTTPException(status_code=404, detail="Container not found") from exc
    except docker.errors.DockerException as exc:
        raise HTTPException(status_code=503, detail="Docker engine unavailable") from exc
    except ValueError as exc:
        write_audit_log(
            action="container_env_apply_failed",
            resource_type="container",
            resource_id=container_id,
            triggered_by=actor,
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    upsert_profile(
        container_id=container_id,
        env=env,
        source_mode=str(profile.get("source_mode") or "db_fallback"),
        detected_env_file=(
            str(profile.get("detected_env_file")) if profile.get("detected_env_file") else None
        ),
        last_detect_status=(
            str(profile.get("last_detect_status")) if profile.get("last_detect_status") else None
        ),
        last_apply_status="applied",
        pending_apply=False,
        updated_by=actor,
    )
    write_audit_log(
        action="container_env_apply_recreate",
        resource_type="container",
        resource_id=container_id,
        triggered_by=actor,
        details={
            "new_container_id": new_container_id or "",
            "warning_count": str(len(warnings)),
        },
    )
    return EnvApplyResponse(
        ok=True,
        strategy="recreate",
        message="Container recreated with updated env",
        old_container_id=container_id,
        new_container_id=new_container_id,
        warnings=warnings,
    )
