"""Images API — list, inspect, delete."""

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


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _image_tags(image: Any) -> list[str]:
    tags = getattr(image, "tags", None) or []
    return [str(t) for t in tags] if tags else []


def _image_display_name(image: Any) -> str:
    tags = _image_tags(image)
    if tags:
        return tags[0]
    return str(getattr(image, "short_id", image.id[:12]))


def _audit_image_action(
    *,
    action: str,
    image_id: str | None,
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
        resource_type="image",
        resource_id=image_id,
        triggered_by=actor,
        details={key: str(value) for key, value in details.items()},
    )


@router.get("")
def list_images(
    dangling: bool | None = Query(default=None, description="Filter dangling images"),
    all_layers: bool = Query(default=False, alias="all", description="Show intermediate layers"),
    _actor: str = Depends(require_read_access),
):
    """List all images. Optionally filter by dangling or show all layers."""
    try:
        client = _get_client()
        filters: dict[str, Any] = {}
        if dangling is not None:
            filters["dangling"] = [str(dangling).lower()]
        images = client.images.list(all=all_layers, filters=filters if filters else None)
        result = []
        for img in images:
            attrs = img.attrs or {}
            created = attrs.get("Created", "")
            size = attrs.get("Size", 0) or 0
            result.append(
                {
                    "id": img.short_id,
                    "tags": _image_tags(img),
                    "display_name": _image_display_name(img),
                    "size": size,
                    "size_human": _format_size(size),
                    "created": created,
                }
            )
        return result
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.get("/{image_id}")
def get_image_detail(
    image_id: str,
    _actor: str = Depends(require_read_access),
):
    """Get image details (inspect)."""
    try:
        client = _get_client()
        image = client.images.get(image_id)
        attrs = image.attrs or {}
        size = attrs.get("Size", 0) or 0
        return {
            "id": image.short_id,
            "tags": _image_tags(image),
            "display_name": _image_display_name(image),
            "size": size,
            "size_human": _format_size(size),
            "created": attrs.get("Created", ""),
            "labels": attrs.get("Config", {}).get("Labels") or {},
            "architecture": attrs.get("Architecture", ""),
            "os": attrs.get("Os", ""),
            "parent": attrs.get("Parent", ""),
        }
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=404, detail="Image not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=503, detail="Docker engine unavailable")


@router.delete("/{image_id}")
def delete_image(
    image_id: str,
    force: bool = Query(default=False),
    actor: str = Depends(require_write_access),
):
    """Delete an image."""
    try:
        client = _get_client()
        image = client.images.get(image_id)
        display = _image_display_name(image)
        client.images.remove(image_id, force=force)
        _audit_image_action(
            action="image_delete",
            image_id=image_id,
            actor=actor,
            result="ok",
            extra={"force": force, "display": display},
        )
        return {"ok": True, "message": f"Image {display} deleted"}
    except docker.errors.ImageNotFound:
        _audit_image_action(
            action="image_delete",
            image_id=image_id,
            actor=actor,
            result="error",
            reason="not_found",
        )
        raise HTTPException(status_code=404, detail="Image not found")
    except docker.errors.APIError as e:
        _audit_image_action(
            action="image_delete",
            image_id=image_id,
            actor=actor,
            result="error",
            reason=str(e.explanation)[:200] if e.explanation else "api_error",
        )
        raise HTTPException(
            status_code=409,
            detail=e.explanation or "Image in use, cannot remove",
        )
    except docker.errors.DockerException:
        _audit_image_action(
            action="image_delete",
            image_id=image_id,
            actor=actor,
            result="error",
            reason="docker_error",
        )
        raise HTTPException(status_code=400, detail="Unable to delete image")
