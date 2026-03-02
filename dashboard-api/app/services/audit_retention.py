"""Background service for periodic audit logs retention purge."""

import logging
import threading
from datetime import UTC, datetime

from app.config import settings
from app.db.audit import purge_audit_logs, write_audit_log

logger = logging.getLogger(__name__)


def run_once() -> int:
    """Run one retention cycle and return deleted rows."""
    deleted = purge_audit_logs(older_than_days=settings.audit_retention_days)
    if deleted > 0:
        write_audit_log(
            action="audit_purge_auto",
            resource_type="audit_log",
            resource_id=None,
            triggered_by="audit-retention-service",
            details={
                "deleted_rows": str(deleted),
                "retention_days": str(settings.audit_retention_days),
            },
        )
    return deleted


class AuditRetentionService:
    """Thread-based periodic purge for audit logs."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cycle_at: str | None = None
        self._last_success_at: str | None = None
        self._consecutive_errors = 0
        self._last_error_reason: str | None = None
        self._last_error_at: str | None = None

    def start(self) -> None:
        if not settings.audit_retention_auto_enabled:
            logger.info("Audit retention service disabled by configuration")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Audit retention service started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("Audit retention service stopped")

    def is_running(self) -> bool:
        """Return whether background thread is currently alive."""
        return bool(self._thread and self._thread.is_alive())

    def get_last_cycle_at(self) -> str | None:
        """Return ISO timestamp of last retention cycle."""
        return self._last_cycle_at

    def get_last_success_at(self) -> str | None:
        """Return ISO timestamp of last successful cycle."""
        return self._last_success_at

    def get_consecutive_errors(self) -> int:
        """Return count of consecutive failed cycles."""
        return self._consecutive_errors

    def get_last_error_reason(self) -> str | None:
        """Return non-sensitive last cycle error reason."""
        return self._last_error_reason

    def get_last_error_at(self) -> str | None:
        """Return ISO timestamp of last failed cycle."""
        return self._last_error_at

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_once()
                self._last_success_at = datetime.now(UTC).isoformat()
                self._consecutive_errors = 0
                self._last_error_reason = None
            except Exception as exc:  # noqa: BLE001
                logger.exception("Audit retention cycle failed")
                self._consecutive_errors += 1
                self._last_error_reason = exc.__class__.__name__[:80]
                self._last_error_at = datetime.now(UTC).isoformat()
            finally:
                self._last_cycle_at = datetime.now(UTC).isoformat()
            self._stop_event.wait(timeout=max(settings.audit_retention_poll_seconds, 10))
