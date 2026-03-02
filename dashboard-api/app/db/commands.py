"""Command center storage helpers."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.db.init import get_db_path


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def list_specs(*, container_id: str | None = None) -> list[dict[str, Any]]:
    query = """
            SELECT id, container_id, service_name, name, argv, cwd, env_allowlist, discovered_at
            FROM command_specs
    """
    params: list[Any] = []
    if container_id is not None:
        query += " WHERE container_id = ?"
        params.append(container_id)
    query += " ORDER BY service_name ASC, name ASC"
    with _conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["argv"] = json.loads(str(data["argv"]))
        data["env_allowlist"] = (
            json.loads(str(data["env_allowlist"])) if data.get("env_allowlist") else []
        )
        results.append(data)
    return results


def create_spec(
    *,
    container_id: str,
    service_name: str,
    name: str,
    argv: list[str],
    cwd: str | None,
    env_allowlist: list[str],
) -> dict[str, Any]:
    discovered_at = _now_iso()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO command_specs (
                container_id, service_name, name, argv, cwd, env_allowlist, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                container_id,
                service_name,
                name,
                json.dumps(argv, separators=(",", ":")),
                cwd,
                json.dumps(env_allowlist, separators=(",", ":")),
                discovered_at,
            ),
        )
        spec_id = int(cur.lastrowid or 0)
        row = conn.execute(
            """
            SELECT id, container_id, service_name, name, argv, cwd, env_allowlist, discovered_at
            FROM command_specs WHERE id = ?
            """,
            (spec_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Failed to create command spec")
    data = dict(row)
    data["argv"] = json.loads(str(data["argv"]))
    data["env_allowlist"] = (
        json.loads(str(data["env_allowlist"])) if data.get("env_allowlist") else []
    )
    return data


def get_spec(spec_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, container_id, service_name, name, argv, cwd, env_allowlist, discovered_at
            FROM command_specs WHERE id = ?
            """,
            (spec_id,),
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["argv"] = json.loads(str(data["argv"]))
    data["env_allowlist"] = (
        json.loads(str(data["env_allowlist"])) if data.get("env_allowlist") else []
    )
    return data


def get_spec_by_container_and_name(container_id: str, name: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, container_id, service_name, name, argv, cwd, env_allowlist, discovered_at
            FROM command_specs
            WHERE container_id = ? AND name = ?
            """,
            (container_id, name),
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["argv"] = json.loads(str(data["argv"]))
    data["env_allowlist"] = (
        json.loads(str(data["env_allowlist"])) if data.get("env_allowlist") else []
    )
    return data


def create_execution(
    *,
    command_spec_id: int,
    container_id: str,
    triggered_by: str,
    stdout_path: str,
    stderr_path: str,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO executions (
                command_spec_id, container_id, status, started_at, finished_at,
                exit_code, duration_ms, triggered_by, stdout_path, stderr_path
            ) VALUES (?, ?, 'running', ?, NULL, NULL, NULL, ?, ?, ?)
            """,
            (command_spec_id, container_id, _now_iso(), triggered_by, stdout_path, stderr_path),
        )
        return int(cur.lastrowid or 0)


def complete_execution(
    *, execution_id: int, exit_code: int, duration_ms: int | None = None
) -> None:
    status = "success" if exit_code == 0 else "failed"
    with _conn() as conn:
        conn.execute(
            """
            UPDATE executions
            SET status = ?, finished_at = ?, exit_code = ?, duration_ms = ?
            WHERE id = ?
            """,
            (status, _now_iso(), exit_code, duration_ms, execution_id),
        )


