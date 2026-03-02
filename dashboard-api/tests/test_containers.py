"""Container endpoints tests."""

import docker

from app.config import settings
from app.security import create_restart_token
from tests.conftest import login_as_admin


class FakeImage:
    tags = ["demo:latest"]
    short_id = "sha256:abc"


class MissingImage:
    @property
    def tags(self):  # noqa: ANN201
        raise docker.errors.ImageNotFound("missing image")

    @property
    def short_id(self):  # noqa: ANN201
        raise docker.errors.ImageNotFound("missing image")


class FakeContainer:
    def __init__(self) -> None:
        self.short_id = "abc123"
        self.name = "demo"
        self.image = FakeImage()
        self.attrs = {
            "State": {
                "Status": "running",
                "StartedAt": "2026-01-01T00:00:00Z",
                "FinishedAt": "0001-01-01T00:00:00Z",
                "ExitCode": 0,
                "OOMKilled": False,
                "Error": "",
                "Health": {"Status": "healthy"},
            }
        }
        self.started = False
        self.restarted = False
        self.removed = False
        self.remove_args: dict[str, bool] | None = None

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        return None

    def restart(self) -> None:
        self.restarted = True

    def remove(self, *, v: bool = False, force: bool = False) -> None:
        self.removed = True
        self.remove_args = {"v": v, "force": force}

    def logs(self, tail: int = 100) -> bytes:
        return f"log-1\nlog-2\nlast-{tail}".encode("utf-8")

    def stats(self, stream: bool = True, decode: bool = True):
        if stream and decode:
            yield {
                "cpu_stats": {
                    "cpu_usage": {"total_usage": 200, "percpu_usage": [1, 1]},
                    "system_cpu_usage": 1000,
                    "online_cpus": 2,
                },
                "precpu_stats": {
                    "cpu_usage": {"total_usage": 100},
                    "system_cpu_usage": 500,
                },
                "memory_stats": {
                    "usage": 104857600,
                    "limit": 209715200,
                },
            }
            return
        raise RuntimeError("unexpected stats mode")

    def stream_logs(self, tail: int = 100):
        yield b"line-a\n"
        yield b"line-b\n"


class FakeContainerManager:
    def __init__(self, container: FakeContainer) -> None:
        self._container = container

    def list(self, all: bool = True):  # noqa: A002
        return [self._container]

    def get(self, container_id: str) -> FakeContainer:
        if container_id != self._container.short_id:
            raise docker.errors.NotFound("no such container")
        return self._container


class FakeDockerClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainerManager(container)


