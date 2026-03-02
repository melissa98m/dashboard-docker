"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """Liveness/readiness check."""
    return {"status": "ok"}
