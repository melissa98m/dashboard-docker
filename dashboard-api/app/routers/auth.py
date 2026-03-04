"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.db.audit import write_audit_log
from app.db.auth import (
    authenticate_credentials,
    create_session,
    create_user,
    get_session,
    list_active_sessions,
    list_users,
    revoke_all_sessions_for_user_id,
    revoke_all_sessions_for_username,
    revoke_session,
    revoke_session_by_id,
    update_user_password,
    update_user_role,
)
from app.security import (
    AuthContext,
    clear_auth_cookies,
    get_current_auth_context,
    require_write_access,
    set_auth_cookies,
)

router = APIRouter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


class LoginResponse(BaseModel):
    authenticated: bool
    username: str
    role: str


class AuthMeResponse(BaseModel):
    authenticated: bool
    username: str
    role: str


class RevokeUserSessionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    exclude_current_session: bool = True


class RevokeUserIdSessionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)
    exclude_current_session: bool = True


class RevokeUserSessionsResponse(BaseModel):
    target_username: str
    revoked_count: int


class AuthSessionListItem(BaseModel):
    session_id: int
    user_id: int
    username: str
    role: str
    created_at: str
    last_seen_at: str
    expires_at: str
    is_current: bool


class AuthSessionsListResponse(BaseModel):
    items: list[AuthSessionListItem]
    total: int


class RevokeSessionByIdResponse(BaseModel):
    session_id: int
    revoked: bool


class AuthUserListItem(BaseModel):
    user_id: int
    username: str
    role: str
    last_login_at: str | None
    created_at: str
    updated_at: str


class AuthUsersListResponse(BaseModel):
    items: list[AuthUserListItem]
    total: int


class CreateAuthUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=512)
    role: str = Field(default="viewer", max_length=20)


class UpdateAuthUserRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(max_length=20)


class UpdateAuthUserPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=512)


class UpdateAuthUserPasswordResponse(BaseModel):
    user: AuthUserListItem
    revoked_sessions: int


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response):
    """Authenticate user and create secure session cookie."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    ok, username, user_id, reason = authenticate_credentials(
        username=payload.username,
        password=payload.password,
    )
    if not ok or not username or not user_id:
        write_audit_log(
            action="auth_login_failed",
            resource_type="user",
            resource_id=payload.username.strip() or None,
            triggered_by="anonymous",
            details={"reason": reason or "invalid_credentials"},
        )
        if reason == "locked":
            mins = settings.auth_lockout_minutes
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Compte temporairement verrouillé (trop de tentatives). Réessayez dans {mins} minutes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    raw_session, csrf_token = create_session(user_id=user_id)
    set_auth_cookies(response=response, session_token=raw_session, csrf_token=csrf_token)
    session = get_session(raw_session_token=raw_session)
    role = session.role if session is not None else "viewer"
    write_audit_log(
        action="auth_login_success",
        resource_type="user",
        resource_id=username,
        triggered_by=username,
    )
    return LoginResponse(authenticated=True, username=username, role=role)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_current_auth_context),
):
    """Revoke active session and clear auth cookies."""
    if not ctx.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    session_token = (request.cookies.get(settings.auth_session_cookie_name) or "").strip()
    if settings.auth_enabled and session_token:
        session = get_session(raw_session_token=session_token)
        revoke_session(raw_session_token=session_token)
        write_audit_log(
            action="auth_logout",
            resource_type="user",
            resource_id=session.username if session is not None else None,
            triggered_by=f"user:{session.username}" if session is not None else "anonymous",
        )
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=AuthMeResponse)
def me(ctx: AuthContext = Depends(get_current_auth_context)):
    """Return current authenticated principal."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    if not ctx.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return AuthMeResponse(
        authenticated=True,
        username=ctx.username or "unknown",
        role=ctx.role or "viewer",
    )


