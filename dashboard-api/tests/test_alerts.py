"""Alert rules endpoints tests."""

from app.db.alerts import (
    rule_exists,
    seed_default_rules_for_containers,
)
from app.db.audit import write_audit_log
from tests.conftest import login_as_admin


class _FakeAlertContainer:
    def __init__(self) -> None:
        self.short_id = "abc123"
        self.restarted = False

    def restart(self) -> None:
        self.restarted = True


class _FakeContainerManager:
    def __init__(self, container: _FakeAlertContainer) -> None:
        self._container = container

    def get(self, container_id: str) -> _FakeAlertContainer:
        if container_id != self._container.short_id:
            raise KeyError("not found")
        return self._container


class _FakeDockerClient:
    def __init__(self, container: _FakeAlertContainer) -> None:
        self.containers = _FakeContainerManager(container)


def test_alert_rule_crud(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    create_response = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "abc123",
            "container_name": "demo",
            "metric_type": "cpu_percent",
            "threshold": 80,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    rule_id = created["id"]

    list_response = client.get("/api/alerts/rules")
    assert list_response.status_code == 200
    rules = list_response.json()
    assert len(rules) == 1
    assert rules[0]["metric_type"] == "cpu_percent"

    patch_response = client.patch(
        f"/api/alerts/rules/{rule_id}",
        json={"threshold": 90, "enabled": False},
        headers=headers,
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["threshold"] == 90
    assert patched["enabled"] is False

    delete_response = client.delete(f"/api/alerts/rules/{rule_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True


def test_alert_evaluate_respects_cooldown(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    create_response = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "abc123",
            "container_name": "demo",
            "metric_type": "cpu_percent",
            "threshold": 50,
            "cooldown_seconds": 3600,
            "enabled": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    first_eval = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "abc123", "metric_type": "cpu_percent", "value": 90},
        headers=headers,
    )
    assert first_eval.status_code == 200
    first_payload = first_eval.json()["results"]
    assert first_payload[0]["triggered"] is True

    second_eval = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "abc123", "metric_type": "cpu_percent", "value": 95},
        headers=headers,
    )
    assert second_eval.status_code == 200
    second_payload = second_eval.json()["results"]
    assert second_payload[0]["triggered"] is False
    assert second_payload[0]["reason"] == "cooldown_active"


def test_alert_evaluate_respects_debounce_samples(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    create_response = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "abc123",
            "container_name": "demo",
            "metric_type": "cpu_percent",
            "threshold": 50,
            "cooldown_seconds": 300,
            "debounce_samples": 2,
            "enabled": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    first_eval = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "abc123", "metric_type": "cpu_percent", "value": 90},
        headers=headers,
    )
    assert first_eval.status_code == 200
    first_payload = first_eval.json()["results"]
    assert first_payload[0]["triggered"] is False
    assert first_payload[0]["reason"] == "debounce_pending"
    assert first_payload[0]["debounce_progress"] == 1
    assert first_payload[0]["debounce_required"] == 2

    second_eval = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "abc123", "metric_type": "cpu_percent", "value": 92},
        headers=headers,
    )
    assert second_eval.status_code == 200
    second_payload = second_eval.json()["results"]
    assert second_payload[0]["triggered"] is True
    assert second_payload[0]["reason"] == "threshold_reached"
    assert second_payload[0]["debounce_progress"] == 2
    assert second_payload[0]["debounce_required"] == 2


def test_alert_rule_restart_container_action(client, monkeypatch):
    from app.routers import alerts as alerts_router

    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    fake = _FakeAlertContainer()
    monkeypatch.setattr(alerts_router, "_get_client", lambda: _FakeDockerClient(fake))

    create_response = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "abc123",
            "container_name": "demo",
            "metric_type": "cpu_percent",
            "threshold": 80,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    rule_id = create_response.json()["id"]

    action_response = client.post(f"/api/alerts/rules/{rule_id}/restart-container", headers=headers)
    assert action_response.status_code == 200
    assert action_response.json()["ok"] is True
    assert fake.restarted is True


def test_alert_history_returns_recent_triggered_entries(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    create_response = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "abc123",
            "container_name": "demo",
            "metric_type": "cpu_percent",
            "threshold": 50,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    evaluate_response = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "abc123", "metric_type": "cpu_percent", "value": 92},
        headers=headers,
    )
    assert evaluate_response.status_code == 200
    assert evaluate_response.json()["results"][0]["triggered"] is True

    history = client.get("/api/alerts/history?limit=10")
    assert history.status_code == 200
    payload = history.json()
    assert payload["total"] >= 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert payload["sort"] == "created_at_desc"
    assert len(payload["items"]) >= 1
    entry = payload["items"][0]
    assert entry["container_id"] == "abc123"
    assert entry["container_name"] == "demo"
    assert entry["metric_type"] == "cpu_percent"
    assert entry["value"] == 92.0
    assert entry["can_restart"] is True


def test_alert_history_supports_filters_and_pagination(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    rule_a = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "aaa111",
            "container_name": "alpha",
            "metric_type": "cpu_percent",
            "threshold": 50,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    assert rule_a.status_code == 200
    rule_b = client.post(
        "/api/alerts/rules",
        json={
            "container_id": "bbb222",
            "container_name": "beta",
            "metric_type": "ram_percent",
            "threshold": 60,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    assert rule_b.status_code == 200

    eval_a = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "aaa111", "metric_type": "cpu_percent", "value": 75},
        headers=headers,
    )
    assert eval_a.status_code == 200
    eval_b = client.post(
        "/api/alerts/evaluate",
        json={"container_id": "bbb222", "metric_type": "ram_percent", "value": 90},
        headers=headers,
    )
    assert eval_b.status_code == 200

    filtered = client.get("/api/alerts/history?container_id=aaa111&metric_type=cpu_percent")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()["items"]
    assert len(filtered_payload) >= 1
    assert all(item["container_id"] == "aaa111" for item in filtered_payload)
    assert all(item["metric_type"] == "cpu_percent" for item in filtered_payload)

    page_1 = client.get("/api/alerts/history?limit=1&offset=0")
    page_2 = client.get("/api/alerts/history?limit=1&offset=1")
    assert page_1.status_code == 200
    assert page_2.status_code == 200
    assert len(page_1.json()["items"]) == 1
    assert len(page_2.json()["items"]) == 1
    assert page_1.json()["items"][0]["id"] != page_2.json()["items"][0]["id"]

    asc = client.get("/api/alerts/history?limit=2&offset=0&sort=created_at_asc")
    desc = client.get("/api/alerts/history?limit=2&offset=0&sort=created_at_desc")
    assert asc.status_code == 200
    assert desc.status_code == 200
    assert asc.json()["sort"] == "created_at_asc"
    assert desc.json()["sort"] == "created_at_desc"
    assert asc.json()["items"][0]["id"] != desc.json()["items"][0]["id"]


def test_alert_history_supports_triggered_by_filter(client):
    login_as_admin(client)
    write_audit_log(
        action="alert_triggered",
        resource_type="alert_rule",
        resource_id="1",
        triggered_by="api-key",
        details={"metric_type": "cpu_percent", "value": "80.0", "container_id": "x1"},
    )
    write_audit_log(
        action="alert_triggered_auto",
        resource_type="alert_rule",
        resource_id="2",
        triggered_by="alert-engine",
        details={"metric_type": "cpu_percent", "value": "90.0", "container_id": "x2"},
    )

    manual = client.get("/api/alerts/history?triggered_by=manual")
    assert manual.status_code == 200
    manual_items = manual.json()["items"]
    assert len(manual_items) >= 1
    assert all(item["triggered_by"] != "alert-engine" for item in manual_items)

    auto = client.get("/api/alerts/history?triggered_by=alert-engine")
    assert auto.status_code == 200
    auto_items = auto.json()["items"]
    assert len(auto_items) >= 1
    assert all(item["triggered_by"] == "alert-engine" for item in auto_items)


def test_rule_exists(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    assert rule_exists("nonexistent", "cpu_percent") is False
    client.post(
        "/api/alerts/rules",
        json={
            "container_id": "x99",
            "container_name": "test",
            "metric_type": "cpu_percent",
            "threshold": 80,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    assert rule_exists("x99", "cpu_percent") is True
    assert rule_exists("x99", "ram_percent") is False


def test_seed_default_rules_for_containers_creates_rules(client):
    login_as_admin(client)
    containers = [("c1", "app-one"), ("c2", "app-two")]
    created = seed_default_rules_for_containers(containers)
    assert created == 4  # 2 containers × 2 metrics (cpu_percent, ram_percent)

    rules = client.get("/api/alerts/rules").json()
    assert len(rules) == 4
    metrics_per_container = {}
    for r in rules:
        cid = r["container_id"]
        metrics_per_container.setdefault(cid, set()).add(r["metric_type"])
        assert r["threshold"] == 90.0
        assert r["cooldown_seconds"] == 300
        assert r["enabled"] is True
    assert metrics_per_container["c1"] == {"cpu_percent", "ram_percent"}
    assert metrics_per_container["c2"] == {"cpu_percent", "ram_percent"}


def test_seed_default_rules_for_containers_skips_existing(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}
    client.post(
        "/api/alerts/rules",
        json={
            "container_id": "existing",
            "container_name": "already-has-rule",
            "metric_type": "cpu_percent",
            "threshold": 50,
            "cooldown_seconds": 300,
            "enabled": True,
        },
        headers=headers,
    )
    containers = [("existing", "already-has-rule")]
    created = seed_default_rules_for_containers(containers)
    assert created == 1  # only ram_percent created, cpu_percent already exists
    rules = client.get("/api/alerts/rules").json()
    assert len(rules) == 2
    assert [r["metric_type"] for r in rules] == ["cpu_percent", "ram_percent"]


def test_alert_seed_run_seed_with_mock_docker(client, monkeypatch):
    login_as_admin(client)

    class FakeContainer:
        def __init__(self, short_id: str, name: str) -> None:
            self.short_id = short_id
            self.name = name

    def fake_docker_client(*args, **kwargs):
        class FakeContainers:
            def list(self):
                return [
                    FakeContainer("abc", "container-a"),
                    FakeContainer("def", "container-b"),
                ]

        class Fake:
            containers = FakeContainers()

        return Fake()

    from app.services import alert_seed

    monkeypatch.setattr(alert_seed.docker, "DockerClient", fake_docker_client)
    created = alert_seed.run_seed()
    assert created == 4
    rules = client.get("/api/alerts/rules").json()
    assert len(rules) == 4


def test_alert_seed_run_seed_docker_unavailable(client, monkeypatch):
    import docker

    def fail(*args, **kwargs):
        raise docker.errors.DockerException("Connection refused")

    from app.services import alert_seed

    monkeypatch.setattr(alert_seed.docker, "DockerClient", fail)
    created = alert_seed.run_seed()
    assert created == 0
