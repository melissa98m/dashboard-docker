"""Volumes API tests."""

import docker

from tests.conftest import login_as_admin


class FakeVolume:
    def __init__(
        self,
        name: str = "my_volume",
        attrs: dict | None = None,
    ):
        self.name = name
        self.attrs = attrs or {
            "Driver": "local",
            "Mountpoint": "/var/lib/docker/volumes/my_volume/_data",
            "Labels": {},
            "CreatedAt": "2024-01-15T10:00:00Z",
            "Scope": "local",
        }

    def remove(self, force: bool = False):
        pass


class FakeVolumeManager:
    def __init__(self, volumes: list[FakeVolume] | None = None):
        self._volumes = volumes or [FakeVolume()]

    def list(self):
        return self._volumes

    def get(self, volume_name: str) -> FakeVolume:
        for v in self._volumes:
            if v.name == volume_name:
                return v
        raise docker.errors.NotFound("no such volume")


class FakeDockerClient:
    def __init__(self, volumes: list[FakeVolume] | None = None):
        self.volumes = FakeVolumeManager(volumes)
        self.containers = FakeContainerList()


class FakeContainerList:
    def list(self, all: bool = True):
        return []


def test_list_volumes(client, monkeypatch):
    from app.routers import volumes as volumes_router

    login_as_admin(client)
    monkeypatch.setattr(volumes_router, "_get_client", lambda: FakeDockerClient())
    response = client.get("/api/volumes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    item = data[0]
    assert item["name"] == "my_volume"
    assert item["driver"] == "local"


def test_get_volume_detail(client, monkeypatch):
    from app.routers import volumes as volumes_router

    login_as_admin(client)
    fake = FakeVolume(name="my_volume")
    monkeypatch.setattr(
        volumes_router, "_get_client", lambda: FakeDockerClient([fake])
    )
    response = client.get("/api/volumes/my_volume")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "my_volume"
    assert data["driver"] == "local"
    assert "containers_using" in data


def test_get_volume_detail_not_found(client, monkeypatch):
    from app.routers import volumes as volumes_router

    login_as_admin(client)
    monkeypatch.setattr(volumes_router, "_get_client", lambda: FakeDockerClient())
    response = client.get("/api/volumes/nonexistent")
    assert response.status_code == 404


def test_delete_volume(client, monkeypatch):
    from app.routers import volumes as volumes_router

    csrf = login_as_admin(client)
    fake = FakeVolume(name="my_volume")
    monkeypatch.setattr(
        volumes_router, "_get_client", lambda: FakeDockerClient([fake])
    )
    response = client.delete(
        "/api/volumes/my_volume?force=false",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
