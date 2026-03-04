"""Volumes API — list, inspect, delete."""

import logging
from typing import Any

import docker
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.db.audit import write_audit_log
from app.security import require_read_access, require_write_access

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


def _audit_volume_action(
    *,
    action: str,
    volume_name: str | None,
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
        resource_type="volume",
        resource_id=volume_name,
        triggered_by=actor,
        details={key: str(value) for key, value in details.items()},
    )


@router.get("")
def list_volumes(
    _actor: str = Depends(require_read_access),
):
    """List all volumes."""
    try:
        client = _get_client()
        volumes_data = client.volumes.list()
        result = []
        for vol in volumes_data:
            attrs = vol.attrs or {}
            labels = attrs.get("Labels") or {}
            driver = attrs.get("Driver", "local")
            result.append(
                {
                    "name": vol.name,
                    "driver": driver,
                    "labels": labels,
                    "mountpoint": attrs.get("Mountpoint", ""),
                    "created_at": attrs.get("CreatedAt", ""),
                }
            )
        return result
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.get("/{volume_name}")
def get_volume_detail(
    volume_name: str,
    _actor: str = Depends(require_read_access),
):
    """Get volume details (inspect)."""
    if not volume_name or len(volume_name) > 255:
        raise HTTPException(status_code=422, detail="Invalid volume name")
    try:
        client = _get_client()
        volume = client.volumes.get(volume_name)
        attrs = volume.attrs or {}
        # Find containers using this volume
        containers_using: list[dict[str, str]] = []
        try:
            for c in client.containers.list(all=True):
                mounts = (c.attrs or {}).get("Mounts") or []
                for m in mounts:
                    if isinstance(m, dict):
                        name = m.get("Name") or m.get("Source", "")
                        if name == volume_name:
                            containers_using.append({"id": c.short_id, "name": c.name.lstrip("/")})
                            break
        except docker.errors.DockerException:
            pass
        return {
            "name": volume.name,
            "driver": attrs.get("Driver", "local"),
            "mountpoint": attrs.get("Mountpoint", ""),
            "labels": attrs.get("Labels") or {},
            "created_at": attrs.get("CreatedAt", ""),
            "scope": attrs.get("Scope", "local"),
            "containers_using": containers_using,
        }
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Volume not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.delete("/{volume_name}")
def delete_volume(
    volume_name: str,
    force: bool = Query(default=False),
    actor: str = Depends(require_write_access),
):
    """Delete a volume."""
    if not volume_name or len(volume_name) > 255:
        raise HTTPException(status_code=422, detail="Invalid volume name")
    try:
        client = _get_client()
        volume = client.volumes.get(volume_name)
        volume.remove(force=force)
        _audit_volume_action(
            action="volume_delete",
            volume_name=volume_name,
            actor=actor,
            result="ok",
            extra={"force": force},
        )
        return {"ok": True, "message": f"Volume {volume_name} deleted"}
    except docker.errors.NotFound:
        _audit_volume_action(
            action="volume_delete",
            volume_name=volume_name,
            actor=actor,
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Volume not found")
    except docker.errors.APIError as e:
        _audit_volume_action(
            action="volume_delete",
            volume_name=volume_name,
            actor=actor,
            result="error",
            reason=str(e.explanation)[:200] if e.explanation else "api_error",
        )
        raise HTTPException(
            status_code=409,
            detail=e.explanation or "Volume in use, cannot remove",
        )
    except docker.errors.DockerException:
        _audit_volume_action(
            action="volume_delete",
            volume_name=volume_name,
            actor=actor,
            result="error",
            reason="docker_error",
        )
        raise HTTPException(status_code=400, detail="Unable to delete volume")
