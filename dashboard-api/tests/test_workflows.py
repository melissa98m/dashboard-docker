"""Tests for act workflows API."""

import pytest

from app.config import settings
from app.services.act_runner import list_workflow_jobs


def test_list_workflow_jobs_parses_ci_workflow(tmp_path):
    """list_workflow_jobs parses .github/workflows/*.yml correctly."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        """
name: CI
on: push
jobs:
  lint:
    runs-on: ubuntu-latest
    steps: []
  test:
    runs-on: ubuntu-latest
    steps: []
"""
    )
    jobs = list_workflow_jobs(str(tmp_path))
    assert len(jobs) == 2
    names = {j["job"] for j in jobs}
    assert names == {"lint", "test"}
    assert all(j["workflow"] == "CI" for j in jobs)
    assert all(j["workflow_file"] == "ci.yml" for j in jobs)


def test_list_workflow_jobs_empty_when_no_workflows(tmp_path):
    """list_workflow_jobs returns empty when .github/workflows does not exist."""
    jobs = list_workflow_jobs(str(tmp_path))
    assert jobs == []


def test_workflows_list_disabled_returns_503(client):
    """GET /api/workflows returns 503 when ACT_ENABLED=false."""
    from tests.conftest import login_as_admin

    previous = settings.act_enabled
    settings.act_enabled = False
    settings.auth_enabled = True
    try:
        login_as_admin(client)
        r = client.get("/api/workflows")
        assert r.status_code == 503, r.json()
        assert "disabled" in r.json().get("detail", "").lower()
    finally:
        settings.act_enabled = previous


def test_workflows_list_requires_auth(client):
    """GET /api/workflows requires authentication when auth enabled."""
    from app.db.auth import ensure_bootstrap_admin
    from tests.conftest import login_as_admin

    previous = settings.act_enabled
    settings.auth_enabled = True
    settings.act_enabled = True
    try:
        ensure_bootstrap_admin()
        r = client.get("/api/workflows")
        assert r.status_code in (401, 403)
        login_as_admin(client)
        r = client.get("/api/workflows")
        assert r.status_code in (200, 503)
    finally:
        settings.act_enabled = previous


def test_workflows_list_returns_jobs_when_enabled(client, monkeypatch):
    """GET /api/workflows returns parsed jobs when act enabled and workflows exist."""
    from tests.conftest import login_as_admin

    previous = settings.act_enabled
    settings.act_enabled = True
    monkeypatch.setattr(
        "app.routers.workflows.list_workflow_jobs",
        lambda p: [{"workflow": "CI", "workflow_file": "ci.yml", "job": "lint"}],
    )
    monkeypatch.setattr(
        "app.routers.workflows.is_act_available",
        lambda: True,
    )
    try:
        login_as_admin(client)
        r = client.get("/api/workflows")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["job"] == "lint"
        assert data[0]["workflow_file"] == "ci.yml"
    finally:
        settings.act_enabled = previous


def test_workflows_run_disabled_returns_503(client):
    """POST /api/workflows/run returns 503 when ACT_ENABLED=false."""
    from tests.conftest import login_as_admin

    previous = settings.act_enabled
    settings.act_enabled = False
    settings.auth_enabled = True
    try:
        csrf = login_as_admin(client)
        r = client.post(
            "/api/workflows/run",
            json={"job": "lint"},
            headers={"x-csrf-token": csrf},
        )
        assert r.status_code == 503
    finally:
        settings.act_enabled = previous


def test_workflows_run_invalid_job_returns_400(client, monkeypatch):
    """POST /api/workflows/run returns 400 for unknown job."""
    from tests.conftest import login_as_admin

    previous = settings.act_enabled
    settings.act_enabled = True
    settings.auth_enabled = True
    monkeypatch.setattr(
        "app.routers.workflows.list_workflow_jobs",
        lambda p: [{"workflow": "CI", "workflow_file": "ci.yml", "job": "lint"}],
    )
    monkeypatch.setattr(
        "app.routers.workflows.is_act_available",
        lambda: True,
    )
    try:
        csrf = login_as_admin(client)
        r = client.post(
            "/api/workflows/run",
            json={"job": "unknown-job"},
            headers={"x-csrf-token": csrf},
        )
        assert r.status_code == 400
    finally:
        settings.act_enabled = previous


def test_workflows_run_streams_output(client, monkeypatch):
    """POST /api/workflows/run streams SSE output."""
    from unittest.mock import MagicMock

    from tests.conftest import login_as_admin

    previous = settings.act_enabled
    settings.act_enabled = True
    settings.auth_enabled = True
    monkeypatch.setattr(
        "app.routers.workflows.list_workflow_jobs",
        lambda p: [{"workflow": "CI", "workflow_file": "ci.yml", "job": "lint"}],
    )
    monkeypatch.setattr(
        "app.routers.workflows.is_act_available",
        lambda: True,
    )
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["line1\n", "line2\n"])
    mock_proc.returncode = 0
    mock_proc.wait = lambda: None

    def fake_run(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr("app.routers.workflows.run_act_job", fake_run)
    try:
        csrf = login_as_admin(client)
        r = client.post(
            "/api/workflows/run",
            json={"job": "lint"},
            headers={"x-csrf-token": csrf},
        )
        assert r.status_code == 200, r.text[:500]
        assert "text/event-stream" in r.headers.get("content-type", "")
        content = r.text
        assert "event: output" in content
        assert "line1" in content or '"line1"' in content
        assert "event: exit" in content
    finally:
        settings.act_enabled = previous
