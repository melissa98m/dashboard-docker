"""Audit retention background service tests."""

from datetime import UTC, datetime, timedelta
import sqlite3

from app.config import settings
from app.db.init import get_db_path
from app.services.audit_retention import run_once


def _insert_audit(action: str, created_at: str) -> None:
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO audit_log (action, resource_type, resource_id, triggered_by, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, "test", "r", "pytest", "{}", created_at),
        )


def test_audit_retention_run_once_purges_old_rows():
    old_time = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    new_time = datetime.now(UTC).isoformat()
    _insert_audit("old_row", old_time)
    _insert_audit("new_row", new_time)

    previous_days = settings.audit_retention_days
    settings.audit_retention_days = 90
    try:
        deleted = run_once()
        assert deleted >= 1
    finally:
        settings.audit_retention_days = previous_days

    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute("SELECT action FROM audit_log ORDER BY action ASC").fetchall()
        actions = [row[0] for row in rows]
    assert "old_row" not in actions
