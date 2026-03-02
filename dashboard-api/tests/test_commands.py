"""Command center endpoints tests."""

from pathlib import Path

from app.config import settings
from app.security import create_execution_stream_token
from tests.conftest import login_as_admin


class _FakeExecResult:
    def __init__(self, exit_code: int, output):
        self.exit_code = exit_code
        self.output = output


class _FakeContainer:
    name = "svc-api"

    def exec_run(self, cmd, workdir=None, environment=None, demux=True):
        assert isinstance(cmd, list)
        assert demux is True
        if cmd[:2] == ["cat", "/app/package.json"] or cmd[:2] == ["cat", "package.json"]:
            return _FakeExecResult(
                0,
                (
                    b'{"scripts":{"test":"vitest run","lint":"eslint .","start":"next start"}}',
                    b"",
                ),
            )
        if cmd[:2] == ["cat", "/app/Makefile"] or cmd[:2] == ["cat", "Makefile"]:
            return _FakeExecResult(1, (b"", b"missing"))
        if cmd[:2] == ["cat", "/app/pyproject.toml"] or cmd[:2] == ["cat", "pyproject.toml"]:
            return _FakeExecResult(1, (b"", b"missing"))
        if cmd[:2] == ["cat", "/app/manage.py"] or cmd[:2] == ["cat", "manage.py"]:
            return _FakeExecResult(1, (b"", b"missing"))
        if cmd[:2] == ["cat", "/app/composer.json"] or cmd[:2] == ["cat", "composer.json"]:
            return _FakeExecResult(1, (b"", b"missing"))
        return _FakeExecResult(0, (b"stdout-ok", b"stderr-warn"))


class _FakeContainers:
    def list(self):
        return [self.get("abc123")]

    def get(self, container_id: str):
        if container_id != "abc123":
            raise KeyError("not found")
        return _FakeContainer()


class _FakeDockerClient:
    containers = _FakeContainers()


def _run_immediately(**kwargs):
    from app.routers import commands as commands_router

    commands_router._execute_worker(**kwargs)


def test_command_specs_crud_list(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    create = client.post(
        "/api/commands/specs",
        json={
            "container_id": "abc123",
            "service_name": "api",
            "name": "Run tests",
            "argv": ["pytest", "-q"],
            "cwd": "/app",
            "env_allowlist": [],
        },
        headers=headers,
    )
    assert create.status_code == 200
    spec_id = create.json()["id"]
    assert spec_id > 0

    listed = client.get("/api/commands/specs")
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload) == 1
    assert payload[0]["argv"] == ["pytest", "-q"]


