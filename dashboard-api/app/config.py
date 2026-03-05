"""App configuration."""

from datetime import UTC, datetime

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:////data/dashboard.db"
    docker_host: str = "unix:///var/run/docker.sock"
    cors_allow_origins: str = "http://localhost:3000"
    cors_allow_methods: str = "GET,POST,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str = "Content-Type,X-CSRF-Token,X-API-Key"
    auth_enabled: bool = False
    auth_session_cookie_name: str = "dashboard_session"
    auth_csrf_cookie_name: str = "dashboard_csrf"
    auth_session_ttl_seconds: int = 28800
    auth_session_extend_threshold_seconds: int = 900
    auth_cookie_secure: bool = True
    auth_cookie_samesite: str = "lax"
    auth_failed_login_limit: int = 5
    auth_lockout_minutes: int = 15
    auth_mfa_issuer: str = "Dashboard"
    auth_mfa_totp_window_steps: int = 1
    auth_mfa_challenge_ttl_seconds: int = 300
    auth_mfa_challenge_max_attempts: int = 5
    auth_mfa_enrollment_ttl_seconds: int = 600
    auth_session_retention_auto_enabled: bool = True
    auth_session_retention_poll_seconds: int = 3600
    auth_bootstrap_admin_username: str | None = None
    auth_bootstrap_admin_password: str | None = None
    sse_max_connections: int = 20
    alert_engine_enabled: bool = True
    alert_poll_seconds: int = 10
    event_watcher_enabled: bool = True
    event_watcher_ntfy_topic: str | None = None
    ntfy_base_url: str | None = None
    ntfy_topic: str | None = None
    resend_api_key: str = ""
    alert_email_from: str = ""
    alert_email_to: str = ""
    public_api_url: str | None = None
    restart_action_ttl_seconds: int = 300
    restart_token_rate_limit_window_seconds: int = 60
    restart_token_rate_limit_max_attempts: int = 20
    execution_stream_token_ttl_seconds: int = 120
    command_discovery_cache_ttl_seconds: int = 300
    log_snapshot_redaction_enabled: bool = True
    log_snapshot_redaction_extra_patterns: str = ""
    audit_retention_days: int = 90
    audit_retention_auto_enabled: bool = True
    audit_retention_poll_seconds: int = 86400
    command_execution_retention_days: int = 30
    command_execution_retention_auto_enabled: bool = True
    command_execution_retention_poll_seconds: int = 86400
    api_secret_key: str = ""
    act_enabled: bool = False
    act_workflows_path: str = "/workspace"


settings = Settings()
# Runtime marker useful for ops visibility in /api/system/security-status.
SETTINGS_LOADED_AT = datetime.now(UTC).isoformat()
