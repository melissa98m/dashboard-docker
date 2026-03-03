"""GitHub Actions local run (act) API."""

import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.db.audit import write_audit_log
from app.security import require_read_access, require_write_access
from app.services.act_runner import (
    get_workflows_path,
    is_act_available,
    list_workflow_jobs,
    run_act_job,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_ACT_STREAM_LOCK = threading.Lock()
_ACT_ACTIVE_JOBS: set[str] = set()


def _ensure_act_enabled() -> None:
    if not settings.act_enabled:
        raise HTTPException(status_code=503, detail="act feature is disabled (ACT_ENABLED=false)")
    if not is_act_available():
        raise HTTPException(status_code=503, detail="act binary not found")


def _sse_event(event_type: str, data: dict | str) -> str:
    payload = json.dumps(data) if isinstance(data, dict) else json.dumps({"text": data})
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.get("/", response_model=list[dict])
def list_workflows(
    container_id: str | None = Query(default=None, alias="container_id"),
    _actor: str = Depends(require_read_access),
):
    """List workflow jobs. Use container_id to get workflows from a container, else default path."""
    _ensure_act_enabled()
    try:
        base_path = get_workflows_path(container_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    jobs = list_workflow_jobs(base_path)
    return jobs


@router.get("/content")
def get_workflow_content(
    workflow_file: str = Query(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$"),
    container_id: str | None = Query(default=None, alias="container_id"),
    _actor: str = Depends(require_read_access),
):
    """Return raw YAML content of a workflow file."""
    _ensure_act_enabled()
    try:
        base_path = get_workflows_path(container_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    from pathlib import Path

    wf_path = Path(base_path) / ".github" / "workflows" / workflow_file
    if not wf_path.exists() or not wf_path.is_file():
        raise HTTPException(status_code=404, detail=f"Workflow file not found: {workflow_file}")
    try:
        return {"content": wf_path.read_text(encoding="utf-8", errors="replace")}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class RunJobRequest(BaseModel):
    job: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    workflow_file: str | None = Field(default=None, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    container_id: str | None = Field(default=None, max_length=128)


@router.post("/run")
def run_job(request: RunJobRequest, actor: str = Depends(require_write_access)):
    """Run a workflow job via act. Streams output as SSE.
    Use container_id for per-container workflows."""
    _ensure_act_enabled()
    try:
        base_path = get_workflows_path(request.container_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    jobs = list_workflow_jobs(base_path)
    if request.workflow_file:
        matching = [
            j
            for j in jobs
            if j["workflow_file"] == request.workflow_file and j["job"] == request.job
        ]
    else:
        matching = [j for j in jobs if j["job"] == request.job]
    if not matching:
        valid = ", ".join(f"{j['workflow_file']}:{j['job']}" for j in jobs[:10])
        raise HTTPException(status_code=400, detail=f"Job not found. Valid: {valid}")

    chosen = matching[0]
    job_key = f"{chosen['workflow_file']}:{chosen['job']}"

    with _ACT_STREAM_LOCK:
        if job_key in _ACT_ACTIVE_JOBS:
            raise HTTPException(status_code=429, detail="Job already running")
        _ACT_ACTIVE_JOBS.add(job_key)

    write_audit_log(
        action="act_job_run",
        resource_type="workflow",
        resource_id=job_key,
        triggered_by=actor,
        details={"job": chosen["job"], "workflow_file": chosen["workflow_file"]},
    )

    def event_stream():
        try:
            proc = run_act_job(
                base_path,
                chosen["job"],
                workflow_file=chosen["workflow_file"],
            )
            for line in proc.stdout or []:
                line = line.rstrip("\n\r")
                yield _sse_event("output", {"line": line})
            proc.wait()
            yield _sse_event("exit", {"code": proc.returncode or 0})
        except Exception as exc:
            logger.exception("act run failed: %s", exc)
            yield _sse_event("error", {"message": str(exc)})
        finally:
            with _ACT_STREAM_LOCK:
                _ACT_ACTIVE_JOBS.discard(job_key)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
