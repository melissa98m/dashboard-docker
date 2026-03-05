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

        user_columns = conn.execute("PRAGMA table_info(users)").fetchall()
        user_column_names = {
            column[1] for column in user_columns if isinstance(column, tuple) and len(column) > 1
        }
        if user_columns and "totp_enabled" not in user_column_names:
            conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0")
        if user_columns and "totp_secret_encrypted" not in user_column_names:
            conn.execute("ALTER TABLE users ADD COLUMN totp_secret_encrypted TEXT")
        if user_columns and "totp_enabled_at" not in user_column_names:
            conn.execute("ALTER TABLE users ADD COLUMN totp_enabled_at TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_mfa_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                challenge_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                consumed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_mfa_challenges_expires "
            "ON auth_mfa_challenges(expires_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_mfa_enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                enrollment_hash TEXT NOT NULL UNIQUE,
                secret_encrypted TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_mfa_enrollments_expires "
            "ON auth_mfa_enrollments(expires_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_executions_container_started "
            "ON executions(container_id, started_at)"
        )


if __name__ == "__main__":
    migrate()
