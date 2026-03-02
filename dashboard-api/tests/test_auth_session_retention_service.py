"""Auth session retention background service tests."""

import sqlite3
from datetime import UTC, datetime, timedelta

from app.db.init import get_db_path
from app.services.auth_session_retention import run_once


def _insert_user() -> int:
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO users (
                username, password_hash, role, failed_login_attempts, locked_until,
                last_login_at, created_at, updated_at
            ) VALUES (?, ?, ?, 0, NULL, NULL, ?, ?)
            """,
            ("retention-user", "pbkdf2_sha256$1$AA==$AA==", "admin", now, now),
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_session(
    *,
    user_id: int,
    expires_at: str,
    revoked_at: str | None,
    session_token_hash: str | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    hash_val = session_token_hash or f"hash-{user_id}-{expires_at}-{revoked_at or 'active'}"
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (
                user_id, session_token_hash, csrf_token,
                created_at, expires_at, last_seen_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, hash_val, "csrf-token", now, expires_at, now, revoked_at),
        )


def test_auth_session_retention_run_once_purges_expired_and_revoked():
    user_id = _insert_user()
    old_time = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    new_time = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    revoked_at = datetime.now(UTC).isoformat()

    _insert_session(user_id=user_id, expires_at=old_time, revoked_at=None)
    _insert_session(user_id=user_id, expires_at=new_time, revoked_at=revoked_at)
    _insert_session(user_id=user_id, expires_at=new_time, revoked_at=None)

    deleted = run_once()
    assert deleted == 2

    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()
    assert int(row[0] if row else 0) == 1
