"""Health check and service status endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    """Schema for health status response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    project: str
    environment: str
    debug: bool


@router.get("", response_model=HealthResponse)
async def check_health() -> HealthResponse:
    """Return application health and environment metadata."""
    return HealthResponse(
        status="healthy",
        project=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )
