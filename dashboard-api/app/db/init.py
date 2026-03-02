"""Initialize database with schema."""

import sqlite3
from pathlib import Path

from app.config import settings


def get_db_path() -> str:
    """Extract path from sqlite URL."""
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "")
    return url


def migrate() -> None:
    """Run schema migrations."""
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)
        columns = conn.execute("PRAGMA table_info(alert_rules)").fetchall()
        has_debounce_samples = any(
            isinstance(column, tuple) and len(column) > 1 and column[1] == "debounce_samples"
            for column in columns
        )
        if not has_debounce_samples:
            conn.execute(
                "ALTER TABLE alert_rules ADD COLUMN debounce_samples INTEGER NOT NULL DEFAULT 1"
            )
        env_columns = conn.execute("PRAGMA table_info(container_env_profiles)").fetchall()
        env_column_names = {
            column[1] for column in env_columns if isinstance(column, tuple) and len(column) > 1
        }
        if env_columns and "pending_apply" not in env_column_names:
            conn.execute(
                "ALTER TABLE container_env_profiles "
                "ADD COLUMN pending_apply INTEGER NOT NULL DEFAULT 1"
            )
        if env_columns and "updated_by" not in env_column_names:
            conn.execute(
                "ALTER TABLE container_env_profiles "
                "ADD COLUMN updated_by TEXT NOT NULL DEFAULT 'system'"
            )
        execution_columns = conn.execute("PRAGMA table_info(executions)").fetchall()
        execution_column_names = {
            column[1]
            for column in execution_columns
            if isinstance(column, tuple) and len(column) > 1
        }
        if execution_columns and "status" not in execution_column_names:
            conn.execute("ALTER TABLE executions ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'")
        if execution_columns and "duration_ms" not in execution_column_names:
            conn.execute("ALTER TABLE executions ADD COLUMN duration_ms INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_executions_container_started "
            "ON executions(container_id, started_at)"
        )


if __name__ == "__main__":
    migrate()