def test_list_containers(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    response = client.get("/api/containers")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "demo"
    assert payload[0]["status"] == "running"
    assert payload[0]["last_down_reason"] is None
    assert payload[0]["finished_at"] is None


def test_list_containers_with_missing_image_metadata(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    fake.image = MissingImage()
    fake.attrs["Config"] = {"Image": "dashboard-web:local"}
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )

    response = client.get("/api/containers")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["image"] == "dashboard-web:local"


def test_get_container_detail(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    response = client.get("/api/containers/abc123?tail=10")
    assert response.status_code == 200
    data = response.json()
    assert data["health_status"] == "healthy"
    assert data["oom_killed"] is False
    assert data["last_logs"][-1] == "last-10"
    assert data["last_down_reason"] is None
    assert data["finished_at"] is None


def test_get_container_detail_down_reason_and_finished_at(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    fake.attrs["State"]["Status"] = "exited"
    fake.attrs["State"]["ExitCode"] = 137
    fake.attrs["State"]["OOMKilled"] = True
    fake.attrs["State"]["Error"] = "process killed by kernel"
    fake.attrs["State"]["FinishedAt"] = "2026-02-10T12:00:00Z"
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    response = client.get("/api/containers/abc123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "exited"
    assert data["finished_at"] == "2026-02-10T12:00:00Z"
    # OOMKilled has priority over generic error/exit code.
    assert data["last_down_reason"] == "oom_killed"


def test_get_container_detail_redacts_snapshot_sensitive_values(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    fake.logs = lambda tail=100: (  # type: ignore[assignment]
        b"user=alice email=alice@example.com password=supersecret token=abc123\n"
        b"Authorization: Bearer very-secret-token\n"
    )
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )

    previous = settings.log_snapshot_redaction_enabled
    settings.log_snapshot_redaction_enabled = True
    try:
        response = client.get("/api/containers/abc123?tail=10")
        assert response.status_code == 200
        lines = response.json()["last_logs"]
        joined = "\n".join(lines)
        assert "alice@example.com" not in joined
        assert "supersecret" not in joined
        assert "abc123" not in joined
        assert "very-secret-token" not in joined
        assert "[EMAIL_REDACTED]" in joined
        assert "[REDACTED]" in joined
    finally:
        settings.log_snapshot_redaction_enabled = previous


def test_get_container_detail_snapshot_redaction_can_be_disabled(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    fake.logs = lambda tail=100: b"password=s3cret email=bob@example.com\n"  # type: ignore[assignment]
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )

    previous = settings.log_snapshot_redaction_enabled
    settings.log_snapshot_redaction_enabled = False
    try:
        response = client.get("/api/containers/abc123?tail=10")
        assert response.status_code == 200
        line = response.json()["last_logs"][0]
        assert "password=s3cret" in line
        assert "bob@example.com" in line
    finally:
        settings.log_snapshot_redaction_enabled = previous


def test_write_action_requires_auth_and_csrf(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.post("/api/containers/abc123/start")
        assert unauthorized.status_code == 401

        csrf = login_as_admin(client)
        authorized = client.post(
            "/api/containers/abc123/start",
            headers={"x-csrf-token": csrf},
        )
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth


def test_container_start_failure_is_audited(client, monkeypatch):
    from app.routers import containers as containers_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    response = client.post(
        "/api/containers/missing/start",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 404

    logs = client.get("/api/audit/logs?action=container_start")
    assert logs.status_code == 200
    entries = logs.json()
    assert len(entries) >= 1
    latest = entries[0]
    assert latest["details"]["result"] == "error"
    assert latest["details"]["reason"] == "not_found"


def test_write_action_returns_503_when_auth_disabled(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = False
        response = client.post("/api/containers/abc123/start")
        assert response.status_code == 503
        assert response.json()["detail"] == "Authentication is disabled"
    finally:
        settings.auth_enabled = previous_auth


def test_delete_container_safe_mode(client, monkeypatch):
    from app.routers import containers as containers_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    response = client.delete(
        "/api/containers/abc123?force=false&volumes=false",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert fake.removed is True
    assert fake.remove_args == {"v": False, "force": False}


def test_stats_sse(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    response = client.get("/api/containers/abc123/stats?max_events=1")
    assert response.status_code == 200
    assert "event: stats" in response.text
    assert '"cpu_percent"' in response.text


def test_logs_sse(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )

    def fake_logs(*, stream: bool = False, follow: bool = False, tail: int = 100):
        if stream and follow:
            yield b"line-a\n"
            yield b"line-b\n"
            return
        return fake.logs(tail=tail)

    fake.logs = fake_logs  # type: ignore[assignment]
    response = client.get("/api/containers/abc123/logs?tail=20&max_events=1")
    assert response.status_code == 200
    assert "event: log" in response.text
    assert "line-a" in response.text


def test_read_action_requires_auth(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.get("/api/containers/abc123")
        assert unauthorized.status_code == 401
        login_as_admin(client)
        authorized = client.get("/api/containers/abc123")
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth


def test_sse_limit_returns_429(client, monkeypatch):
    from app.routers import containers as containers_router

    login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )

    class RejectingSemaphore:
        def acquire(self, blocking: bool = False) -> bool:
            return False

    monkeypatch.setattr(containers_router, "_SSE_SEMAPHORE", RejectingSemaphore())
    response = client.get("/api/containers/abc123/stats")
    assert response.status_code == 429


def test_restart_by_token_success_and_one_time(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    previous_secret = settings.api_secret_key
    settings.api_secret_key = "test-secret-key"
    try:
        token = create_restart_token(container_id="abc123", ttl_seconds=60)
        first = client.post("/api/containers/restart-by-token", json={"token": token})
        assert first.status_code == 200
        assert fake.restarted is True

        second = client.post("/api/containers/restart-by-token", json={"token": token})
        assert second.status_code == 409
    finally:
        settings.api_secret_key = previous_secret


def test_restart_by_token_expired(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    previous_secret = settings.api_secret_key
    settings.api_secret_key = "test-secret-key"
    try:
        token = create_restart_token(container_id="abc123", ttl_seconds=-1)
        response = client.post("/api/containers/restart-by-token", json={"token": token})
        assert response.status_code == 401
    finally:
        settings.api_secret_key = previous_secret


def test_restart_by_token_query_post(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    previous_secret = settings.api_secret_key
    settings.api_secret_key = "test-secret-key"
    try:
        token = create_restart_token(container_id="abc123", ttl_seconds=60)
        response = client.post(f"/api/containers/restart-by-token?token={token}")
        assert response.status_code == 200
    finally:
        settings.api_secret_key = previous_secret


def test_restart_by_token_rate_limit(client, monkeypatch):
    from app.routers import containers as containers_router

    fake = FakeContainer()
    monkeypatch.setattr(
        containers_router,
        "_get_client",
        lambda: FakeDockerClient(fake),
    )
    monkeypatch.setattr(containers_router, "_TOKEN_RATE_LIMIT_ATTEMPTS", {})

    previous_secret = settings.api_secret_key
    previous_window = settings.restart_token_rate_limit_window_seconds
    previous_max = settings.restart_token_rate_limit_max_attempts
    settings.api_secret_key = "test-secret-key"
    settings.restart_token_rate_limit_window_seconds = 60
    settings.restart_token_rate_limit_max_attempts = 1
    try:
        first = client.post("/api/containers/restart-by-token", json={"token": "invalid.token"})
        assert first.status_code == 401
        second = client.post("/api/containers/restart-by-token", json={"token": "invalid.token"})
        assert second.status_code == 429
    finally:
        settings.api_secret_key = previous_secret
        settings.restart_token_rate_limit_window_seconds = previous_window
        settings.restart_token_rate_limit_max_attempts = previous_max


def test_container_commands_scoped_endpoints_filter_by_container(client):
    from app.db.commands import complete_execution, create_execution, replace_discovered_commands

    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}

    first_spec = client.post(
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
    assert first_spec.status_code == 200
    second_spec = client.post(
        "/api/commands/specs",
        json={
            "container_id": "def456",
            "service_name": "worker",
            "name": "Run worker checks",
            "argv": ["python", "-m", "pytest"],
            "cwd": "/srv",
            "env_allowlist": [],
        },
        headers=headers,
    )
    assert second_spec.status_code == 200

    replace_discovered_commands(
        container_id="abc123",
        service_name="api",
        commands=[{"name": "npm test", "argv": ["npm", "test"], "cwd": "/app", "source": "npm"}],
    )
    replace_discovered_commands(
        container_id="def456",
        service_name="worker",
        commands=[
            {"name": "python -m pytest", "argv": ["python", "-m", "pytest"], "cwd": "/srv", "source": "poetry"}
        ],
    )

    exec_first = create_execution(
        command_spec_id=int(first_spec.json()["id"]),
        container_id="abc123",
        triggered_by="tests",
        stdout_path="/tmp/stdout-1.log",
        stderr_path="/tmp/stderr-1.log",
    )
    complete_execution(execution_id=exec_first, exit_code=0)
    exec_second = create_execution(
        command_spec_id=int(second_spec.json()["id"]),
        container_id="def456",
        triggered_by="tests",
        stdout_path="/tmp/stdout-2.log",
        stderr_path="/tmp/stderr-2.log",
    )
    complete_execution(execution_id=exec_second, exit_code=1)

    specs_response = client.get("/api/containers/abc123/commands/specs")
    assert specs_response.status_code == 200
    specs_payload = specs_response.json()
    assert len(specs_payload) == 1
    assert specs_payload[0]["container_id"] == "abc123"

    discovered_response = client.get("/api/containers/abc123/commands/discovered")
    assert discovered_response.status_code == 200
    discovered_payload = discovered_response.json()
    assert len(discovered_payload) == 1
    assert discovered_payload[0]["container_id"] == "abc123"

    executions_response = client.get("/api/containers/abc123/commands/executions")
    assert executions_response.status_code == 200
    executions_payload = executions_response.json()
    assert len(executions_payload) == 1
    assert executions_payload[0]["container_id"] == "abc123"


def test_container_commands_scoped_endpoints_require_auth(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.get("/api/containers/abc123/commands/specs")
        assert unauthorized.status_code == 401

        login_as_admin(client)
        authorized = client.get("/api/containers/abc123/commands/specs")
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth
