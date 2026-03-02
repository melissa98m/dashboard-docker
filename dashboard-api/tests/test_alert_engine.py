"""Alert engine unit tests."""


def test_extract_metrics():
    from app.services.alert_engine import _extract_metrics

    payload = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200, "percpu_usage": [1, 1]},
            "system_cpu_usage": 1000,
            "online_cpus": 2,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 500,
        },
        "memory_stats": {"usage": 104857600, "limit": 209715200},
    }
    metrics = _extract_metrics(payload)
    assert metrics["cpu_percent"] > 0
    assert round(metrics["ram_mb"], 2) == 100.0
    assert round(metrics["ram_percent"], 2) == 50.0


def test_run_once_triggers_notification_and_audit(monkeypatch):
    from app.services import alert_engine
    from app.config import settings

    class FakeContainer:
        short_id = "abc123"
        name = "demo"

        def stats(self, stream: bool = False, decode: bool = True):
            return {
                "cpu_stats": {
                    "cpu_usage": {"total_usage": 200, "percpu_usage": [1, 1]},
                    "system_cpu_usage": 1000,
                    "online_cpus": 2,
                },
                "precpu_stats": {
                    "cpu_usage": {"total_usage": 100},
                    "system_cpu_usage": 500,
                },
                "memory_stats": {"usage": 104857600, "limit": 209715200},
            }

    class FakeContainerManager:
        def list(self):
            return [FakeContainer()]

    class FakeClient:
        containers = FakeContainerManager()

    monkeypatch.setattr(alert_engine, "_docker_client", lambda: FakeClient())
    monkeypatch.setattr(
        alert_engine,
        "evaluate_rules",
        lambda **kwargs: [
            {
                "rule_id": 1,
                "triggered": True,
                "threshold": 80.0,
                "container_name": "demo",
                "ntfy_topic": None,
            }
        ],
    )
    audit_calls: list[dict] = []
    notif_calls: list[dict] = []
    monkeypatch.setattr(
        alert_engine,
        "write_audit_log",
        lambda **kwargs: audit_calls.append(kwargs),
    )
    monkeypatch.setattr(
        alert_engine,
        "send_ntfy_notification",
        lambda **kwargs: notif_calls.append(kwargs) or True,
    )
    previous_public_api = settings.public_api_url
    previous_secret = settings.api_secret_key
    settings.public_api_url = "http://localhost:8000"
    settings.api_secret_key = "test-secret-key"
    try:
        triggered = alert_engine.run_once()
        assert triggered == 3
        assert len(audit_calls) == 3
        assert len(notif_calls) == 3
        assert "action_url" in notif_calls[0]
        assert notif_calls[0]["action_url"] is not None
        assert "/api/containers/restart-by-token?token=" in notif_calls[0]["action_url"]
    finally:
        settings.public_api_url = previous_public_api
        settings.api_secret_key = previous_secret
