"""Authentication endpoints tests."""

import sqlite3
from datetime import UTC, datetime

from app.config import settings
from app.db.auth import create_session, ensure_bootstrap_admin, get_session
from app.db.init import get_db_path


def test_auth_login_me_logout_flow(client):
    from tests.conftest import login_as_admin

    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        csrf_token = login_as_admin(client)

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "admin"
        assert me.json()["role"] == "admin"

        no_csrf = client.patch("/api/system/runtime-settings", json={"sse_max_connections": 44})
        assert no_csrf.status_code == 403

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        with_csrf = client.patch(
            "/api/system/runtime-settings",
            json={"sse_max_connections": 45},
            headers={"x-csrf-token": csrf_token},
        )
        assert with_csrf.status_code == 200

        logout = client.post("/api/auth/logout")
        assert logout.status_code == 200

        me_after_logout = client.get("/api/auth/me")
        assert me_after_logout.status_code == 401
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_create_user_via_endpoint(client):
    from tests.conftest import login_as_admin

    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        csrf_token = login_as_admin(client)

        created = client.post(
            "/api/auth/users",
            json={
                "username": "created-user",
                "password": "StrongPass1234",
                "role": "viewer",
            },
            headers={"x-csrf-token": csrf_token},
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["username"] == "created-user"
        assert payload["role"] == "viewer"
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_create_user_rejects_weak_password(client):
    from tests.conftest import login_as_admin

    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        csrf_token = login_as_admin(client)

        created = client.post(
            "/api/auth/users",
            json={
                "username": "weak-user",
                "password": "weakpass",
                "role": "viewer",
            },
            headers={"x-csrf-token": csrf_token},
        )
        assert created.status_code == 422
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_update_user_role_and_cannot_demote_last_admin(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        target_id = _insert_user(username="role-target", role="viewer")
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200
        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)

        promoted = client.patch(
            f"/api/auth/users/{target_id}/role",
            json={"role": "admin"},
            headers={"x-csrf-token": csrf_token},
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "admin"

        admin_id = _get_user_id(username="admin")
        demote_one = client.patch(
            f"/api/auth/users/{target_id}/role",
            json={"role": "viewer"},
            headers={"x-csrf-token": csrf_token},
        )
        assert demote_one.status_code == 200
        assert demote_one.json()["role"] == "viewer"

        demote_last = client.patch(
            f"/api/auth/users/{admin_id}/role",
            json={"role": "viewer"},
            headers={"x-csrf-token": csrf_token},
        )
        assert demote_last.status_code == 400
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_update_user_password_and_revoke_sessions(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200
        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)

        created = client.post(
            "/api/auth/users",
            json={"username": "pwd-target", "password": "OldPass1234Ab", "role": "viewer"},
            headers={"x-csrf-token": csrf_token},
        )
        assert created.status_code == 200
        target_id = int(created.json()["user_id"])

        target_session, _ = create_session(user_id=target_id)
        assert get_session(raw_session_token=target_session) is not None

        rotated = client.patch(
            f"/api/auth/users/{target_id}/password",
            json={"password": "NewPass12345Ab"},
            headers={"x-csrf-token": csrf_token},
        )
        assert rotated.status_code == 200
        assert rotated.json()["revoked_sessions"] >= 1
        assert get_session(raw_session_token=target_session) is None

        old_login = client.post(
            "/api/auth/login",
            json={"username": "pwd-target", "password": "OldPass1234Ab"},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/auth/login",
            json={"username": "pwd-target", "password": "NewPass12345Ab"},
        )
        assert new_login.status_code == 200
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_password_update_rejects_weak_password(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        target_id = _insert_user(username="weak-update-target", role="viewer")
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200
        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)

        rotated = client.patch(
            f"/api/auth/users/{target_id}/password",
            json={"password": "weak"},
            headers={"x-csrf-token": csrf_token},
        )
        assert rotated.status_code == 422
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_auth_lockout_after_failed_attempts(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_limit = settings.auth_failed_login_limit
    previous_lockout = settings.auth_lockout_minutes
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_failed_login_limit = 2
        settings.auth_lockout_minutes = 5
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        first = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
        second = client.post("/api/auth/login", json={"username": "admin", "password": "bad"})
        third = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 401
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_failed_login_limit = previous_limit
        settings.auth_lockout_minutes = previous_lockout
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_auth_rejects_unauthenticated_request(client):
    """Without session, any /api/* request returns 401."""
    previous_auth_enabled = settings.auth_enabled
    try:
        settings.auth_enabled = True
        response = client.patch(
            "/api/system/runtime-settings",
            json={"sse_max_connections": 42},
        )
        assert response.status_code == 401
    finally:
        settings.auth_enabled = previous_auth_enabled


def _insert_user(*, username: str, role: str = "viewer") -> int:
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO users (
                username, password_hash, role, failed_login_attempts, locked_until,
                last_login_at, created_at, updated_at
            ) VALUES (?, ?, ?, 0, NULL, NULL, ?, ?)
            """,
            (username, "pbkdf2_sha256$1$AA==$AA==", role, now, now),
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _get_user_id(*, username: str) -> int:
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return int(row[0])


def test_admin_can_revoke_all_sessions_for_one_user(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        target_user_id = _insert_user(username="target-user")
        target_session, _ = create_session(user_id=target_user_id)
        assert get_session(raw_session_token=target_session) is not None

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        response = client.post(
            "/api/auth/sessions/revoke-user",
            json={"username": "target-user"},
            headers={"x-csrf-token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["target_username"] == "target-user"
        assert response.json()["revoked_count"] >= 1
        assert get_session(raw_session_token=target_session) is None
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_revoke_user_sessions_requires_csrf_with_session_auth(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        response = client.post(
            "/api/auth/sessions/revoke-user",
            json={"username": "target-user"},
        )
        assert response.status_code == 403
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_revoke_user_sessions_can_keep_current_admin_session(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        admin_id = _get_user_id(username="admin")
        extra_admin_session, _ = create_session(user_id=admin_id)
        assert get_session(raw_session_token=extra_admin_session) is not None

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        response = client.post(
            "/api/auth/sessions/revoke-user",
            json={"username": "admin", "exclude_current_session": True},
            headers={"x-csrf-token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["revoked_count"] >= 1
        assert get_session(raw_session_token=extra_admin_session) is None

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "admin"
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_revoke_sessions_by_user_id(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        target_user_id = _insert_user(username="target-id-user")
        target_session, _ = create_session(user_id=target_user_id)
        assert get_session(raw_session_token=target_session) is not None

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        response = client.post(
            "/api/auth/sessions/revoke-user-id",
            json={"user_id": target_user_id},
            headers={"x-csrf-token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["target_username"] == f"user-id:{target_user_id}"
        assert response.json()["revoked_count"] >= 1
        assert get_session(raw_session_token=target_session) is None
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_list_active_sessions(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        target_user_id = _insert_user(username="list-user")
        target_session, _ = create_session(user_id=target_user_id)
        assert get_session(raw_session_token=target_session) is not None

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        response = client.get(
            "/api/auth/sessions?username=list-user",
            headers={"x-csrf-token": csrf_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert data["items"][0]["username"] == "list-user"
        assert "session_token_hash" not in str(data)
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_list_sessions_marks_current_session(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        response = client.get(
            "/api/auth/sessions?username=admin",
            headers={"x-csrf-token": csrf_token},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(item["is_current"] is True for item in items)
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_revoke_one_session_by_id(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        target_user_id = _insert_user(username="single-revoke-user")
        target_session, _ = create_session(user_id=target_user_id)
        target_active = get_session(raw_session_token=target_session)
        assert target_active is not None

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        revoke = client.delete(
            f"/api/auth/sessions/{target_active.session_id}",
            headers={"x-csrf-token": csrf_token},
        )
        assert revoke.status_code == 200
        assert revoke.json()["revoked"] is True
        assert get_session(raw_session_token=target_session) is None
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_revoke_current_session_requires_allow_current_flag(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200

        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)
        listed = client.get(
            "/api/auth/sessions?username=admin",
            headers={"x-csrf-token": csrf_token},
        )
        assert listed.status_code == 200
        current_item = next(item for item in listed.json()["items"] if item["is_current"] is True)
        current_session_id = int(current_item["session_id"])

        blocked = client.delete(
            f"/api/auth/sessions/{current_session_id}",
            headers={"x-csrf-token": csrf_token},
        )
        assert blocked.status_code == 400

        allowed = client.delete(
            f"/api/auth/sessions/{current_session_id}?allow_current=true",
            headers={"x-csrf-token": csrf_token},
        )
        assert allowed.status_code == 200
        assert allowed.json()["revoked"] is True

        me_after = client.get("/api/auth/me")
        assert me_after.status_code == 401
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password


def test_admin_can_list_users_with_query_filter(client):
    previous_auth_enabled = settings.auth_enabled
    previous_secure_cookie = settings.auth_cookie_secure
    previous_admin_user = settings.auth_bootstrap_admin_username
    previous_admin_password = settings.auth_bootstrap_admin_password
    try:
        settings.auth_enabled = True
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_admin_username = "admin"
        settings.auth_bootstrap_admin_password = "strong-password-123"
        ensure_bootstrap_admin()
        _insert_user(username="alice-viewer")
        _insert_user(username="bob-viewer")

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "strong-password-123"},
        )
        assert login.status_code == 200
        csrf_token = client.cookies.get(settings.auth_csrf_cookie_name)

        response = client.get("/api/auth/users?q=alice", headers={"x-csrf-token": csrf_token})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all("alice" in item["username"] for item in data["items"])
        assert "password_hash" not in str(data)
    finally:
        settings.auth_enabled = previous_auth_enabled
        settings.auth_cookie_secure = previous_secure_cookie
        settings.auth_bootstrap_admin_username = previous_admin_user
        settings.auth_bootstrap_admin_password = previous_admin_password
