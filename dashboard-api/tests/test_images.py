"""Images API tests."""

import docker

from tests.conftest import login_as_admin


class FakeImage:
    def __init__(self, short_id: str = "sha256:abc123", tags: list | None = None):
        self.short_id = short_id
        self.id = short_id
        self.tags = tags or ["nginx:latest"]
        self.attrs = {
            "Created": "2024-01-15T10:00:00Z",
            "Size": 150_000_000,
            "Architecture": "amd64",
            "Os": "linux",
            "Parent": "",
            "Config": {"Labels": {"com.example": "test"}},
        }


class FakeImageManager:
    def __init__(self, images: list[FakeImage] | None = None):
        self._images = images or [FakeImage()]

    def list(self, all: bool = False, filters: dict | None = None):
        return self._images

    def get(self, image_id: str) -> FakeImage:
        for img in self._images:
            if img.short_id == image_id or image_id in img.short_id:
                return img
        raise docker.errors.ImageNotFound("image not found")

    def remove(self, image: str, force: bool = False):
        for img in self._images:
            if img.short_id == image or image in img.short_id:
                return
        raise docker.errors.ImageNotFound("image not found")


class FakeDockerClient:
    def __init__(self, images: list[FakeImage] | None = None):
        self.images = FakeImageManager(images)


def test_list_images(client, monkeypatch):
    from app.routers import images as images_router

    login_as_admin(client)
    monkeypatch.setattr(images_router, "_get_client", lambda: FakeDockerClient())
    response = client.get("/api/images")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    item = data[0]
    assert "id" in item
    assert "tags" in item
    assert "display_name" in item
    assert "size" in item
    assert "size_human" in item


def test_get_image_detail(client, monkeypatch):
    from app.routers import images as images_router

    login_as_admin(client)
    fake = FakeImage(short_id="sha256:abc123")
    monkeypatch.setattr(images_router, "_get_client", lambda: FakeDockerClient([fake]))
    response = client.get("/api/images/sha256:abc123")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "sha256:abc123"
    assert "nginx:latest" in data["tags"]
    assert data["architecture"] == "amd64"


def test_get_image_detail_not_found(client, monkeypatch):
    from app.routers import images as images_router

    login_as_admin(client)
    monkeypatch.setattr(images_router, "_get_client", lambda: FakeDockerClient())
    response = client.get("/api/images/nonexistent")
    assert response.status_code == 404


def test_delete_image(client, monkeypatch):
    from app.routers import images as images_router

    csrf = login_as_admin(client)
    fake = FakeImage(short_id="sha256:abc123")
    monkeypatch.setattr(images_router, "_get_client", lambda: FakeDockerClient([fake]))
    response = client.delete(
        "/api/images/sha256:abc123?force=false",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
