"""Audit log API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.config import settings
from app.db.audit import (
    count_audit_logs,
    count_purgeable_audit_logs,
    list_audit_logs,
    purge_audit_logs,
    write_audit_log,
)
from app.security import require_read_access, require_write_access

router = APIRouter()


class AuditLogItem(BaseModel):
    id: int
    action: str
    resource_type: str
    resource_id: str | None
    triggered_by: str
    details: dict[str, Any]
    created_at: str


class PurgeAuditResponse(BaseModel):
    ok: bool
    deleted_rows: int
    retention_days: int


class PurgeAuditDryRunResponse(BaseModel):
    ok: bool
    purgeable_rows: int
    retention_days: int


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int


@router.get("/logs", response_model=list[AuditLogItem] | AuditLogListResponse)
def get_audit_logs(
    action: str | None = Query(default=None, min_length=1, max_length=100),
    resource_type: str | None = Query(default=None, min_length=1, max_length=100),
    triggered_by: str | None = Query(default=None, min_length=1, max_length=100),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_total: bool = Query(default=False),
    _actor: str = Depends(require_read_access),
):
    """Read audit logs with optional filtering and pagination metadata."""
    rows = list_audit_logs(
        action=action,
        resource_type=resource_type,
        triggered_by=triggered_by,
        query=q,
        limit=limit,
        offset=offset,
    )
    items = [AuditLogItem(**row) for row in rows]
    if not include_total:
        return items
    total = count_audit_logs(
        action=action,
        resource_type=resource_type,
        triggered_by=triggered_by,
        query=q,
    )
    return AuditLogListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/purge", response_model=PurgeAuditResponse)
def purge_logs(
    days: int | None = Query(default=None, ge=1, le=3650),
    actor: str = Depends(require_write_access),
):
    """Purge old audit logs based on retention period."""
    retention_days = days if days is not None else settings.audit_retention_days
    deleted = purge_audit_logs(older_than_days=retention_days)
    write_audit_log(
        action="audit_purge",
        resource_type="audit_log",
        resource_id=None,
        triggered_by=actor,
        details={
            "deleted_rows": str(deleted),
            "retention_days": str(retention_days),
        },
    )
    return PurgeAuditResponse(
        ok=True,
        deleted_rows=deleted,
        retention_days=retention_days,
    )


@router.get("/purge-dry-run", response_model=PurgeAuditDryRunResponse)
def purge_logs_dry_run(
    days: int | None = Query(default=None, ge=1, le=3650),
    _actor: str = Depends(require_read_access),
):
    """Estimate how many rows would be purged."""
    retention_days = days if days is not None else settings.audit_retention_days
    purgeable = count_purgeable_audit_logs(older_than_days=retention_days)
    return PurgeAuditDryRunResponse(
        ok=True,
        purgeable_rows=purgeable,
        retention_days=retention_days,
    )
