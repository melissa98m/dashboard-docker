"""Alert rules API."""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Literal

import docker
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.db.alerts import create_rule, delete_rule, evaluate_rules, get_rule, list_rules, update_rule
from app.db.audit import list_audit_logs, write_audit_log
from app.security import require_read_access, require_write_access

router = APIRouter()

MetricType = Literal["cpu_percent", "ram_mb", "ram_percent"]


class AlertRuleCreate(BaseModel):
    container_id: str = Field(min_length=1, max_length=128)
    container_name: str = Field(min_length=1, max_length=255)
    metric_type: MetricType
    threshold: float = Field(ge=0)
    cooldown_seconds: int = Field(default=300, ge=1, le=86400)
    debounce_samples: int = Field(default=1, ge=1, le=20)
    ntfy_topic: str | None = Field(default=None, max_length=255)
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    container_name: str | None = Field(default=None, min_length=1, max_length=255)
    threshold: float | None = Field(default=None, ge=0)
    cooldown_seconds: int | None = Field(default=None, ge=1, le=86400)
    debounce_samples: int | None = Field(default=None, ge=1, le=20)
    ntfy_topic: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None


class AlertRuleResponse(BaseModel):
    id: int
    container_id: str
    container_name: str
    metric_type: MetricType
    threshold: float
    cooldown_seconds: int
    debounce_samples: int
    ntfy_topic: str | None
    enabled: bool
    created_at: str
    updated_at: str


class EvaluateRequest(BaseModel):
    container_id: str = Field(min_length=1, max_length=128)
    metric_type: MetricType
    value: float = Field(ge=0)


class EvaluateRuleResult(BaseModel):
    rule_id: int
    triggered: bool
    reason: str
    cooldown_remaining_seconds: int | None = None
    debounce_progress: int | None = None
    debounce_required: int | None = None
    container_name: str | None = None
    threshold: float | None = None
    ntfy_topic: str | None = None


class EvaluateResponse(BaseModel):
    results: list[EvaluateRuleResult]


class AlertActionResponse(BaseModel):
    ok: bool
    message: str


class AlertHistoryItem(BaseModel):
    id: int
    rule_id: int | None
    container_id: str | None
    container_name: str | None
    metric_type: MetricType | None
    value: float | None
    triggered_by: str
    created_at: str
    can_restart: bool


class AlertHistoryResponse(BaseModel):
    items: list[AlertHistoryItem]
    total: int
    limit: int
    offset: int
    sort: str


def _get_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


@router.get("/rules", response_model=list[AlertRuleResponse])
def get_rules(_actor: str = Depends(require_read_access)):
    return list_rules()


@router.post("/rules", response_model=AlertRuleResponse)
def post_rule(payload: AlertRuleCreate, actor: str = Depends(require_write_access)):
    try:
        created = create_rule(
            container_id=payload.container_id,
            container_name=payload.container_name,
            metric_type=payload.metric_type,
            threshold=payload.threshold,
            cooldown_seconds=payload.cooldown_seconds,
            debounce_samples=payload.debounce_samples,
            ntfy_topic=payload.ntfy_topic,
            enabled=payload.enabled,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A rule already exists for this container and metric",
        )
    write_audit_log(
        action="alert_rule_create",
        resource_type="alert_rule",
        resource_id=str(created["id"]),
        triggered_by=actor,
        details={"metric_type": str(created["metric_type"])},
    )
    return created


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
def patch_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    actor: str = Depends(require_write_access),
):
    updates = payload.model_dump(exclude_unset=True)
    try:
        updated = update_rule(rule_id, updates)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Invalid update for this alert rule",
        )
    if updated is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    write_audit_log(
        action="alert_rule_update",
        resource_type="alert_rule",
        resource_id=str(rule_id),
        triggered_by=actor,
        details={"fields": ",".join(sorted(updates.keys()))},
    )
    return updated


