"""Storage for one-time execution stream tokens."""

import hashlib
import sqlite3
from datetime import UTC, datetime

from app.db.init import get_db_path


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def consume_stream_token(*, token: str, execution_id: int) -> bool:
    """Mark stream token as consumed once. Returns False if already used."""
    token_hash = _sha256(token)
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        try:
            conn.execute(
                """
                INSERT INTO used_stream_tokens (token_hash, execution_id, used_at)
                VALUES (?, ?, ?)
                """,
                (token_hash, execution_id, now),
            )
            return True
        except sqlite3.IntegrityError:
            return False
