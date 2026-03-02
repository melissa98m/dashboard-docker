"""System endpoints tests."""

import sqlite3

from app.config import settings
from app.db.init import get_db_path
from tests.conftest import login_as_admin


def test_version_endpoint(client):
    login_as_admin(client)
    response = client.get("/api/system/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "0.1.0"
    assert payload["docker_host"].startswith("unix://")


def test_version_requires_auth(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.get("/api/system/version")
        assert unauthorized.status_code == 401
        login_as_admin(client)
        authorized = client.get("/api/system/version")
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth


def test_security_status_exposes_non_sensitive_flags(client):
    previous_secret = settings.api_secret_key
    previous_public_api_url = settings.public_api_url
    previous_ntfy_base = settings.ntfy_base_url
    previous_ntfy_topic = settings.ntfy_topic
    previous_audit_days = settings.audit_retention_days
    previous_audit_auto = settings.audit_retention_auto_enabled
    previous_audit_poll = settings.audit_retention_poll_seconds
    previous_log_redaction = settings.log_snapshot_redaction_enabled
    previous_log_extra = settings.log_snapshot_redaction_extra_patterns
    previous_auth_enabled = settings.auth_enabled
    previous_auth_retention_auto = settings.auth_session_retention_auto_enabled
    previous_auth_retention_poll = settings.auth_session_retention_poll_seconds
    try:
        settings.auth_enabled = True
        settings.auth_session_retention_auto_enabled = True
        settings.auth_session_retention_poll_seconds = 1800
        settings.api_secret_key = "secret-key"
        settings.public_api_url = "http://localhost:8000"
        settings.ntfy_base_url = "https://ntfy.example.com"
        settings.ntfy_topic = "dashboard"
        settings.audit_retention_days = 45
        settings.audit_retention_auto_enabled = True
        settings.audit_retention_poll_seconds = 3600
        settings.log_snapshot_redaction_enabled = True
        settings.log_snapshot_redaction_extra_patterns = r"sessionid=\w+||jwt=[A-Za-z0-9-_\.]+"

        login_as_admin(client)
        response = client.get("/api/system/security-status")
        assert response.status_code == 200
        data = response.json()
        assert data["write_auth_configured"] is True
        assert data["auth_enabled"] is True
        assert data["read_auth_enforced"] is True
        assert data["read_auth_configured"] is True
        assert data["restart_action_enabled"] is True
        assert data["ntfy_configured"] is True
        assert data["auth_session_retention_auto_enabled"] is True
        assert isinstance(data["auth_session_retention_running"], bool)
        assert data["auth_session_retention_poll_seconds"] == 1800
        assert isinstance(data["alert_engine_running"], bool)
        assert data["alert_engine_last_cycle_at"] is None or isinstance(
            data["alert_engine_last_cycle_at"], str
        )
        assert data["alert_engine_last_success_at"] is None or isinstance(
            data["alert_engine_last_success_at"], str
        )
        assert isinstance(data["alert_engine_consecutive_errors"], int)
        assert data["alert_engine_consecutive_errors"] >= 0
        assert data["alert_engine_last_error_reason"] is None or isinstance(
            data["alert_engine_last_error_reason"], str
        )
        assert data["alert_engine_last_error_at"] is None or isinstance(
            data["alert_engine_last_error_at"], str
        )
        assert data["audit_retention_days"] == 45
        assert data["audit_retention_auto_enabled"] is True
        assert isinstance(data["audit_retention_running"], bool)
        assert data["audit_retention_last_cycle_at"] is None or isinstance(
            data["audit_retention_last_cycle_at"], str
        )
        assert data["audit_retention_last_success_at"] is None or isinstance(
            data["audit_retention_last_success_at"], str
        )
        assert isinstance(data["audit_retention_consecutive_errors"], int)
        assert data["audit_retention_consecutive_errors"] >= 0
        assert data["audit_retention_last_error_reason"] is None or isinstance(
            data["audit_retention_last_error_reason"], str
        )
        assert data["audit_retention_last_error_at"] is None or isinstance(
            data["audit_retention_last_error_at"], str
        )
        assert data["audit_retention_poll_seconds"] == 3600
        assert data["log_snapshot_redaction_enabled"] is True
        assert "authorization_bearer" in data["log_snapshot_redaction_default_rules"]
        assert "credential_key_values" in data["log_snapshot_redaction_default_rules"]
        assert "email_addresses" in data["log_snapshot_redaction_default_rules"]
        # extra regexes are not exposed directly, only non-sensitive count.
        assert data["log_snapshot_redaction_extra_rules_count"] == 2
        assert isinstance(data["runtime_config_loaded_at"], str)
        assert "T" in data["runtime_config_loaded_at"]
        assert "secret-key" not in str(data)
        assert "sessionid" not in str(data)
    finally:
        settings.api_secret_key = previous_secret
        settings.public_api_url = previous_public_api_url
        settings.ntfy_base_url = previous_ntfy_base
        settings.ntfy_topic = previous_ntfy_topic
        settings.audit_retention_days = previous_audit_days
        settings.audit_retention_auto_enabled = previous_audit_auto
        settings.audit_retention_poll_seconds = previous_audit_poll
        settings.log_snapshot_redaction_enabled = previous_log_redaction
        settings.log_snapshot_redaction_extra_patterns = previous_log_extra
        settings.auth_enabled = previous_auth_enabled
        settings.auth_session_retention_auto_enabled = previous_auth_retention_auto
        settings.auth_session_retention_poll_seconds = previous_auth_retention_poll


def test_security_status_requires_auth(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.get("/api/system/security-status")
        assert unauthorized.status_code == 401

        login_as_admin(client)
        authorized = client.get("/api/system/security-status")
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth


def test_dependencies_health_endpoint(client, monkeypatch):
    from app.routers import system as system_router

    login_as_admin(client)
    monkeypatch.setattr(system_router, "_check_docker_dependency", lambda: (True, "reachable"))
    monkeypatch.setattr(system_router, "_check_sqlite_dependency", lambda: (True, "writable"))
    response = client.get("/api/system/health/deps")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"]["docker"]["ok"] is True
    assert payload["checks"]["sqlite"]["ok"] is True


def test_dependencies_health_requires_auth(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.get("/api/system/health/deps")
        assert unauthorized.status_code == 401
        login_as_admin(client)
        authorized = client.get("/api/system/health/deps")
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth


def test_runtime_settings_endpoint_returns_editable_values(client):
    login_as_admin(client)
    response = client.get("/api/system/runtime-settings")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["sse_max_connections"], int)
    assert isinstance(payload["alert_engine_enabled"], bool)
    assert isinstance(payload["alert_poll_seconds"], int)
    assert isinstance(payload["restart_action_ttl_seconds"], int)
    assert isinstance(payload["restart_token_rate_limit_window_seconds"], int)
    assert isinstance(payload["restart_token_rate_limit_max_attempts"], int)
    assert isinstance(payload["audit_retention_days"], int)
    assert isinstance(payload["audit_retention_auto_enabled"], bool)
    assert isinstance(payload["audit_retention_poll_seconds"], int)


def test_patch_runtime_settings_updates_memory_and_db(client):
    csrf = login_as_admin(client)
    payload = {
        "sse_max_connections": 55,
        "alert_poll_seconds": 12,
        "audit_retention_days": 120,
    }
    response = client.patch(
        "/api/system/runtime-settings",
        json=payload,
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sse_max_connections"] == 55
    assert data["alert_poll_seconds"] == 12
    assert data["audit_retention_days"] == 120

    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT key, value FROM runtime_settings WHERE key IN (?, ?, ?)",
            ("sse_max_connections", "alert_poll_seconds", "audit_retention_days"),
        ).fetchall()
    persisted = {key: int(value) for key, value in rows}
    assert persisted["sse_max_connections"] == 55
    assert persisted["alert_poll_seconds"] == 12
    assert persisted["audit_retention_days"] == 120


def test_patch_runtime_settings_validates_ranges(client):
    csrf = login_as_admin(client)
    response = client.patch(
        "/api/system/runtime-settings",
        json={"alert_poll_seconds": 0},
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 422


def test_patch_runtime_settings_requires_auth_and_csrf(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.patch(
            "/api/system/runtime-settings",
            json={"sse_max_connections": 42},
        )
        assert unauthorized.status_code == 401

        csrf = login_as_admin(client)
        authorized = client.patch(
            "/api/system/runtime-settings",
            headers={"x-csrf-token": csrf},
            json={"sse_max_connections": 42},
        )
        assert authorized.status_code == 200
        assert authorized.json()["sse_max_connections"] == 42
    finally:
        settings.auth_enabled = previous_auth


def test_patch_runtime_settings_toggles_services(client):
    csrf = login_as_admin(client)
    headers = {"x-csrf-token": csrf}

    class FakeService:
        def __init__(self):
            self.started = 0
            self.stopped = 0

        def start(self):
            self.started += 1

        def stop(self):
            self.stopped += 1

    fake_alert_engine = FakeService()
    fake_audit_retention = FakeService()
    previous_alert_enabled = settings.alert_engine_enabled
    previous_audit_enabled = settings.audit_retention_auto_enabled
    previous_alert_service = getattr(client.app.state, "alert_engine", None)
    previous_audit_service = getattr(client.app.state, "audit_retention_service", None)
    try:
        client.app.state.alert_engine = fake_alert_engine
        client.app.state.audit_retention_service = fake_audit_retention
        settings.alert_engine_enabled = True
        settings.audit_retention_auto_enabled = True

        disable = client.patch(
            "/api/system/runtime-settings",
            json={
                "alert_engine_enabled": False,
                "audit_retention_auto_enabled": False,
            },
            headers=headers,
        )
        assert disable.status_code == 200
        assert fake_alert_engine.stopped == 1
        assert fake_audit_retention.stopped == 1
        assert disable.json()["alert_engine_enabled"] is False
        assert disable.json()["audit_retention_auto_enabled"] is False

        enable = client.patch(
            "/api/system/runtime-settings",
            json={
                "alert_engine_enabled": True,
                "audit_retention_auto_enabled": True,
            },
            headers=headers,
        )
        assert enable.status_code == 200
        assert fake_alert_engine.started == 1
        assert fake_audit_retention.started == 1
        assert enable.json()["alert_engine_enabled"] is True
        assert enable.json()["audit_retention_auto_enabled"] is True
    finally:
        settings.alert_engine_enabled = previous_alert_enabled
        settings.audit_retention_auto_enabled = previous_audit_enabled
        client.app.state.alert_engine = previous_alert_service
        client.app.state.audit_retention_service = previous_audit_service
