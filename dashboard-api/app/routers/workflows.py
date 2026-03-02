"""GitHub Actions local run (act) API."""

import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.db.audit import write_audit_log
from app.security import require_read_access, require_write_access
from app.services.act_runner import is_act_available, list_workflow_jobs, run_act_job

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
def list_workflows(_actor: str = Depends(require_read_access)):
    """List workflow jobs from .github/workflows. Returns [{workflow, workflow_file, job}]."""
    _ensure_act_enabled()
    jobs = list_workflow_jobs(settings.act_workflows_path)
    return jobs


class RunJobRequest(BaseModel):
    job: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    workflow_file: str | None = Field(default=None, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")


@router.post("/run")
def run_job(request: RunJobRequest, actor: str = Depends(require_write_access)):
    """Run a workflow job via act. Streams output as SSE."""
    _ensure_act_enabled()

    jobs = list_workflow_jobs(settings.act_workflows_path)
    if request.workflow_file:
        matching = [j for j in jobs if j["workflow_file"] == request.workflow_file and j["job"] == request.job]
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
                settings.act_workflows_path,
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