@router.get("/sessions", response_model=AuthSessionsListResponse)
def get_sessions(
    username: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    _actor: str = Depends(require_write_access),
    ctx: AuthContext = Depends(get_current_auth_context),
):
    """List active sessions for operational incident response."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    current_session_id: int | None = None
    if ctx.auth_type == "session" and ctx.session_token:
        current_session = get_session(raw_session_token=ctx.session_token)
        if current_session is not None:
            current_session_id = current_session.session_id

    rows = list_active_sessions(
        username=username,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    items = [
        AuthSessionListItem(
            session_id=int(row["id"]),
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            created_at=str(row["created_at"]),
            last_seen_at=str(row["last_seen_at"]),
            expires_at=str(row["expires_at"]),
            is_current=bool(current_session_id and int(row["id"]) == current_session_id),
        )
        for row in rows
    ]
    return AuthSessionsListResponse(items=items, total=len(items))


@router.get("/users", response_model=AuthUsersListResponse)
def get_users(
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _actor: str = Depends(require_write_access),
):
    """List known users for admin operations."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    rows = list_users(query=q, limit=limit, offset=offset)
    items = [
        AuthUserListItem(
            user_id=int(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            last_login_at=str(row["last_login_at"]) if row["last_login_at"] else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    ]
    return AuthUsersListResponse(items=items, total=len(items))


@router.post("/users", response_model=AuthUserListItem)
def create_auth_user(
    payload: CreateAuthUserRequest,
    actor: str = Depends(require_write_access),
):
    """Create a new user account."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    try:
        created = create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "username_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        if reason in {"invalid_username", "weak_password", "invalid_role"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)
        raise
    write_audit_log(
        action="auth_user_create",
        resource_type="user",
        resource_id=created["username"],
        triggered_by=actor,
        details={"role": str(created["role"])},
    )
    return AuthUserListItem(
        user_id=int(created["id"]),
        username=str(created["username"]),
        role=str(created["role"]),
        last_login_at=str(created["last_login_at"]) if created["last_login_at"] else None,
        created_at=str(created["created_at"]),
        updated_at=str(created["updated_at"]),
    )


@router.patch("/users/{user_id}/role", response_model=AuthUserListItem)
def patch_auth_user_role(
    user_id: int,
    payload: UpdateAuthUserRoleRequest,
    actor: str = Depends(require_write_access),
):
    """Update one user's role."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    try:
        updated = update_user_role(user_id=user_id, role=payload.role)
    except ValueError as exc:
        reason = str(exc)
        if reason == "last_admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
        if reason == "invalid_role":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)
        raise
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    write_audit_log(
        action="auth_user_role_update",
        resource_type="user",
        resource_id=str(updated["username"]),
        triggered_by=actor,
        details={"role": str(updated["role"])},
    )
    return AuthUserListItem(
        user_id=int(updated["id"]),
        username=str(updated["username"]),
        role=str(updated["role"]),
        last_login_at=str(updated["last_login_at"]) if updated["last_login_at"] else None,
        created_at=str(updated["created_at"]),
        updated_at=str(updated["updated_at"]),
    )


@router.patch("/users/{user_id}/password", response_model=UpdateAuthUserPasswordResponse)
def patch_auth_user_password(
    user_id: int,
    payload: UpdateAuthUserPasswordRequest,
    actor: str = Depends(require_write_access),
):
    """Update one user's password and revoke all active sessions."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    try:
        updated = update_user_password(user_id=user_id, password=payload.password)
    except ValueError as exc:
        reason = str(exc)
        if reason == "weak_password":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)
        raise
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    revoked_sessions = revoke_all_sessions_for_user_id(user_id=user_id)
    write_audit_log(
        action="auth_user_password_update",
        resource_type="user",
        resource_id=str(updated["username"]),
        triggered_by=actor,
        details={"revoked_sessions": str(revoked_sessions)},
    )
    return UpdateAuthUserPasswordResponse(
        user=AuthUserListItem(
            user_id=int(updated["id"]),
            username=str(updated["username"]),
            role=str(updated["role"]),
            last_login_at=str(updated["last_login_at"]) if updated["last_login_at"] else None,
            created_at=str(updated["created_at"]),
            updated_at=str(updated["updated_at"]),
        ),
        revoked_sessions=revoked_sessions,
    )


@router.delete("/sessions/{session_id}", response_model=RevokeSessionByIdResponse)
def revoke_session_by_id_endpoint(
    session_id: int,
    allow_current: bool = False,
    actor: str = Depends(require_write_access),
    ctx: AuthContext = Depends(get_current_auth_context),
):
    """Revoke one session by identifier."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    current_session_id: int | None = None
    if ctx.auth_type == "session" and ctx.session_token:
        current_session = get_session(raw_session_token=ctx.session_token)
        if current_session is not None:
            current_session_id = current_session.session_id

    if current_session_id is not None and session_id == current_session_id and not allow_current:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refusing to revoke current session without allow_current=true",
        )

    revoked = revoke_session_by_id(session_id=session_id)
    write_audit_log(
        action="auth_session_revoke_one",
        resource_type="auth_sessions",
        resource_id=str(session_id),
        triggered_by=actor,
        details={
            "revoked": str(revoked),
            "allow_current": str(allow_current),
        },
    )
    return RevokeSessionByIdResponse(session_id=session_id, revoked=revoked)


@router.post("/sessions/revoke-user", response_model=RevokeUserSessionsResponse)
def revoke_user_sessions(
    payload: RevokeUserSessionsRequest,
    actor: str = Depends(require_write_access),
    ctx: AuthContext = Depends(get_current_auth_context),
):
    """Revoke all sessions for one user (admin only)."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    target_username = payload.username.strip()
    exclude_token = (
        ctx.session_token
        if payload.exclude_current_session and ctx.auth_type == "session"
        else None
    )
    revoked_count = revoke_all_sessions_for_username(
        username=target_username,
        exclude_raw_session_token=exclude_token,
    )
    write_audit_log(
        action="auth_sessions_revoke_user",
        resource_type="auth_sessions",
        resource_id=target_username,
        triggered_by=actor,
        details={
            "revoked_count": str(revoked_count),
            "exclude_current_session": str(payload.exclude_current_session),
        },
    )
    return RevokeUserSessionsResponse(
        target_username=target_username,
        revoked_count=revoked_count,
    )


@router.post("/sessions/revoke-user-id", response_model=RevokeUserSessionsResponse)
def revoke_user_id_sessions(
    payload: RevokeUserIdSessionsRequest,
    actor: str = Depends(require_write_access),
    ctx: AuthContext = Depends(get_current_auth_context),
):
    """Revoke all sessions for one user id (admin only)."""
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is disabled",
        )
    exclude_token = (
        ctx.session_token
        if payload.exclude_current_session and ctx.auth_type == "session"
        else None
    )
    revoked_count = revoke_all_sessions_for_user_id(
        user_id=payload.user_id,
        exclude_raw_session_token=exclude_token,
    )
    write_audit_log(
        action="auth_sessions_revoke_user_id",
        resource_type="auth_sessions",
        resource_id=str(payload.user_id),
        triggered_by=actor,
        details={
            "revoked_count": str(revoked_count),
            "exclude_current_session": str(payload.exclude_current_session),
        },
    )
    return RevokeUserSessionsResponse(
        target_username=f"user-id:{payload.user_id}",
        revoked_count=revoked_count,
    )
