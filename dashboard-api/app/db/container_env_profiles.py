"""Container environment profile persistence."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.db.init import get_db_path

SourceMode = str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _parse_env_json(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result


def get_profile(container_id: str) -> dict[str, Any] | None:
    with _db_connect() as conn:
        row = conn.execute(
            """
            SELECT container_id, env_json, source_mode, detected_env_file,
                   last_detect_status, last_apply_status, pending_apply, updated_at, updated_by
            FROM container_env_profiles
            WHERE container_id = ?
            """,
            (container_id,),
        ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["env"] = _parse_env_json(str(payload.get("env_json") or "{}"))
    payload["pending_apply"] = bool(payload.get("pending_apply", 0))
    return payload


def upsert_profile(
    *,
    container_id: str,
    env: dict[str, str],
    source_mode: SourceMode,
    detected_env_file: str | None,
    last_detect_status: str | None,
    last_apply_status: str | None,
    pending_apply: bool,
    updated_by: str,
) -> dict[str, Any]:
    now = _now_iso()
    env_json = json.dumps(env, separators=(",", ":"), sort_keys=True)
    with _db_connect() as conn:
        conn.execute(
            """
            INSERT INTO container_env_profiles (
                container_id, env_json, source_mode, detected_env_file,
                last_detect_status, last_apply_status, pending_apply, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(container_id)
            DO UPDATE SET
                env_json = excluded.env_json,
                source_mode = excluded.source_mode,
                detected_env_file = excluded.detected_env_file,
                last_detect_status = excluded.last_detect_status,
                last_apply_status = excluded.last_apply_status,
                pending_apply = excluded.pending_apply,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (
                container_id,
                env_json,
                source_mode,
                detected_env_file,
                last_detect_status,
                last_apply_status,
                1 if pending_apply else 0,
                now,
                updated_by,
            ),
        )
    profile = get_profile(container_id)
    if profile is None:
        raise RuntimeError("Failed to upsert container env profile")
    return profile


def touch_detect_result(
    *,
    container_id: str,
    source_mode: SourceMode,
    detected_env_file: str | None,
    last_detect_status: str,
    updated_by: str,
) -> dict[str, Any]:
    existing = get_profile(container_id)
    env = existing["env"] if existing is not None else {}
    return upsert_profile(
        container_id=container_id,
        env=env,
        source_mode=source_mode,
        detected_env_file=detected_env_file,
        last_detect_status=last_detect_status,
        last_apply_status=(str(existing["last_apply_status"]) if existing else None),
        pending_apply=bool(existing["pending_apply"]) if existing else False,
        updated_by=updated_by,
    )
