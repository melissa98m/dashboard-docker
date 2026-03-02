"""Command executions retention background service tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from app.config import settings
from app.db.init import get_db_path
from app.services.command_retention import run_once


def _insert_execution(*, container_id: str, started_at: str, stdout_path: str, stderr_path: str) -> None:
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO command_specs (
                container_id, service_name, name, argv, cwd, env_allowlist, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                container_id,
                "svc",
                f"spec-{container_id}",
                '["pytest","-q"]',
                "/app",
                "[]",
                started_at,
            ),
        )
        spec_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO executions (
                command_spec_id, container_id, status, started_at, finished_at, exit_code,
                duration_ms, triggered_by, stdout_path, stderr_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                spec_id,
                container_id,
                "success",
                started_at,
                started_at,
                0,
                1000,
                "pytest",
                stdout_path,
                stderr_path,
            ),
        )


def test_command_retention_run_once_purges_old_rows_and_logs(tmp_path):
    old_time = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    new_time = datetime.now(UTC).isoformat()

    old_stdout = tmp_path / "old-stdout.log"
    old_stderr = tmp_path / "old-stderr.log"
    old_stdout.write_text("old out", encoding="utf-8")
    old_stderr.write_text("old err", encoding="utf-8")
    new_stdout = tmp_path / "new-stdout.log"
    new_stderr = tmp_path / "new-stderr.log"
    new_stdout.write_text("new out", encoding="utf-8")
    new_stderr.write_text("new err", encoding="utf-8")

    _insert_execution(
        container_id="old-ctn",
        started_at=old_time,
        stdout_path=str(old_stdout),
        stderr_path=str(old_stderr),
    )
    _insert_execution(
        container_id="new-ctn",
        started_at=new_time,
        stdout_path=str(new_stdout),
        stderr_path=str(new_stderr),
    )

    previous_days = settings.command_execution_retention_days
    settings.command_execution_retention_days = 30
    try:
        deleted = run_once()
        assert deleted == 1
    finally:
        settings.command_execution_retention_days = previous_days

    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute("SELECT container_id FROM executions ORDER BY container_id ASC").fetchall()
        container_ids = [row[0] for row in rows]

    assert "old-ctn" not in container_ids
    assert "new-ctn" in container_ids
    assert not Path(old_stdout).exists()
    assert not Path(old_stderr).exists()
    assert Path(new_stdout).exists()
    assert Path(new_stderr).exists()
