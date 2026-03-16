"""Notifications service tests."""

from app.config import settings
from app.services import notifications as notifications_module
from app.services.notifications import send_email_notification, send_ntfy_notification


def test_send_email_returns_false_when_not_configured():
    previous_key = settings.resend_api_key
    previous_from = settings.alert_email_from
    previous_to = settings.alert_email_to
    try:
        settings.resend_api_key = ""
        settings.alert_email_from = ""
        settings.alert_email_to = ""
        assert send_email_notification(subject="Test", message="Body") is False
    finally:
        settings.resend_api_key = previous_key
        settings.alert_email_from = previous_from
        settings.alert_email_to = previous_to


def test_send_email_calls_resend_when_configured(monkeypatch):
    import sys

    sent_params: list[dict] = []

    def fake_send(params):
        sent_params.append(params)
        return {"id": "test-id"}

    class FakeEmails:
        send = staticmethod(fake_send)

    class FakeResendModule:
        api_key = None
        Emails = FakeEmails

    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(settings, "alert_email_from", "a@b.com")
    monkeypatch.setattr(settings, "alert_email_to", "c@d.com")
    prev_resend = sys.modules.get("resend")
    sys.modules["resend"] = FakeResendModule
    try:
        result = send_email_notification(
            subject="Alert: x",
            message="CPU high",
            action_url="https://example.com/restart",
        )
        assert result is True
        assert len(sent_params) == 1
        assert sent_params[0]["subject"] == "Alert: x"
        assert "CPU high" in sent_params[0]["text"]
        assert "Restart: https://example.com/restart" in sent_params[0]["text"]
    finally:
        if prev_resend is not None:
            sys.modules["resend"] = prev_resend
        else:
            sys.modules.pop("resend", None)


def test_send_ntfy_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "ntfy_base_url", None)
    monkeypatch.setattr(settings, "ntfy_topic", None)

    assert send_ntfy_notification(title="Alert", message="Body") is False


def test_send_ntfy_posts_expected_payload_and_action(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

    def fake_post(url, *, content, headers, timeout):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(settings, "ntfy_base_url", "https://ntfy.example.com/")
    monkeypatch.setattr(settings, "ntfy_topic", "default-topic")
    monkeypatch.setattr(notifications_module.httpx, "post", fake_post)

    assert (
        send_ntfy_notification(
            title="CPU high",
            message="Usage above threshold",
            topic="custom-topic",
            action_url="https://dashboard.example.com/restart",
        )
        is True
    )
    assert captured["url"] == "https://ntfy.example.com/custom-topic"
    assert captured["content"] == b"Usage above threshold"
    assert captured["timeout"] == 5.0
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Title"] == "CPU high"
    assert headers["Priority"] == "4"
    assert "https://dashboard.example.com/restart" in headers["Actions"]


def test_send_ntfy_returns_false_on_http_error(monkeypatch):
    def fake_post(*args, **kwargs):
        _ = (args, kwargs)
        raise notifications_module.httpx.HTTPError("boom")

    monkeypatch.setattr(settings, "ntfy_base_url", "https://ntfy.example.com")
    monkeypatch.setattr(settings, "ntfy_topic", "dashboard")
    monkeypatch.setattr(notifications_module.httpx, "post", fake_post)

    assert send_ntfy_notification(title="Alert", message="Body") is False
