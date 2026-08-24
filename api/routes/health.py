"""Health check endpoints."""

from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "northstar-sales-agent",
    }


@router.get("/readiness")
async def readiness_check():
    """Readiness check endpoint."""
    # TODO: Add checks for dependencies (DB, APIs, etc.)
    return {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat(),
    }