@router.delete("/rules/{rule_id}")
def remove_rule(rule_id: int, actor: str = Depends(require_write_access)):
    deleted = delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    write_audit_log(
        action="alert_rule_delete",
        resource_type="alert_rule",
        resource_id=str(rule_id),
        triggered_by=actor,
        details={"result": "ok"},
    )
    return {"ok": True}


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(payload: EvaluateRequest, actor: str = Depends(require_write_access)):
    results = evaluate_rules(
        container_id=payload.container_id,
        metric_type=payload.metric_type,
        value=payload.value,
    )
    for item in results:
        if item["triggered"]:
            write_audit_log(
                action="alert_triggered",
                resource_type="alert_rule",
                resource_id=str(item["rule_id"]),
                triggered_by=actor,
                details={
                    "metric_type": payload.metric_type,
                    "value": f"{payload.value:.2f}",
                    "container_id": payload.container_id,
                    "container_name": item.get("container_name", ""),
                },
            )
    return EvaluateResponse(results=[EvaluateRuleResult(**item) for item in results])


@router.post("/rules/{rule_id}/restart-container", response_model=AlertActionResponse)
def restart_alert_container(rule_id: int, actor: str = Depends(require_write_access)):
    """Restart container linked to alert rule from dashboard UI."""
    rule = get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    container_id = str(rule["container_id"])
    try:
        client = _get_client()
        container = client.containers.get(container_id)
        container.restart()
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.DockerException:
        raise HTTPException(status_code=400, detail="Unable to restart container")

    write_audit_log(
        action="alert_rule_restart_container",
        resource_type="alert_rule",
        resource_id=str(rule_id),
        triggered_by=actor,
        details={
            "container_id": container_id,
            "container_name": str(rule.get("container_name", "")),
            "result": "ok",
        },
    )
    return AlertActionResponse(ok=True, message="Container restarted")


@router.get("/history", response_model=AlertHistoryResponse)
def get_alert_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    container_id: str | None = Query(default=None, min_length=1, max_length=128),
    metric_type: MetricType | None = Query(default=None),
    since_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    sort: Literal["created_at_desc", "created_at_asc"] = Query(default="created_at_desc"),
    triggered_by: Literal["all", "manual", "alert-engine"] = Query(default="all"),
    _actor: str = Depends(require_read_access),
):
    """List recent triggered alerts from audit logs."""
    # Read a bounded window then apply typed filters in Python to avoid leaking
    # raw JSON query details into SQL and keep behavior deterministic.
    rows = list_audit_logs(action=None, limit=500, offset=0)
    all_items: list[AlertHistoryItem] = []
    since_cutoff: datetime | None = None
    if since_hours is not None:
        since_cutoff = datetime.now(UTC) - timedelta(hours=since_hours)

    for row in rows:
        action = str(row.get("action") or "")
        if action not in {"alert_triggered", "alert_triggered_auto"}:
            continue

        details = row.get("details", {})
        rule_id: int | None = None
        raw_rule_id = row.get("resource_id")
        if isinstance(raw_rule_id, str) and raw_rule_id.isdigit():
            rule_id = int(raw_rule_id)
        raw_value = details.get("value")
        value: float | None = None
        if isinstance(raw_value, str):
            try:
                value = float(raw_value)
            except ValueError:
                value = None
        metric = details.get("metric_type")
        normalized_metric_type: MetricType | None = (
            metric if metric in {"cpu_percent", "ram_mb", "ram_percent"} else None
        )
        detail_container_id = details.get("container_id")
        container_name = details.get("container_name")
        created_at = str(row["created_at"])
        created_dt: datetime | None = None
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            created_dt = None

        normalized_container_id = detail_container_id if isinstance(detail_container_id, str) else None
        if container_id is not None and normalized_container_id != container_id:
            continue
        if metric_type is not None and normalized_metric_type != metric_type:
            continue
        if since_cutoff is not None and created_dt is not None and created_dt < since_cutoff:
            continue

        normalized_triggered_by = str(row.get("triggered_by") or "unknown")
        normalized_source = "alert-engine" if normalized_triggered_by == "alert-engine" else "manual"
        if triggered_by != "all" and normalized_source != triggered_by:
            continue

        all_items.append(
            AlertHistoryItem(
                id=int(row["id"]),
                rule_id=rule_id,
                container_id=normalized_container_id,
                container_name=container_name if isinstance(container_name, str) else None,
                metric_type=normalized_metric_type,
                value=value,
                triggered_by=normalized_triggered_by,
                created_at=created_at,
                can_restart=rule_id is not None and isinstance(normalized_container_id, str) and bool(normalized_container_id),
            )
        )
    if sort == "created_at_asc":
        all_items.reverse()

    total = len(all_items)
    page = all_items[offset : offset + limit]
    return AlertHistoryResponse(
        items=page,
        total=total,
        limit=limit,
        offset=offset,
        sort=sort,
    )
