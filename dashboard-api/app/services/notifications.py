"""Notifications providers."""

import httpx

from app.config import settings


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