def list_executions(limit: int = 100, *, container_id: str | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    query = """
            SELECT id, command_spec_id, container_id, status, started_at, finished_at, exit_code,
                   duration_ms, triggered_by, stdout_path, stderr_path
            FROM executions
    """
    params: list[Any] = []
    if container_id is not None:
        query += " WHERE container_id = ?"
        params.append(container_id)
    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(safe_limit)
    with _conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_execution(execution_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, command_spec_id, container_id, status, started_at, finished_at, exit_code,
                   duration_ms, triggered_by, stdout_path, stderr_path
            FROM executions
            WHERE id = ?
            """,
            (execution_id,),
        ).fetchone()
    return dict(row) if row else None


def count_purgeable_executions(*, older_than_days: int) -> int:
    safe_days = max(1, min(older_than_days, 3650))
    cutoff = (datetime.now(UTC) - timedelta(days=safe_days)).isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM executions WHERE started_at < ?", (cutoff,)
        ).fetchone()
    return int(row[0] if row else 0)


def purge_executions(*, older_than_days: int) -> int:
    safe_days = max(1, min(older_than_days, 3650))
    cutoff = (datetime.now(UTC) - timedelta(days=safe_days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, stdout_path, stderr_path FROM executions WHERE started_at < ?",
            (cutoff,),
        ).fetchall()
        if not rows:
            return 0
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM executions WHERE id IN ({placeholders})", tuple(ids))

    for row in rows:
        for key in ("stdout_path", "stderr_path"):
            raw_path = row[key]
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = Path(raw_path)
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                continue
    return len(rows)


def replace_discovered_commands(
    *,
    container_id: str,
    service_name: str,
    commands: list[dict[str, Any]],
) -> int:
    discovered_at = _now_iso()
    with _conn() as conn:
        conn.execute("DELETE FROM discovered_commands WHERE container_id = ?", (container_id,))
        for command in commands:
            conn.execute(
                """
                INSERT INTO discovered_commands (
                    container_id, service_name, raw_spec, discovered_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    container_id,
                    service_name,
                    json.dumps(command, separators=(",", ":")),
                    discovered_at,
                ),
            )
    return len(commands)


def list_discovered_commands(
    *,
    container_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    query = """
        SELECT id, container_id, service_name, raw_spec, discovered_at
        FROM discovered_commands
    """
    params: list[Any] = []
    if container_id is not None:
        query += " WHERE container_id = ?"
        params.append(container_id)
    query += " ORDER BY discovered_at DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([safe_limit, safe_offset])
    with _conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        try:
            raw_spec = json.loads(str(data["raw_spec"]))
        except json.JSONDecodeError:
            raw_spec = {}
        result = {
            "id": int(data["id"]),
            "container_id": str(data["container_id"]),
            "service_name": str(data["service_name"]),
            "discovered_at": str(data["discovered_at"]),
            "name": str(raw_spec.get("name") or "unknown"),
            "argv": raw_spec.get("argv") if isinstance(raw_spec.get("argv"), list) else [],
            "cwd": raw_spec.get("cwd") if isinstance(raw_spec.get("cwd"), str) else None,
            "source": str(raw_spec.get("source") or "unknown"),
        }
        results.append(result)
    return results


def get_discovered_command(discovered_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, container_id, service_name, raw_spec, discovered_at
            FROM discovered_commands
            WHERE id = ?
            """,
            (discovered_id,),
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    try:
        raw_spec = json.loads(str(data["raw_spec"]))
    except json.JSONDecodeError:
        raw_spec = {}
    return {
        "id": int(data["id"]),
        "container_id": str(data["container_id"]),
        "service_name": str(data["service_name"]),
        "discovered_at": str(data["discovered_at"]),
        "name": str(raw_spec.get("name") or "unknown"),
        "argv": raw_spec.get("argv") if isinstance(raw_spec.get("argv"), list) else [],
        "cwd": raw_spec.get("cwd") if isinstance(raw_spec.get("cwd"), str) else None,
        "source": str(raw_spec.get("source") or "unknown"),
    }


def count_discovered_commands(container_id: str) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM discovered_commands WHERE container_id = ?",
            (container_id,),
        ).fetchone()
    return int(row[0] if row else 0)


def latest_discovered_at(container_id: str) -> str | None:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT discovered_at
            FROM discovered_commands
            WHERE container_id = ?
            ORDER BY discovered_at DESC
            LIMIT 1
            """,
            (container_id,),
        ).fetchone()
    if row is None:
        return None
    return str(row["discovered_at"])
