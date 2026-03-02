"""Background service for periodic command executions retention purge."""

import logging
import threading

from app.config import settings
from app.db.audit import write_audit_log
from app.db.commands import purge_executions

logger = logging.getLogger(__name__)


def run_once() -> int:
    """Run one retention cycle and return deleted execution rows."""
    deleted = purge_executions(older_than_days=settings.command_execution_retention_days)
    if deleted > 0:
        write_audit_log(
            action="command_executions_purge_auto",
            resource_type="executions",
            resource_id=None,
            triggered_by="command-retention-service",
            details={
                "deleted_rows": str(deleted),
                "retention_days": str(settings.command_execution_retention_days),
            },
        )
    return deleted


class CommandRetentionService:
    """Thread-based periodic purge for command executions and log files."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not settings.command_execution_retention_auto_enabled:
            logger.info("Command retention service disabled by configuration")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Command retention service started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("Command retention service stopped")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_once()
            except Exception:  # noqa: BLE001
                logger.exception("Command retention cycle failed")
            self._stop_event.wait(timeout=max(settings.command_execution_retention_poll_seconds, 10))
