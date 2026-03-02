"""Authentication storage helpers."""

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.db.init import get_db_path

_PASSWORD_ALGO = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 600_000
_ALLOWED_ROLES = {"admin", "viewer"}
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,120}$")


@dataclass
class AuthSession:
    session_id: int
    user_id: int
    username: str
    role: str
    csrf_token: str
    expires_at: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _build_password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(digest).decode("ascii")
    return f"{_PASSWORD_ALGO}${_PASSWORD_ITERATIONS}${salt_b64}${hash_b64}"


def _validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in _ALLOWED_ROLES:
        raise ValueError("invalid_role")
    return normalized


def _validate_username(username: str) -> str:
    normalized = username.strip()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("invalid_username")
    return normalized


def _validate_password_strength(password: str) -> None:
    if len(password) < 12:
        raise ValueError("weak_password")
    has_alpha = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    if not has_alpha or not has_digit:
        raise ValueError("weak_password")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against persisted pbkdf2 hash."""
    try:
        algorithm, iterations_raw, salt_b64, hash_b64 = password_hash.split("$", 3)
        if algorithm != _PASSWORD_ALGO:
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
    except Exception:  # noqa: BLE001
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


def ensure_bootstrap_admin() -> None:
    """Create bootstrap admin account on first run when configured."""
    username = (settings.auth_bootstrap_admin_username or "").strip()
    password = settings.auth_bootstrap_admin_password or ""
    if not settings.auth_enabled or not username or not password:
        return
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if row is not None:
            return
        conn.execute(
            """
            INSERT INTO users (
                username, password_hash, role, failed_login_attempts,
                locked_until, last_login_at, created_at, updated_at
            ) VALUES (?, ?, ?, 0, NULL, NULL, ?, ?)
            """,
            (username, _build_password_hash(password), "admin", now, now),
        )


def create_user(*, username: str, password: str, role: str = "viewer") -> dict[str, Any]:
    """Create one user account with validated role and password policy."""
    normalized_username = _validate_username(username)
    normalized_role = _validate_role(role)
    _validate_password_strength(password)
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, role, failed_login_attempts,
                    locked_until, last_login_at, created_at, updated_at
                ) VALUES (?, ?, ?, 0, NULL, NULL, ?, ?)
                """,
                (
                    normalized_username,
                    _build_password_hash(password),
                    normalized_role,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("username_taken") from exc
        row = conn.execute(
            """
            SELECT id, username, role, last_login_at, created_at, updated_at
            FROM users
            WHERE username = ?
            """,
            (normalized_username,),
        ).fetchone()
    return {
        "id": int(row[0]),
        "username": str(row[1]),
        "role": str(row[2]),
        "last_login_at": str(row[3]) if row[3] else None,
        "created_at": str(row[4]),
        "updated_at": str(row[5]),
    }


def update_user_role(*, user_id: int, role: str) -> dict[str, Any] | None:
    """Update one user's role while preventing removal of last admin."""
    if user_id <= 0:
        return None
    normalized_role = _validate_role(role)
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, username, role, last_login_at, created_at, updated_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            return None
        current_role = str(user["role"])
        if current_role == "admin" and normalized_role != "admin":
            admin_count_row = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin'"
            ).fetchone()
            admin_count = int(admin_count_row[0] if admin_count_row else 0)
            if admin_count <= 1:
                raise ValueError("last_admin")
        conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (normalized_role, now, user_id),
        )
        updated = conn.execute(
            "SELECT id, username, role, last_login_at, created_at, updated_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if updated is None:
        return None
    return {
        "id": int(updated["id"]),
        "username": str(updated["username"]),
        "role": str(updated["role"]),
        "last_login_at": str(updated["last_login_at"]) if updated["last_login_at"] else None,
        "created_at": str(updated["created_at"]),
        "updated_at": str(updated["updated_at"]),
    }


def update_user_password(*, user_id: int, password: str) -> dict[str, Any] | None:
    """Update one user's password with policy checks and reset lockout counters."""
    if user_id <= 0:
        return None
    _validate_password_strength(password)
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            return None
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?,
                failed_login_attempts = 0,
                locked_until = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (_build_password_hash(password), now, user_id),
        )
        updated = conn.execute(
            "SELECT id, username, role, last_login_at, created_at, updated_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if updated is None:
        return None
    return {
        "id": int(updated["id"]),
        "username": str(updated["username"]),
        "role": str(updated["role"]),
        "last_login_at": str(updated["last_login_at"]) if updated["last_login_at"] else None,
        "created_at": str(updated["created_at"]),
        "updated_at": str(updated["updated_at"]),
    }


def authenticate_credentials(
    *, username: str, password: str
) -> tuple[bool, str | None, int | None]:
    """Validate credentials, applying lockout policy."""
    normalized = username.strip()
    if not normalized or not password:
        return False, None, None
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            """
            SELECT id, username, password_hash, locked_until, failed_login_attempts
            FROM users
            WHERE username = ?
            """,
            (normalized,),
        ).fetchone()
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        if user is None:
            # Constant-time-ish fallback to reduce user enumeration signal.
            verify_password(password, _build_password_hash("invalid-password"))
            return False, None, None
        locked_until = str(user["locked_until"] or "")
        if locked_until and locked_until > now:
            return False, None, int(user["id"])
        password_ok = verify_password(password, str(user["password_hash"]))
        if password_ok:
            conn.execute(
                """
                UPDATE users
                SET failed_login_attempts = 0,
                    locked_until = NULL,
                    last_login_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, int(user["id"])),
            )
            return True, str(user["username"]), int(user["id"])

        failed_attempts = int(user["failed_login_attempts"] or 0) + 1
        lockout_deadline: str | None = None
        if failed_attempts >= settings.auth_failed_login_limit:
            lockout_deadline = (
                now_dt + timedelta(minutes=settings.auth_lockout_minutes)
            ).isoformat()
            failed_attempts = 0
        conn.execute(
            """
            UPDATE users
            SET failed_login_attempts = ?, locked_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (failed_attempts, lockout_deadline, now, int(user["id"])),
        )
        return False, None, int(user["id"])


