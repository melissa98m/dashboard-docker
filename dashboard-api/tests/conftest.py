"""Pytest fixtures."""

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

# Use temp DB for tests (before app imports config)
# Force override (docker-compose env_file can set these; tests need predictable values)
os.environ["DATABASE_URL"] = "sqlite:////tmp/dashboard_test.db"
os.environ["AUTH_ENABLED"] = "true"
os.environ["ALERT_ENGINE_ENABLED"] = "false"
os.environ["EVENT_WATCHER_ENABLED"] = "false"
os.environ["AUDIT_RETENTION_AUTO_ENABLED"] = "false"
os.environ["COMMAND_EXECUTION_RETENTION_AUTO_ENABLED"] = "false"

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login_as_admin(client, *, auth_enabled: bool = True):
    """Bootstrap admin, login, return CSRF token. Client keeps session cookies."""
    from app.config import settings
    from app.db.auth import ensure_bootstrap_admin

    settings.auth_enabled = auth_enabled
    settings.auth_cookie_secure = False
    settings.auth_bootstrap_admin_username = "admin"
    settings.auth_bootstrap_admin_password = "strong-password-123"
    ensure_bootstrap_admin()
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "strong-password-123"},
    )
    assert r.status_code == 200
    return client.cookies.get(settings.auth_csrf_cookie_name)


@pytest.fixture(autouse=True)
def reset_db(client):
    db_url = os.environ.get("DATABASE_URL", "sqlite:////tmp/dashboard_test.db")
    db_path = db_url.replace("sqlite:///", "")
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM alert_debounce_state")
        conn.execute("DELETE FROM alert_cooldowns")
        conn.execute("DELETE FROM alert_rules")
        conn.execute("DELETE FROM executions")
        conn.execute("DELETE FROM command_specs")
        conn.execute("DELETE FROM discovered_commands")
        conn.execute("DELETE FROM audit_log")
        conn.execute("DELETE FROM used_action_tokens")
        conn.execute("DELETE FROM used_stream_tokens")
        conn.execute("DELETE FROM container_env_profiles")
        conn.execute("DELETE FROM runtime_settings")
        conn.execute("DELETE FROM auth_sessions")
        conn.execute("DELETE FROM users")
