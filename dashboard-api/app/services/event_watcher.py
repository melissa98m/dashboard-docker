"""Docker events watcher: detect container die/oom and send notifications."""

import logging
import threading

import docker

from app.config import settings
from app.db.audit import write_audit_log
from app.security import create_restart_token
from app.services.container_logs import snapshot_container_logs
from app.services.notifications import send_ntfy_notification

logger = logging.getLogger(__name__)
_EVENTS_OF_INTEREST = ("die", "oom")
_MAX_LAST_LOGS_LINES = 50
_RECONNECT_DELAY_SECONDS = 10


def _docker_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


def _safe_container_name(raw_name: str) -> str:
    if raw_name.startswith("/"):
        return raw_name[1:]
    return raw_name


def _handle_container_event(
    *,
    event_action: str,
    container_id: str,
) -> None:
    """Process a die/oom event: fetch logs, audit, notify."""
    if event_action not in _EVENTS_OF_INTEREST:
        return

    client = _docker_client()
    container_name = container_id[:12]
    reason = event_action
    logs_preview = ""

    try:
        container = client.containers.get(container_id)
        container_name = _safe_container_name(container.name)
        state = container.attrs.get("State", {})

        if event_action == "oom":
            reason = "oom_killed"
        elif event_action == "die":
            exit_code = state.get("ExitCode")
            if state.get("OOMKilled") is True:
                reason = "oom_killed"
            elif isinstance(exit_code, int):
                reason = f"exit_code_{exit_code}"
            else:
                reason = "exited"

        try:
            lines = snapshot_container_logs(container, tail=_MAX_LAST_LOGS_LINES)
            logs_preview = "\n".join(lines[-10:]) if lines else ""
        except docker.errors.DockerException:
            logs_preview = "(logs unavailable)"

    except docker.errors.NotFound:
        container_name = container_id[:12]
        logs_preview = "(container already removed)"
    except docker.errors.DockerException as exc:
        logger.warning("Event watcher: unable to inspect %s: %s", container_id, exc)
        return

    write_audit_log(
        action=f"container_{event_action}",
        resource_type="container",
        resource_id=container_id,
        triggered_by="event-watcher",
        details={"reason": reason, "container_name": container_name},
    )

    title = f"Container down: {container_name}"
    message = f"{container_name} ({reason})"
    if logs_preview:
        message += f"\n\nLast logs:\n{logs_preview[:1500]}"
        if len(logs_preview) > 1500:
            message += "\n..."

    action_url = None
    if settings.public_api_url and settings.api_secret_key:
        try:
            token = create_restart_token(container_id=container_id)
            base = settings.public_api_url.rstrip("/")
            action_url = f"{base}/api/containers/restart-by-token?token={token}"
        except ValueError:
            pass

    topic = settings.event_watcher_ntfy_topic or settings.ntfy_topic
    sent = send_ntfy_notification(
        title=title,
        message=message,
        topic=topic,
        action_url=action_url,
    )
    if not sent:
        logger.debug("ntfy notification skipped for container %s", container_id)


def _events_loop(stop_event: threading.Event) -> None:
    """Main loop: stream Docker events and process die/oom."""
    while not stop_event.is_set():
        try:
            client = _docker_client()
            events = client.events(
                decode=True,
                filters={"type": ["container"], "event": list(_EVENTS_OF_INTEREST)},
            )
            for event in events:
                if stop_event.is_set():
                    break
                if not isinstance(event, dict):
                    continue
                action = event.get("Action") or event.get("status")
                actor = event.get("Actor") or {}
                container_id = event.get("id") or actor.get("ID")
                if action in _EVENTS_OF_INTEREST and container_id:
                    try:
                        _handle_container_event(
                            event_action=action,
                            container_id=str(container_id),
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Event watcher: error handling %s for %s",
                            action,
                            container_id,
                        )
        except docker.errors.DockerException as exc:
            logger.warning("Event watcher: Docker unavailable, reconnecting: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("Event watcher: unexpected error")
        if not stop_event.is_set():
            stop_event.wait(timeout=_RECONNECT_DELAY_SECONDS)


class EventWatcherService:
    """Background service that listens to Docker container die/oom events."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not settings.event_watcher_enabled:
            logger.info("Event watcher disabled by configuration")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=_events_loop, args=(self._stop_event,), daemon=True)
        self._thread.start()
        logger.info("Event watcher started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        logger.info("Event watcher stopped")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
