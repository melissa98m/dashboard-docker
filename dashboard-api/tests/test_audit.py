"""Audit endpoints tests."""

import sqlite3
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.db.audit import write_audit_log
from app.db.init import get_db_path
from tests.conftest import login_as_admin


def test_list_audit_logs_returns_entries(client):
    login_as_admin(client)
    write_audit_log(
        action="unit_test_action",
        resource_type="test",
        resource_id="r-1",
        triggered_by="pytest",
        details={"k": "v"},
    )
    response = client.get("/api/audit/logs")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    assert payload[0]["action"] == "unit_test_action"
    assert payload[0]["details"]["k"] == "v"


def test_list_audit_logs_filter_by_action(client):
    login_as_admin(client)
    write_audit_log(
        action="action_one",
        resource_type="test",
        resource_id="r-1",
        triggered_by="pytest",
        details={},
    )
    write_audit_log(
        action="action_two",
        resource_type="test",
        resource_id="r-2",
        triggered_by="pytest",
        details={},
    )
    response = client.get("/api/audit/logs?action=action_two")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    assert all(item["action"] == "action_two" for item in payload)


def test_purge_audit_logs_endpoint(client):
    csrf = login_as_admin(client)
    write_audit_log(
        action="old_action",
        resource_type="test",
        resource_id="old-1",
        triggered_by="pytest",
        details={},
    )
    write_audit_log(
        action="new_action",
        resource_type="test",
        resource_id="new-1",
        triggered_by="pytest",
        details={},
    )
    old_date = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "UPDATE audit_log SET created_at = ? WHERE action = ?",
            (old_date, "old_action"),
        )

    purge_response = client.post(
        "/api/audit/purge?days=90",
        headers={"x-csrf-token": csrf},
    )
    assert purge_response.status_code == 200
    purge_payload = purge_response.json()
    assert purge_payload["ok"] is True
    assert purge_payload["deleted_rows"] >= 1

    logs = client.get("/api/audit/logs").json()
    actions = [item["action"] for item in logs]
    assert "old_action" not in actions


def test_purge_requires_auth(client):
    previous_auth = settings.auth_enabled
    try:
        settings.auth_enabled = True
        unauthorized = client.post("/api/audit/purge")
        assert unauthorized.status_code == 401
        csrf = login_as_admin(client)
        authorized = client.post("/api/audit/purge", headers={"x-csrf-token": csrf})
        assert authorized.status_code == 200
    finally:
        settings.auth_enabled = previous_auth


def test_purge_dry_run_endpoint(client):
    login_as_admin(client)
    write_audit_log(
        action="dry_old_action",
        resource_type="test",
        resource_id="old-1",
        triggered_by="pytest",
        details={},
    )
    old_date = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "UPDATE audit_log SET created_at = ? WHERE action = ?",
            (old_date, "dry_old_action"),
        )
    response = client.get("/api/audit/purge-dry-run?days=90")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["purgeable_rows"] >= 1


def test_write_audit_log_redacts_sensitive_detail_keys(client):
    login_as_admin(client)
    write_audit_log(
        action="sensitive_action",
        resource_type="test",
        resource_id="r-42",
        triggered_by="pytest",
        details={
            "api_key": "should-not-appear",
            "token": "super-secret-token",
            "password": "super-secret-password",
            "safe_value": "visible",
        },
    )
    response = client.get("/api/audit/logs?action=sensitive_action")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    details = payload[0]["details"]
    assert details["safe_value"] == "visible"
    assert details["api_key"] == "[REDACTED]"
    assert details["token"] == "[REDACTED]"
    assert details["password"] == "[REDACTED]"
