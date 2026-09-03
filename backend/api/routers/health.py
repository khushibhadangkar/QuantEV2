"""
Health check router.

GET /api/v1/health  — liveness probe, returns service status and version.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check() -> HealthResponse:
    """Return the current liveness status of the EVision API."""
    return HealthResponse(
        status="ok",
        service="EVision API",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
