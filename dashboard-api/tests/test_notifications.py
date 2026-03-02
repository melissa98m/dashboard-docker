"""Notifications service tests."""

from app.config import settings
from app.services.notifications import send_email_notification


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
