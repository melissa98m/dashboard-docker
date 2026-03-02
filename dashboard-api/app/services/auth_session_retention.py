"""Background service for periodic auth session retention purge."""

import logging
import threading

from app.config import settings
from app.db.audit import write_audit_log
from app.db.auth import purge_expired_sessions

logger = logging.getLogger(__name__)


def run_once() -> int:
    """Run one retention cycle and return deleted session rows."""
    deleted = purge_expired_sessions()
    if deleted > 0:
        write_audit_log(
            action="auth_sessions_purge_auto",
            resource_type="auth_sessions",
            resource_id=None,
            triggered_by="auth-session-retention-service",
            details={"deleted_rows": str(deleted)},
        )
    return deleted


class AuthSessionRetentionService:
    """Thread-based periodic purge for authentication sessions."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not settings.auth_session_retention_auto_enabled:
            logger.info("Auth session retention service disabled by configuration")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Auth session retention service started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("Auth session retention service stopped")

    def is_running(self) -> bool:
        """Return whether background thread is currently alive."""
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_once()
            except Exception:  # noqa: BLE001
                logger.exception("Auth session retention cycle failed")
            self._stop_event.wait(timeout=max(settings.auth_session_retention_poll_seconds, 10))
