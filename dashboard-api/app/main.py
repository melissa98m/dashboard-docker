"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.auth import ensure_bootstrap_admin
from app.db.init import migrate
from app.db.runtime_settings import apply_runtime_settings, list_runtime_settings
from app.routers import (
    alerts,
    audit,
    auth,
    commands,
    container_env,
    containers,
    health,
    images,
    system,
    volumes,
    workflows,
)
from app.security import get_current_auth_context
from app.services.alert_engine import AlertEngine
from app.services.alert_seed import run_seed as seed_default_alert_rules
from app.services.audit_retention import AuditRetentionService
from app.services.auth_session_retention import AuthSessionRetentionService
from app.services.command_retention import CommandRetentionService
from app.services.event_watcher import EventWatcherService


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    ensure_bootstrap_admin()
    apply_runtime_settings(overrides=list_runtime_settings())
    seed_default_alert_rules()
    app.state.alert_engine = AlertEngine()
    app.state.event_watcher = EventWatcherService()
    app.state.audit_retention_service = AuditRetentionService()
    app.state.auth_session_retention_service = AuthSessionRetentionService()
    app.state.command_retention_service = CommandRetentionService()
    app.state.alert_engine.start()
    app.state.event_watcher.start()
    app.state.audit_retention_service.start()
    app.state.auth_session_retention_service.start()
    app.state.command_retention_service.start()
    yield
    app.state.alert_engine.stop()
    app.state.event_watcher.stop()
    app.state.audit_retention_service.stop()
    app.state.auth_session_retention_service.stop()
    app.state.command_retention_service.stop()


app = FastAPI(
    title="Dashboard API",
    description="Docker monitoring and management for Raspberry Pi",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env.strip().lower() in {"development", "dev"} else None,
    redoc_url="/redoc" if settings.app_env.strip().lower() in {"development", "dev"} else None,
    openapi_url="/openapi.json"
    if settings.app_env.strip().lower() in {"development", "dev"}
    else None,
)


def _resolve_cors_origins() -> list[str]:
    raw = settings.cors_allow_origins.strip()
    if not raw:
        return ["http://localhost:3000"]
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["http://localhost:3000"]


def _resolve_csv_list(raw: str, default_values: list[str]) -> list[str]:
    parsed = [value.strip() for value in raw.split(",") if value.strip()]
    return parsed or default_values


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=_resolve_csv_list(
        settings.cors_allow_methods,
        ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    ),
    allow_headers=_resolve_csv_list(
        settings.cors_allow_headers,
        ["Content-Type", "X-CSRF-Token", "X-API-Key"],
    ),
)


@app.middleware("http")
async def enforce_authenticated_api(request: Request, call_next):
    """Enforce strict session auth for every /api endpoint except login."""
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)
    excluded = {"/api/auth/login", "/api/auth/me", "/api/containers/restart-by-token"}
    if path.startswith("/api") and path not in excluded:
        try:
            get_current_auth_context(
                request=request,
                x_csrf_token=request.headers.get("x-csrf-token"),
            )
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


app.include_router(health.router, tags=["health"])
app.include_router(containers.router, prefix="/api/containers", tags=["containers"])
app.include_router(container_env.router, prefix="/api/containers", tags=["container-env"])
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(volumes.router, prefix="/api/volumes", tags=["volumes"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(commands.router, prefix="/api/commands", tags=["commands"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
