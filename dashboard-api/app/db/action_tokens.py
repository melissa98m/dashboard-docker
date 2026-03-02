"""Storage for one-time action tokens."""

import hashlib
import sqlite3
from datetime import UTC, datetime

from app.db.init import get_db_path


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def consume_action_token(*, token: str, container_id: str) -> bool:
    """Mark token as consumed once. Returns False if already used."""
    token_hash = _sha256(token)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        try:
            conn.execute(
                """
                INSERT INTO used_action_tokens (token_hash, container_id, used_at)
                VALUES (?, ?, ?)
                """,
                (token_hash, container_id, now),
            )
            return True
        except sqlite3.IntegrityError:
            return False
