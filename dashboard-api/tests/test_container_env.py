"""Container env API tests."""

import pytest

from app.config import settings
from app.services.container_env import (
    detect_env_file,
    merge_env,
    parse_env_file,
    write_env_file_atomic,
)
from tests.conftest import login_as_admin


class FakeContainer:
    def __init__(self) -> None:
        self.short_id = "abc123"
        self.name = "demo-service"
        self.attrs = {
            "Config": {
                "Env": ["FOO=bar", "SECRET_TOKEN=abcd"],
                "Image": "demo:latest",
                "Cmd": ["python", "app.py"],
                "Labels": {},
            },
            "HostConfig": {
                "Binds": None,
                "PortBindings": None,
                "RestartPolicy": {},
                "NetworkMode": "default",
                "Privileged": False,
                "CapAdd": None,
                "CapDrop": None,
                "ExtraHosts": None,
            },
            "Mounts": [],
        }

    def stop(self) -> None:
        return None

    def start(self) -> None:
        return None

    def rename(self, _name: str) -> None:
        return None

    def remove(self, *, v: bool = False, force: bool = False) -> None:
        _ = (v, force)
        return None


class FakeContainerManager:
    def __init__(self, container: FakeContainer) -> None:
        self._container = container

    def get(self, container_id: str):
        if container_id in {self._container.short_id, "new-container-id"}:
            if container_id == "new-container-id":
                new_container = FakeContainer()
                new_container.short_id = "new-container-id"
                new_container.name = "demo-service-new"
                return new_container
            return self._container
        raise KeyError("not found")


class FakeDockerApi:
    def create_host_config(self, **kwargs):
        return kwargs

    def create_container(self, **kwargs):
        _ = kwargs
        return {"Id": "new-container-id"}

    def start(self, _container_id: str) -> None:
        return None


class FakeDockerClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainerManager(container)
        self.api = FakeDockerApi()


def test_parse_env_file_supports_quotes_comments_and_empty_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# ignored comment\n"
        "FOO=bar\n"
        'QUOTED="value with spaces"\n'
        "SINGLE='value'\n"
        "EMPTY=\n"
        "INVALID_LINE\n",
        encoding="utf-8",
    )

    assert parse_env_file(env_file) == {
        "FOO": "bar",
        "QUOTED": "value with spaces",
        "SINGLE": "value",
        "EMPTY": "",
    }


def test_write_env_file_atomic_sorts_keys_and_ends_with_newline(tmp_path):
    env_file = tmp_path / ".env"

    write_env_file_atomic(env_file, {"ZETA": "last", "ALPHA": "first"})

    assert env_file.read_text(encoding="utf-8") == "ALPHA=first\nZETA=last\n"


def test_detect_env_file_deduplicates_candidates_and_returns_existing_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\n", encoding="utf-8")
    container = type(
        "ContainerStub",
        (),
        {
            "attrs": {
                "Config": {
                    "Labels": {
                        "com.docker.compose.project.working_dir": str(tmp_path),
                    }
                },
                "Mounts": [
                    {
                        "Source": str(tmp_path),
                        "Destination": "/app",
                    }
                ],
            }
        },
    )()

    path, writable, candidates = detect_env_file(container)

    assert path == str(env_file)
    assert writable is True
    assert candidates == [str(env_file)]


def test_merge_env_replace_mode_discards_current_and_rejects_multiline_values():
    merged = merge_env(
        current={"OLD": "1", "KEEP": "x"},
        updates={"NEW_VALUE": "2"},
        unset=["KEEP"],
        mode="replace",
    )

    assert merged == {"NEW_VALUE": "2"}

    with pytest.raises(ValueError, match="Multiline env values"):
        merge_env(
            current={},
            updates={"BROKEN": "line1\nline2"},
            unset=[],
            mode="merge",
        )


def test_get_env_profile_uses_runtime_env(client, monkeypatch):
    from app.routers import container_env as env_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    response = client.get(
        "/api/containers/abc123/env/profile",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_mode"] == "db_fallback"
    keys = {item["key"]: item for item in payload["env"]}
    assert keys["FOO"]["value"] == "bar"
    assert keys["SECRET_TOKEN"]["sensitive"] is True


def test_update_env_profile_merge_and_unset(client, monkeypatch):
    from app.routers import container_env as env_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    response = client.put(
        "/api/containers/abc123/env/profile",
        json={
            "mode": "merge",
            "set": {"FOO": "updated", "NEW_VAR": "1"},
            "unset": ["SECRET_TOKEN"],
        },
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_apply"] is True
    keys = {item["key"]: item for item in payload["env"]}
    assert keys["FOO"]["value"] == "updated"
    assert keys["NEW_VAR"]["value"] == "1"
    assert "SECRET_TOKEN" not in keys


def test_update_env_profile_rejects_invalid_key(client, monkeypatch):
    from app.routers import container_env as env_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    response = client.put(
        "/api/containers/abc123/env/profile",
        json={"mode": "merge", "set": {"BAD-KEY": "x"}, "unset": []},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 422
    assert "Invalid env key" in response.json()["detail"]


def test_update_env_profile_writes_detected_env_file(client, monkeypatch, tmp_path):
    from app.routers import container_env as env_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=from-file\n", encoding="utf-8")
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    monkeypatch.setattr(
        env_router,
        "detect_env_file",
        lambda _container: (str(env_file), True, [str(env_file)]),
    )
    response = client.put(
        "/api/containers/abc123/env/profile",
        json={"mode": "merge", "set": {"FOO": "new"}, "unset": []},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    assert "FOO=new" in env_file.read_text(encoding="utf-8")


def test_apply_env_profile_dry_run(client, monkeypatch):
    from app.routers import container_env as env_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    save_response = client.put(
        "/api/containers/abc123/env/profile",
        json={"mode": "merge", "set": {"FOO": "after"}, "unset": []},
        headers={"x-csrf-token": csrf},
    )
    assert save_response.status_code == 200
    response = client.post(
        "/api/containers/abc123/env/apply",
        json={"dry_run": True},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["strategy"] == "recreate"


def test_apply_env_profile_recreate_success(client, monkeypatch):
    from app.routers import container_env as env_router

    csrf = login_as_admin(client)
    fake = FakeContainer()
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    monkeypatch.setattr(
        env_router,
        "recreate_container_with_env",
        lambda **_kwargs: ("new-container-id", []),
    )
    save_response = client.put(
        "/api/containers/abc123/env/profile",
        json={"mode": "merge", "set": {"FOO": "after"}, "unset": []},
        headers={"x-csrf-token": csrf},
    )
    assert save_response.status_code == 200
    response = client.post(
        "/api/containers/abc123/env/apply",
        json={"dry_run": False},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["new_container_id"] == "new-container-id"


def test_env_profile_requires_auth(client, monkeypatch):
    from app.routers import container_env as env_router

    fake = FakeContainer()
    monkeypatch.setattr(env_router, "_docker_client", lambda: FakeDockerClient(fake))
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.get("/api/containers/abc123/env/profile")
        assert unauthorized.status_code == 401
        csrf = login_as_admin(client)
        authorized = client.get(
            "/api/containers/abc123/env/profile",
            headers={"x-csrf-token": csrf},
        )
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth
