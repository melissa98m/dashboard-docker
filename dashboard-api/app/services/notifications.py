"""Notifications providers."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def send_email_notification(
    *,
    subject: str,
    message: str,
    action_url: str | None = None,
) -> bool:
    """Send an email via Resend if configured."""
    api_key = (settings.resend_api_key or "").strip()
    from_addr = (settings.alert_email_from or "").strip()
    to_raw = (settings.alert_email_to or "").strip()
    if not api_key or not from_addr or not to_raw:
        return False
    to_list = [a.strip() for a in to_raw.split(",") if a.strip()]
    if not to_list:
        return False
    body = message
    if action_url:
        body += f"\n\nRestart: {action_url}"
    try:
        import resend

        resend.api_key = api_key
        params: dict = {
            "from": from_addr,
            "to": to_list,
            "subject": subject,
            "text": body,
        }
        resend.Emails.send(params)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Resend email failed: %s", exc.__class__.__name__)
        return False


def send_ntfy_notification(
    *,
    title: str,
    message: str,
    topic: str | None = None,
    action_url: str | None = None,
) -> bool:
    """Send a basic ntfy notification if configured."""
    base_url = settings.ntfy_base_url
    target_topic = topic or settings.ntfy_topic
    if not base_url or not target_topic:
        return False
    endpoint = f"{base_url.rstrip('/')}/{target_topic}"
    headers = {
        "Title": title,
        "Tags": "warning,whale",
        "Priority": "4",
    }
    if action_url:
        headers["Actions"] = f"http, Restart, {action_url}, method=POST, clear=true"
    try:
        response = httpx.post(
            endpoint,
            content=message.encode("utf-8"),
            headers=headers,
            timeout=5.0,
        )
        return response.status_code < 300
    except httpx.HTTPError:
        return False
