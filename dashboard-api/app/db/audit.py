"""Audit log persistence."""

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.init import get_db_path

_SENSITIVE_DETAIL_KEY = re.compile(
    r"(?i)(token|secret|password|passwd|pwd|api[_-]?key|authorization)"
)
_REDACTED_VALUE = "[REDACTED]"
_MAX_DETAIL_VALUE_CHARS = 500


def _sanitize_details(details: dict[str, str] | None) -> dict[str, str]:
    if not details:
        return {}
    sanitized: dict[str, str] = {}
    for key, value in details.items():
        normalized_key = str(key).strip()[:120]
        if not normalized_key:
            continue
        if _SENSITIVE_DETAIL_KEY.search(normalized_key):
            sanitized[normalized_key] = _REDACTED_VALUE
            continue
        normalized_value = str(value).strip()
        sanitized[normalized_key] = normalized_value[:_MAX_DETAIL_VALUE_CHARS]
    return sanitized


def write_audit_log(
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    triggered_by: str,
    details: dict[str, str] | None = None,
) -> None:
    """Write one audit log row."""
    payload = json.dumps(_sanitize_details(details), separators=(",", ":"))
    created_at = datetime.now(UTC).isoformat()
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_log (
                action, resource_type, resource_id, triggered_by, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, resource_type, resource_id, triggered_by, payload, created_at),
        )


def list_audit_logs(
    *,
    action: str | None = None,
    resource_type: str | None = None,
    triggered_by: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List audit logs with optional structured filters and free-text search."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    sql = """
        SELECT id, action, resource_type, resource_id, triggered_by, details, created_at
        FROM audit_log
    """
    where_clauses: list[str] = []
    params: list[Any] = []

    if action:
        where_clauses.append("action = ?")
        params.append(action.strip())
    if resource_type:
        where_clauses.append("resource_type = ?")
        params.append(resource_type.strip())
    if triggered_by:
        where_clauses.append("triggered_by = ?")
        params.append(triggered_by.strip())

    normalized_query = (query or "").strip().lower()
    if normalized_query:
        like_value = f"%{normalized_query}%"
        where_clauses.append(
            """
            (
                LOWER(action) LIKE ?
                OR LOWER(resource_type) LIKE ?
                OR LOWER(COALESCE(resource_id, '')) LIKE ?
                OR LOWER(triggered_by) LIKE ?
                OR LOWER(COALESCE(details, '')) LIKE ?
            )
            """.strip()
        )
        params.extend([like_value] * 5)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([safe_limit, safe_offset])

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, tuple(params)).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        try:
            details = json.loads(str(data.get("details") or "{}"))
        except json.JSONDecodeError:
            details = {}
        data["details"] = details
        results.append(data)
    return results


def count_audit_logs(
    *,
    action: str | None = None,
    resource_type: str | None = None,
    triggered_by: str | None = None,
    query: str | None = None,
) -> int:
    """Count audit logs matching the same filters as list_audit_logs."""
    sql = "SELECT COUNT(*) FROM audit_log"
    where_clauses: list[str] = []
    params: list[Any] = []

    if action:
        where_clauses.append("action = ?")
        params.append(action.strip())
    if resource_type:
        where_clauses.append("resource_type = ?")
        params.append(resource_type.strip())
    if triggered_by:
        where_clauses.append("triggered_by = ?")
        params.append(triggered_by.strip())

    normalized_query = (query or "").strip().lower()
    if normalized_query:
        like_value = f"%{normalized_query}%"
        where_clauses.append(
            """
            (
                LOWER(action) LIKE ?
                OR LOWER(resource_type) LIKE ?
                OR LOWER(COALESCE(resource_id, '')) LIKE ?
                OR LOWER(triggered_by) LIKE ?
                OR LOWER(COALESCE(details, '')) LIKE ?
            )
            """.strip()
        )
        params.extend([like_value] * 5)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
        return int(row[0] if row else 0)


def purge_audit_logs(*, older_than_days: int) -> int:
    """Delete audit rows older than N days and return deleted count."""
    safe_days = max(1, min(older_than_days, 3650))
    cutoff = (datetime.now(UTC) - timedelta(days=safe_days)).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        cur = conn.execute("DELETE FROM audit_log WHERE created_at < ?", (cutoff,))
        return int(cur.rowcount)


def count_purgeable_audit_logs(*, older_than_days: int) -> int:
    """Count audit rows that would be deleted by retention purge."""
    safe_days = max(1, min(older_than_days, 3650))
    cutoff = (datetime.now(UTC) - timedelta(days=safe_days)).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE created_at < ?",
            (cutoff,),
        ).fetchone()
        return int(row[0] if row else 0)
