"""Alert rules storage and evaluation helpers."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.db.init import get_db_path

MetricType = str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def list_rules() -> list[dict[str, Any]]:
    with _db_connect() as conn:
        rows = conn.execute(
            """
            SELECT id, container_id, container_name, metric_type, threshold,
                   cooldown_seconds, debounce_samples, ntfy_topic, enabled, created_at, updated_at
            FROM alert_rules
            ORDER BY container_name ASC, metric_type ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def rule_exists(container_id: str, metric_type: MetricType) -> bool:
    """Check if a rule already exists for this container and metric."""
    with _db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM alert_rules WHERE container_id = ? AND metric_type = ?",
            (container_id, metric_type),
        ).fetchone()
    return row is not None


def get_rule(rule_id: int) -> dict[str, Any] | None:
    with _db_connect() as conn:
        row = conn.execute(
            """
            SELECT id, container_id, container_name, metric_type, threshold,
                   cooldown_seconds, debounce_samples, ntfy_topic, enabled, created_at, updated_at
            FROM alert_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
    return dict(row) if row else None


def create_rule(
    *,
    container_id: str,
    container_name: str,
    metric_type: MetricType,
    threshold: float,
    cooldown_seconds: int,
    debounce_samples: int,
    ntfy_topic: str | None,
    enabled: bool,
) -> dict[str, Any]:
    now = _now_iso()
    with _db_connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO alert_rules (
                container_id, container_name, metric_type, threshold,
                cooldown_seconds, debounce_samples, ntfy_topic, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                container_id,
                container_name,
                metric_type,
                threshold,
                cooldown_seconds,
                debounce_samples,
                ntfy_topic,
                1 if enabled else 0,
                now,
                now,
            ),
        )
        rule_id = int(cur.lastrowid or 0)
        row = conn.execute(
            """
            SELECT id, container_id, container_name, metric_type, threshold,
                   cooldown_seconds, debounce_samples, ntfy_topic, enabled, created_at, updated_at
            FROM alert_rules WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Failed to create alert rule")
    return dict(row)


def update_rule(rule_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    if not updates:
        with _db_connect() as conn:
            row = conn.execute(
                """
                SELECT id, container_id, container_name, metric_type, threshold,
                       cooldown_seconds, debounce_samples, ntfy_topic, enabled,
                       created_at, updated_at
                FROM alert_rules WHERE id = ?
                """,
                (rule_id,),
            ).fetchone()
        return dict(row) if row else None

    set_parts: list[str] = []
    params: list[Any] = []
    allowed = {
        "container_name",
        "threshold",
        "cooldown_seconds",
        "debounce_samples",
        "ntfy_topic",
        "enabled",
    }
    for key, value in updates.items():
        if key not in allowed:
            continue
        set_parts.append(f"{key} = ?")
        if key == "enabled":
            params.append(1 if bool(value) else 0)
        else:
            params.append(value)
    set_parts.append("updated_at = ?")
    params.append(_now_iso())
    params.append(rule_id)

    with _db_connect() as conn:
        cur = conn.execute(
            f"UPDATE alert_rules SET {', '.join(set_parts)} WHERE id = ?",
            tuple(params),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT id, container_id, container_name, metric_type, threshold,
                   cooldown_seconds, debounce_samples, ntfy_topic, enabled, created_at, updated_at
            FROM alert_rules WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_rule(rule_id: int) -> bool:
    with _db_connect() as conn:
        conn.execute("DELETE FROM alert_debounce_state WHERE alert_rule_id = ?", (rule_id,))
        conn.execute("DELETE FROM alert_cooldowns WHERE alert_rule_id = ?", (rule_id,))
        cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        return cur.rowcount > 0


DEFAULT_ESSENTIAL_RULES: list[tuple[MetricType, float]] = [
    ("cpu_percent", 90.0),
    ("ram_percent", 90.0),
]


def seed_default_rules_for_containers(
    containers: list[tuple[str, str]],
    *,
    cooldown_seconds: int = 300,
    debounce_samples: int = 1,
) -> int:
    """
    Create essential default alert rules for containers that don't have any.
    Returns the number of rules created.
    """
    created = 0
    for container_id, container_name in containers:
        for metric_type, threshold in DEFAULT_ESSENTIAL_RULES:
            if rule_exists(container_id, metric_type):
                continue
            create_rule(
                container_id=container_id,
                container_name=container_name,
                metric_type=metric_type,
                threshold=threshold,
                cooldown_seconds=cooldown_seconds,
                debounce_samples=debounce_samples,
                ntfy_topic=None,
                enabled=True,
            )
            created += 1
    return created


def evaluate_rules(
    *,
    container_id: str,
    metric_type: MetricType,
    value: float,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    with _db_connect() as conn:
        rows = conn.execute(
            """
            SELECT id, container_id, container_name, metric_type, threshold,
                   cooldown_seconds, debounce_samples, ntfy_topic, enabled, created_at, updated_at
            FROM alert_rules
            WHERE container_id = ? AND metric_type = ? AND enabled = 1
            """,
            (container_id, metric_type),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            rule = dict(row)
            threshold = float(rule["threshold"])
            debounce_samples = max(int(rule.get("debounce_samples") or 1), 1)
            breached = value >= threshold
            if not breached:
                conn.execute(
                    "DELETE FROM alert_debounce_state WHERE alert_rule_id = ?",
                    (int(rule["id"]),),
                )
                results.append(
                    {
                        "rule_id": int(rule["id"]),
                        "triggered": False,
                        "reason": "threshold_not_reached",
                        "debounce_progress": 0,
                        "debounce_required": debounce_samples,
                        "container_name": str(rule["container_name"]),
                        "threshold": float(rule["threshold"]),
                        "ntfy_topic": rule["ntfy_topic"],
                    }
                )
                continue

            latest = conn.execute(
                """
                SELECT triggered_at
                FROM alert_cooldowns
                WHERE alert_rule_id = ?
                ORDER BY triggered_at DESC
                LIMIT 1
                """,
                (int(rule["id"]),),
            ).fetchone()
            if latest is not None:
                last_dt = datetime.fromisoformat(str(latest["triggered_at"]))
                elapsed = int((now - last_dt).total_seconds())
                cooldown = int(rule["cooldown_seconds"])
                if elapsed < cooldown:
                    results.append(
                        {
                            "rule_id": int(rule["id"]),
                            "triggered": False,
                            "reason": "cooldown_active",
                            "debounce_progress": 0,
                            "debounce_required": debounce_samples,
                            "cooldown_remaining_seconds": cooldown - elapsed,
                            "container_name": str(rule["container_name"]),
                            "threshold": float(rule["threshold"]),
                            "ntfy_topic": rule["ntfy_topic"],
                        }
                    )
                    continue

            state_row = conn.execute(
                """
                SELECT consecutive_breaches
                FROM alert_debounce_state
                WHERE alert_rule_id = ?
                """,
                (int(rule["id"]),),
            ).fetchone()
            previous_breaches = (
                int(state_row["consecutive_breaches"]) if state_row is not None else 0
            )
            current_breaches = previous_breaches + 1
            conn.execute(
                """
                INSERT INTO alert_debounce_state (
                    alert_rule_id, consecutive_breaches, last_breach_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(alert_rule_id)
                DO UPDATE SET
                    consecutive_breaches = excluded.consecutive_breaches,
                    last_breach_at = excluded.last_breach_at
                """,
                (int(rule["id"]), current_breaches, now.isoformat()),
            )
            if current_breaches < debounce_samples:
                results.append(
                    {
                        "rule_id": int(rule["id"]),
                        "triggered": False,
                        "reason": "debounce_pending",
                        "debounce_progress": current_breaches,
                        "debounce_required": debounce_samples,
                        "container_name": str(rule["container_name"]),
                        "threshold": float(rule["threshold"]),
                        "ntfy_topic": rule["ntfy_topic"],
                    }
                )
                continue

            conn.execute(
                """
                INSERT INTO alert_cooldowns (alert_rule_id, triggered_at)
                VALUES (?, ?)
                """,
                (int(rule["id"]), now.isoformat()),
            )
            conn.execute(
                "DELETE FROM alert_debounce_state WHERE alert_rule_id = ?",
                (int(rule["id"]),),
            )
            results.append(
                {
                    "rule_id": int(rule["id"]),
                    "triggered": True,
                    "reason": "threshold_reached",
                    "debounce_progress": debounce_samples,
                    "debounce_required": debounce_samples,
                    "container_name": str(rule["container_name"]),
                    "threshold": float(rule["threshold"]),
                    "ntfy_topic": rule["ntfy_topic"],
                }
            )
        return results
