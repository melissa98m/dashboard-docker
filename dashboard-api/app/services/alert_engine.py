"""Background engine to evaluate alert rules from Docker stats."""

import logging
import threading
from datetime import UTC, datetime
from typing import Any

import docker

from app.config import settings
from app.db.alerts import evaluate_rules
from app.db.audit import write_audit_log
from app.security import create_restart_token
from app.services.notifications import send_email_notification, send_ntfy_notification

logger = logging.getLogger(__name__)


def _docker_client() -> docker.DockerClient:
    return docker.DockerClient(base_url=settings.docker_host)


def _extract_metrics(raw: dict[str, Any]) -> dict[str, float]:
    cpu_stats = raw.get("cpu_stats", {})
    precpu = raw.get("precpu_stats", {})
    cpu_usage = cpu_stats.get("cpu_usage", {})
    pre_cpu_usage = precpu.get("cpu_usage", {})

    cpu_total = float(cpu_usage.get("total_usage", 0))
    pre_cpu_total = float(pre_cpu_usage.get("total_usage", 0))
    system_total = float(cpu_stats.get("system_cpu_usage", 0))
    pre_system_total = float(precpu.get("system_cpu_usage", 0))
    cpu_delta = cpu_total - pre_cpu_total
    system_delta = system_total - pre_system_total

    online_cpus = cpu_stats.get("online_cpus")
    percpu_usage = cpu_usage.get("percpu_usage")
    if isinstance(online_cpus, int) and online_cpus > 0:
        cpu_count = online_cpus
    elif isinstance(percpu_usage, list) and len(percpu_usage) > 0:
        cpu_count = len(percpu_usage)
    else:
        cpu_count = 1

    cpu_percent = 0.0
    if cpu_delta > 0 and system_delta > 0:
        cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0

    memory = raw.get("memory_stats", {})
    memory_usage = float(memory.get("usage", 0))
    memory_limit = float(memory.get("limit", 0))
    memory_percent = (memory_usage / memory_limit * 100.0) if memory_limit > 0 else 0.0
    memory_mb = memory_usage / (1024 * 1024)
    return {
        "cpu_percent": cpu_percent,
        "ram_mb": memory_mb,
        "ram_percent": memory_percent,
    }


def _notify_trigger(
    *,
    container_id: str,
    container_name: str,
    metric_type: str,
    value: float,
    threshold: float | None,
    topic: str | None,
) -> None:
    action_url = None
    if settings.public_api_url and settings.api_secret_key:
        try:
            token = create_restart_token(container_id=container_id)
            base = settings.public_api_url.rstrip("/")
            action_url = f"{base}/api/containers/restart-by-token?token={token}"
        except ValueError:
            action_url = None
    threshold_label = f"{threshold:.2f}" if threshold is not None else "n/a"
    msg = (
        f"{metric_type} threshold exceeded on {container_name}: "
        f"value={value:.2f}, threshold={threshold_label}"
    )
    send_ntfy_notification(
        title=f"Alert: {container_name}",
        message=msg,
        topic=topic,
        action_url=action_url,
    )
    send_email_notification(
        subject=f"Alert: {container_name}",
        message=msg,
        action_url=action_url,
    )


def run_once() -> int:
    """Run one evaluation cycle across running containers."""
    triggered_count = 0
    try:
        client = _docker_client()
        containers = client.containers.list()
    except docker.errors.DockerException:
        logger.warning("Alert engine: docker unavailable for this cycle")
        return 0

    for container in containers:
        container_id = container.short_id
        container_name = container.name
        try:
            raw = container.stats(stream=False, decode=True)
            if not isinstance(raw, dict):
                continue
            metrics = _extract_metrics(raw)
        except docker.errors.DockerException:
            logger.warning("Alert engine: unable to fetch stats for %s", container_id)
            continue

        for metric_type, value in metrics.items():
            results = evaluate_rules(
                container_id=container_id,
                metric_type=metric_type,
                value=value,
            )
            for result in results:
                if not result.get("triggered"):
                    continue
                triggered_count += 1
                rule_id = int(result["rule_id"])
                threshold = (
                    float(result["threshold"]) if result.get("threshold") is not None else None
                )
                topic = str(result["ntfy_topic"]) if result.get("ntfy_topic") is not None else None
                rule_container_name = str(result.get("container_name") or container_name)
                write_audit_log(
                    action="alert_triggered_auto",
                    resource_type="alert_rule",
                    resource_id=str(rule_id),
                    triggered_by="alert-engine",
                    details={
                        "metric_type": metric_type,
                        "value": f"{value:.2f}",
                    },
                )
                _notify_trigger(
                    container_id=container_id,
                    container_name=rule_container_name,
                    metric_type=metric_type,
                    value=value,
                    threshold=threshold,
                    topic=topic,
                )
    return triggered_count


class AlertEngine:
    """Thread-based alert evaluation engine."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_cycle_at: str | None = None
        self._last_success_at: str | None = None
        self._consecutive_errors = 0
        self._last_error_reason: str | None = None
        self._last_error_at: str | None = None

    def start(self) -> None:
        if not settings.alert_engine_enabled:
            logger.info("Alert engine disabled by configuration")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Alert engine started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("Alert engine stopped")

    def is_running(self) -> bool:
        """Return whether background thread is currently alive."""
        return bool(self._thread and self._thread.is_alive())

    def get_last_cycle_at(self) -> str | None:
        """Return ISO timestamp of last evaluation cycle."""
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
                logger.exception("Alert engine cycle failed")
                self._consecutive_errors += 1
                self._last_error_reason = exc.__class__.__name__[:80]
                self._last_error_at = datetime.now(UTC).isoformat()
            finally:
                self._last_cycle_at = datetime.now(UTC).isoformat()
            self._stop_event.wait(timeout=max(settings.alert_poll_seconds, 1))
