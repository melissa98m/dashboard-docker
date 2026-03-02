-- Alert rules per container
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id TEXT NOT NULL,
    container_name TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    threshold REAL NOT NULL,
    cooldown_seconds INTEGER NOT NULL DEFAULT 300,
    debounce_samples INTEGER NOT NULL DEFAULT 1,
    ntfy_topic TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(container_id, metric_type)
);

CREATE TABLE IF NOT EXISTS alert_cooldowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_rule_id INTEGER NOT NULL,
    triggered_at TEXT NOT NULL,
    FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id)
);

CREATE INDEX IF NOT EXISTS idx_alert_cooldowns_rule ON alert_cooldowns(alert_rule_id);

CREATE TABLE IF NOT EXISTS alert_debounce_state (
    alert_rule_id INTEGER PRIMARY KEY,
    consecutive_breaches INTEGER NOT NULL,
    last_breach_at TEXT NOT NULL,
    FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id)
);

CREATE TABLE IF NOT EXISTS command_specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    name TEXT NOT NULL,
    argv TEXT NOT NULL,
    cwd TEXT,
    env_allowlist TEXT,
    discovered_at TEXT NOT NULL,
    UNIQUE(container_id, name)
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_spec_id INTEGER NOT NULL,
    container_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER,
    duration_ms INTEGER,
    triggered_by TEXT,
    stdout_path TEXT,
    stderr_path TEXT,
    FOREIGN KEY (command_spec_id) REFERENCES command_specs(id)
);

CREATE INDEX IF NOT EXISTS idx_executions_spec ON executions(command_spec_id);
CREATE INDEX IF NOT EXISTS idx_executions_started ON executions(started_at);
CREATE INDEX IF NOT EXISTS idx_executions_container_started ON executions(container_id, started_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    triggered_by TEXT,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS discovered_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    container_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    raw_spec TEXT NOT NULL,
    discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS used_action_tokens (
    token_hash TEXT PRIMARY KEY,
    container_id TEXT NOT NULL,
    used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS used_stream_tokens (
    token_hash TEXT PRIMARY KEY,
    execution_id INTEGER NOT NULL,
    used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS container_env_profiles (
    container_id TEXT PRIMARY KEY,
    env_json TEXT NOT NULL,
    source_mode TEXT NOT NULL DEFAULT 'db_fallback',
    detected_env_file TEXT,
    last_detect_status TEXT,
    last_apply_status TEXT,
    pending_apply INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);
