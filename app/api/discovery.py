"""
Discovery trigger endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/run")
async def trigger_discovery(background_tasks: BackgroundTasks) -> dict:
    """Manually trigger topology discovery in the background."""
    from app.services.discovery import run_discovery
    background_tasks.add_task(run_discovery)
    return {"status": "discovery started", "message": "Check /api/devices in a few seconds"}
