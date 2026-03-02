"""Authentication and authorization helpers."""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException, Request, Response, status

from app.config import settings
from app.db.auth import get_session, touch_session


def _constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


@dataclass
class AuthContext:
    actor: str
    role: str | None
    username: str | None
    is_authenticated: bool
    auth_type: str
    session_token: str | None = None


def _normalize_samesite(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"strict", "none", "lax"}:
        return normalized
    return "lax"


def set_auth_cookies(*, response: Response, session_token: str, csrf_token: str) -> None:
    """Attach session + csrf cookies to response."""
    samesite = _normalize_samesite(settings.auth_cookie_samesite)
    response.set_cookie(
        key=settings.auth_session_cookie_name,
        value=session_token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=samesite,
        path="/",
    )
    response.set_cookie(
        key=settings.auth_csrf_cookie_name,
        value=csrf_token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=samesite,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    """Remove auth cookies from response."""
    response.delete_cookie(key=settings.auth_session_cookie_name, path="/")
    response.delete_cookie(key=settings.auth_csrf_cookie_name, path="/")


def _session_context(
    *,
    request: Request,
    require_write: bool,
    x_csrf_token: str | None,
) -> AuthContext | None:
    session_token = (request.cookies.get(settings.auth_session_cookie_name) or "").strip()
    if not session_token:
        return None
    session = get_session(raw_session_token=session_token)
    if session is None:
        return None

    if require_write:
        if session.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        csrf_cookie = (request.cookies.get(settings.auth_csrf_cookie_name) or "").strip()
        csrf_header = x_csrf_token.strip() if isinstance(x_csrf_token, str) else ""
        if (
            not csrf_header
            or not csrf_cookie
            or not _constant_time_equals(csrf_header, csrf_cookie)
            or not _constant_time_equals(csrf_header, session.csrf_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )

    touch_session(session_id=session.session_id, current_expires_at=session.expires_at)
    return AuthContext(
        actor=f"user:{session.username}",
        role=session.role,
        username=session.username,
        is_authenticated=True,
        auth_type="session",
        session_token=session_token,
    )


def _resolve_context(
    *,
    request: Request,
    x_csrf_token: str | None,
    require_write: bool,
) -> AuthContext:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    session_ctx = _session_context(
        request=request,
        require_write=require_write,
        x_csrf_token=x_csrf_token,
    )
    if session_ctx is not None:
        return session_ctx
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized action",
    )


def get_current_auth_context(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="x-csrf-token"),
) -> AuthContext:
    """Resolve current context without forcing write permissions."""
    return _resolve_context(
        request=request,
        x_csrf_token=x_csrf_token,
        require_write=False,
    )


def require_write_access(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="x-csrf-token"),
) -> str:
    """Validate write access and return actor identifier."""
    return _resolve_context(
        request=request,
        x_csrf_token=x_csrf_token,
        require_write=True,
    ).actor


def require_read_access(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="x-csrf-token"),
) -> str:
    """Validate read access and return actor identifier."""
    return _resolve_context(
        request=request,
        x_csrf_token=x_csrf_token,
        require_write=False,
    ).actor


def _token_secret() -> bytes:
    if not settings.api_secret_key:
        raise ValueError("API_SECRET_KEY is missing")
    return settings.api_secret_key.encode("utf-8")


def create_restart_token(*, container_id: str, ttl_seconds: int | None = None) -> str:
    """Create a signed restart token with expiration."""
    secret = _token_secret()
    expires = datetime.now(UTC) + timedelta(
        seconds=ttl_seconds if ttl_seconds is not None else settings.restart_action_ttl_seconds
    )
    payload = {
        "container_id": container_id,
        "exp": int(expires.timestamp()),
        "nonce": secrets.token_urlsafe(12),
    }
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")
    signature = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def verify_restart_token(token: str) -> str:
    """Validate restart token and return container_id."""
    secret = _token_secret()
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
        got_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(expected_sig, got_sig):
            raise ValueError("Invalid token signature")

        raw_payload = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(raw_payload.decode("utf-8"))
        container_id = payload.get("container_id")
        exp = payload.get("exp")
        if not isinstance(container_id, str) or not container_id:
            raise ValueError("Invalid token payload")
        if not isinstance(exp, int):
            raise ValueError("Invalid token expiration")
        if datetime.now(UTC).timestamp() > exp:
            raise ValueError("Token expired")
        return container_id
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Malformed token") from exc


def create_execution_stream_token(
    *, execution_id: int, ttl_seconds: int | None = None
) -> str:
    """Create signed token for execution output stream."""
    secret = _token_secret()
    expires = datetime.now(UTC) + timedelta(
        seconds=ttl_seconds
        if ttl_seconds is not None
        else settings.execution_stream_token_ttl_seconds
    )
    payload = {
        "execution_id": execution_id,
        "exp": int(expires.timestamp()),
        "nonce": secrets.token_urlsafe(12),
        "typ": "exec_stream",
    }
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")
    signature = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def verify_execution_stream_token(token: str) -> int:
    """Validate stream token and return execution_id."""
    secret = _token_secret()
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
        got_sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(expected_sig, got_sig):
            raise ValueError("Invalid token signature")
        raw_payload = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        payload = json.loads(raw_payload.decode("utf-8"))
        if payload.get("typ") != "exec_stream":
            raise ValueError("Invalid token type")
        execution_id = payload.get("execution_id")
        exp = payload.get("exp")
        if not isinstance(execution_id, int) or execution_id <= 0:
            raise ValueError("Invalid execution id")
        if not isinstance(exp, int):
            raise ValueError("Invalid token expiration")
        if datetime.now(UTC).timestamp() > exp:
            raise ValueError("Token expired")
        return execution_id
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Malformed token") from exc