def test_command_specs_reject_disallowed_shell_argv(client):
    csrf = login_as_admin(client)
    response = client.post(
        "/api/commands/specs",
        json={
            "container_id": "abc123",
            "service_name": "api",
            "name": "Unsafe shell",
            "argv": ["sh", "-c", "echo hello"],
            "cwd": "/app",
            "env_allowlist": [],
        },
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 422
    audit_logs = client.get("/api/audit/logs?action=command_spec_create")
    assert audit_logs.status_code == 200
    entries = audit_logs.json()
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["details"]["result"] == "error"
    assert latest["details"]["reason"] == "invalid_argv"


def test_command_execute_and_history(client, monkeypatch):
    from app.routers import commands as commands_router

    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    monkeypatch.setattr(commands_router, "_docker_client", lambda: _FakeDockerClient())
    monkeypatch.setattr(commands_router, "_spawn_execution", _run_immediately)
    create = client.post(
        "/api/commands/specs",
        json={
            "container_id": "abc123",
            "service_name": "api",
            "name": "Run tests",
            "argv": ["pytest", "-q"],
            "cwd": "/app",
            "env_allowlist": [],
        },
        headers=headers,
    )
    spec_id = create.json()["id"]
    run = client.post("/api/commands/execute", json={"spec_id": spec_id}, headers=headers)
    assert run.status_code == 200
    execution_id = run.json()["execution_id"]
    assert run.json()["status"] == "started"

    listed = client.get("/api/commands/executions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"/api/commands/executions/{execution_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert "stdout-ok" in payload["stdout_tail"]
    assert "stderr-warn" in payload["stderr_tail"]
    assert Path(payload["stdout_path"]).exists()

    stream = client.get(f"/api/commands/executions/{execution_id}/stream?max_events=1")
    assert stream.status_code == 200
    assert "event: stdout" in stream.text


def test_execution_stream_token_flow(client, monkeypatch):
    from app.routers import commands as commands_router

    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    monkeypatch.setattr(commands_router, "_docker_client", lambda: _FakeDockerClient())
    monkeypatch.setattr(commands_router, "_spawn_execution", _run_immediately)
    create = client.post(
        "/api/commands/specs",
        json={
            "container_id": "abc123",
            "service_name": "api",
            "name": "Run tests",
            "argv": ["pytest", "-q"],
            "cwd": "/app",
            "env_allowlist": [],
        },
        headers=headers,
    )
    spec_id = create.json()["id"]
    run = client.post("/api/commands/execute", json={"spec_id": spec_id}, headers=headers)
    execution_id = run.json()["execution_id"]

    previous_secret = settings.api_secret_key
    settings.api_secret_key = "stream-secret"
    try:
        token_response = client.get(f"/api/commands/executions/{execution_id}/stream-token")
        assert token_response.status_code == 200
        token = token_response.json()["token"]

        stream = client.get(
            f"/api/commands/executions/{execution_id}/stream?token={token}&max_events=1"
        )
        assert stream.status_code == 200
        assert "event: stdout" in stream.text

        replay = client.get(
            f"/api/commands/executions/{execution_id}/stream?token={token}&max_events=1"
        )
        assert replay.status_code == 409
    finally:
        settings.api_secret_key = previous_secret


def test_execution_stream_token_rejects_mismatch(client):
    login_as_admin(client)
    previous_secret = settings.api_secret_key
    settings.api_secret_key = "stream-secret"
    try:
        token = create_execution_stream_token(execution_id=999, ttl_seconds=60)
        response = client.get("/api/commands/executions/1/stream?token=" + token)
        assert response.status_code in (401, 404)
    finally:
        settings.api_secret_key = previous_secret


def test_command_execute_requires_auth(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.post("/api/commands/execute", json={"spec_id": 1})
        assert unauthorized.status_code == 401
    finally:
        settings.auth_enabled = previous_auth


def test_command_execute_rejects_container_mismatch(client):
    csrf = login_as_admin(client)
    create = client.post(
        "/api/commands/specs",
        json={
            "container_id": "abc123",
            "service_name": "api",
            "name": "Run tests",
            "argv": ["pytest", "-q"],
            "cwd": "/app",
            "env_allowlist": [],
        },
        headers={"x-csrf-token": csrf},
    )
    spec_id = create.json()["id"]
    response = client.post(
        "/api/commands/execute",
        json={"spec_id": spec_id, "container_id": "wrong-id"},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 409


def test_discover_and_allowlist_flow(client, monkeypatch):
    from app.routers import commands as commands_router

    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    monkeypatch.setattr(commands_router, "_docker_client", lambda: _FakeDockerClient())

    discover = client.post(
        "/api/commands/discover",
        json={"container_id": "abc123"},
        headers=headers,
    )
    assert discover.status_code == 200
    assert discover.json()["discovered_count"] >= 1
    assert discover.json()["cached"] is False

    listed = client.get("/api/commands/discovered?container_id=abc123")
    assert listed.status_code == 200
    discovered = listed.json()
    assert len(discovered) >= 1
    assert all(item["container_id"] == "abc123" for item in discovered)
    npm_item = next((item for item in discovered if item.get("argv", [None])[0] == "npm"), None)
    assert npm_item is not None

    allow = client.post(f"/api/commands/discovered/{npm_item['id']}/allowlist", headers=headers)
    assert allow.status_code == 200
    spec_id = allow.json()["spec_id"]
    assert spec_id > 0

    second = client.post(f"/api/commands/discovered/{npm_item['id']}/allowlist", headers=headers)
    assert second.status_code == 200
    assert second.json()["already_exists"] is True
    assert second.json()["spec_id"] == spec_id


def test_allowlist_discovered_rejects_disallowed_argv(client):
    from app.db.commands import replace_discovered_commands

    csrf = login_as_admin(client)
    replace_discovered_commands(
        container_id="abc123",
        service_name="api",
        commands=[
            {
                "name": "Unsafe shell",
                "argv": ["bash", "-c", "id"],
                "cwd": "/app",
                "source": "manual",
            }
        ],
    )
    discovered = client.get("/api/commands/discovered?container_id=abc123")
    item_id = discovered.json()[0]["id"]
    response = client.post(
        f"/api/commands/discovered/{item_id}/allowlist",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 422


def test_discover_uses_cache_when_recent(client, monkeypatch):
    from app.routers import commands as commands_router

    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    monkeypatch.setattr(commands_router, "_docker_client", lambda: _FakeDockerClient())
    first = client.post(
        "/api/commands/discover",
        json={"container_id": "abc123"},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["cached"] is False

    called = {"count": 0}

    def fail_if_called(_container):  # noqa: ANN001
        called["count"] += 1
        raise AssertionError("discover_commands should not run when cache is fresh")

    monkeypatch.setattr(commands_router, "discover_commands", fail_if_called)
    previous_ttl = settings.command_discovery_cache_ttl_seconds
    settings.command_discovery_cache_ttl_seconds = 3600
    try:
        second = client.post(
            "/api/commands/discover",
            json={"container_id": "abc123"},
            headers=headers,
        )
        assert second.status_code == 200
        payload = second.json()
        assert payload["cached"] is True
        assert payload["discovered_count"] >= 1
        assert payload["cache_age_seconds"] is not None
        assert called["count"] == 0
    finally:
        settings.command_discovery_cache_ttl_seconds = previous_ttl
