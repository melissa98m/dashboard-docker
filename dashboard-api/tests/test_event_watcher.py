"""Event watcher service tests."""

from app.config import settings
from app.db.audit import list_audit_logs
from app.services.event_watcher import (
    _EVENTS_OF_INTEREST,
    EventWatcherService,
    _handle_container_event,
)


def test_events_of_interest():
    assert "die" in _EVENTS_OF_INTEREST
    assert "oom" in _EVENTS_OF_INTEREST


def test_event_watcher_service_start_stop_when_disabled():
    previous = settings.event_watcher_enabled
    try:
        settings.event_watcher_enabled = False
        service = EventWatcherService()
        service.start()
        assert not service.is_running()
        service.stop()
    finally:
        settings.event_watcher_enabled = previous


def test_handle_container_event_die_triggers_audit_and_notification(
    monkeypatch,
):
    from app.services import event_watcher as ev_module

    class FakeContainer:
        name = "test-container"
        short_id = "abc12345"
        attrs = {"State": {"ExitCode": 1, "OOMKilled": False}}

        def logs(self, tail=50):
            return b"last line of log\n"

    class FakeContainers:
        def get(self, cid):
            return FakeContainer()

    class FakeClient:
        containers = FakeContainers()

    ntfy_calls = []
    email_calls = []

    def fake_ntfy(*, title, message, topic=None, action_url=None):
        ntfy_calls.append(
            {"title": title, "message": message, "topic": topic, "action_url": action_url}
        )
        return True

    def fake_email(*, subject, message, action_url=None):
        email_calls.append({"subject": subject, "message": message, "action_url": action_url})

    monkeypatch.setattr(ev_module, "_docker_client", FakeClient)
    monkeypatch.setattr(ev_module, "send_ntfy_notification", fake_ntfy)
    monkeypatch.setattr(ev_module, "send_email_notification", fake_email)

    previous_secret = settings.api_secret_key
    previous_url = settings.public_api_url
    try:
        settings.api_secret_key = "test-secret"
        settings.public_api_url = "http://localhost:8000"
        _handle_container_event(event_action="die", container_id="abc12345")
        assert len(ntfy_calls) == 1
        assert "test-container" in ntfy_calls[0]["title"]
        assert "die" in ntfy_calls[0]["message"] or "exit_code" in ntfy_calls[0]["message"]
        assert "/api/containers/restart-by-token?token=" in str(
            ntfy_calls[0].get("action_url", "")
        )
        assert len(email_calls) == 1
        assert "test-container" in email_calls[0]["subject"]
        logs = list_audit_logs(limit=5)
        audit_entries = [e for e in logs if e.get("action") == "container_die"]
        assert len(audit_entries) >= 1
    finally:
        settings.api_secret_key = previous_secret
        settings.public_api_url = previous_url


def test_handle_container_event_oom_triggers_audit(monkeypatch):
    from app.services import event_watcher as ev_module

    class FakeContainer:
        name = "oom-victim"
        short_id = "def67890"
        attrs = {"State": {"ExitCode": 137, "OOMKilled": True}}

        def logs(self, tail=50):
            return b"Killed\n"

    class FakeContainers:
        def get(self, cid):
            return FakeContainer()

    class FakeClient:
        containers = FakeContainers()

    ntfy_calls = []
    email_calls = []

    def fake_ntfy(*, title, message, topic=None, action_url=None):
        ntfy_calls.append({"title": title, "message": message})
        return True

    def fake_email(*, subject, message, action_url=None):
        email_calls.append({"subject": subject, "message": message})

    monkeypatch.setattr(ev_module, "_docker_client", FakeClient)
    monkeypatch.setattr(ev_module, "send_ntfy_notification", fake_ntfy)
    monkeypatch.setattr(ev_module, "send_email_notification", fake_email)

    _handle_container_event(event_action="oom", container_id="def67890")
    assert len(ntfy_calls) == 1
    assert "oom" in ntfy_calls[0]["message"].lower() or "oom_victim" in ntfy_calls[0]["title"]
    assert len(email_calls) == 1
    logs = list_audit_logs(limit=5)
    audit_entries = [e for e in logs if e.get("action") == "container_oom"]
    assert len(audit_entries) >= 1


def test_handle_container_event_ignores_non_die_oom():
    """Events other than die/oom are ignored (no notification, no audit)."""
    from app.services.event_watcher import _handle_container_event

    # Should return immediately without error - no Docker call
    _handle_container_event(event_action="start", container_id="xyz")
    _handle_container_event(event_action="create", container_id="xyz")