def create_session(*, user_id: int) -> tuple[str, str]:
    """Create persisted session and return raw session/csrf tokens."""
    raw_session = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=settings.auth_session_ttl_seconds)
    ).isoformat()
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (
                user_id, session_token_hash, csrf_token,
                created_at, expires_at, last_seen_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (user_id, _hash_token(raw_session), csrf_token, now, expires_at, now),
        )
    return raw_session, csrf_token


def get_session(*, raw_session_token: str) -> AuthSession | None:
    """Resolve active session by raw session token."""
    token_hash = _hash_token(raw_session_token)
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT s.id, s.user_id, s.csrf_token, s.expires_at, u.username, u.role
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        if row is None:
            return None
        return AuthSession(
            session_id=int(row["id"]),
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            csrf_token=str(row["csrf_token"]),
            expires_at=str(row["expires_at"]),
        )


def touch_session(*, session_id: int, current_expires_at: str) -> str:
    """Extend session expiry when close to expiration."""
    try:
        expires_dt = datetime.fromisoformat(current_expires_at)
    except ValueError:
        return current_expires_at
    now_dt = datetime.now(UTC)
    if (expires_dt - now_dt).total_seconds() > settings.auth_session_extend_threshold_seconds:
        return current_expires_at
    new_expiry = (now_dt + timedelta(seconds=settings.auth_session_ttl_seconds)).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = ?, last_seen_at = ? WHERE id = ?",
            (new_expiry, now_dt.isoformat(), session_id),
        )
    return new_expiry


def revoke_session(*, raw_session_token: str) -> None:
    """Revoke one session token if present."""
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "UPDATE auth_sessions SET revoked_at = ? "
            "WHERE session_token_hash = ? AND revoked_at IS NULL",
            (now, _hash_token(raw_session_token)),
        )


def revoke_session_by_id(*, session_id: int) -> bool:
    """Revoke one active session by id."""
    if session_id <= 0:
        return False
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        cursor = conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (now, session_id),
        )
        return int(cursor.rowcount) > 0


def _resolve_excluded_session_hash(exclude_raw_session_token: str | None) -> str | None:
    raw = (exclude_raw_session_token or "").strip()
    if not raw:
        return None
    return _hash_token(raw)


def revoke_all_sessions_for_username(
    *,
    username: str,
    exclude_raw_session_token: str | None = None,
) -> int:
    """Revoke all active sessions for one username."""
    normalized = username.strip()
    if not normalized:
        return 0
    now = _now_iso()
    excluded_hash = _resolve_excluded_session_hash(exclude_raw_session_token)
    with sqlite3.connect(get_db_path()) as conn:
        if excluded_hash:
            cursor = conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE revoked_at IS NULL
                  AND session_token_hash != ?
                  AND user_id IN (
                      SELECT id
                      FROM users
                      WHERE username = ?
                  )
                """,
                (now, excluded_hash, normalized),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE revoked_at IS NULL
                  AND user_id IN (
                      SELECT id
                      FROM users
                      WHERE username = ?
                  )
                """,
                (now, normalized),
            )
        return int(cursor.rowcount)


def revoke_all_sessions_for_user_id(
    *,
    user_id: int,
    exclude_raw_session_token: str | None = None,
) -> int:
    """Revoke all active sessions for one user id."""
    if user_id <= 0:
        return 0
    now = _now_iso()
    excluded_hash = _resolve_excluded_session_hash(exclude_raw_session_token)
    with sqlite3.connect(get_db_path()) as conn:
        if excluded_hash:
            cursor = conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE revoked_at IS NULL
                  AND session_token_hash != ?
                  AND user_id = ?
                """,
                (now, excluded_hash, user_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE revoked_at IS NULL
                  AND user_id = ?
                """,
                (now, user_id),
            )
        return int(cursor.rowcount)


def list_active_sessions(
    *,
    username: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List active non-revoked sessions with user identity."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    now = _now_iso()
    query = """
        SELECT
            s.id,
            s.user_id,
            u.username,
            u.role,
            s.created_at,
            s.last_seen_at,
            s.expires_at
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.revoked_at IS NULL
          AND s.expires_at > ?
    """
    params: list[Any] = [now]
    if user_id is not None and user_id > 0:
        query += " AND s.user_id = ?"
        params.append(user_id)
    if username:
        query += " AND u.username = ?"
        params.append(username.strip())
    query += " ORDER BY s.last_seen_at DESC, s.id DESC LIMIT ? OFFSET ?"
    params.extend([safe_limit, safe_offset])

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def list_users(
    *,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List users for admin operations."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    sql = """
        SELECT id, username, role, last_login_at, created_at, updated_at
        FROM users
    """
    params: list[Any] = []
    normalized_query = (query or "").strip()
    if normalized_query:
        sql += " WHERE username LIKE ?"
        params.append(f"%{normalized_query}%")
    sql += " ORDER BY username ASC LIMIT ? OFFSET ?"
    params.extend([safe_limit, safe_offset])
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def purge_expired_sessions() -> int:
    """Delete revoked/expired sessions and return deleted rows."""
    now = _now_iso()
    with sqlite3.connect(get_db_path()) as conn:
        cursor = conn.execute(
            """
            DELETE FROM auth_sessions
            WHERE expires_at <= ? OR revoked_at IS NOT NULL
            """,
            (now,),
        )
        return int(cursor.rowcount)
