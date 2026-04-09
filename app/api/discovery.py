"""
Discovery trigger endpoint.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

router = APIRouter(prefix="/discovery", tags=["discovery"])


class DiscoveryRunRequest(BaseModel):
    device_ids: list[int] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)


class DiscoverySeedOut(BaseModel):
    name: str
    host: str
    access_profile: str
    ssh_port: int


@router.get("/seeds", response_model=list[DiscoverySeedOut])
async def list_discovery_seeds() -> Any:
    """List configured Cisco seed devices without exposing secrets."""
    from app.services.discovery import get_configured_seed_targets

    targets = get_configured_seed_targets()
    return [
        DiscoverySeedOut(
            name=target["name"],
            host=target["host"],
            access_profile=target["access_profile"],
            ssh_port=target["ssh_port"],
        )
        for target in targets
    ]


@router.post("/run")
async def trigger_discovery(
    background_tasks: BackgroundTasks,
    payload: DiscoveryRunRequest | None = None,
) -> dict[str, Any]:
    """Manually trigger topology discovery in the background."""
    from app.services.discovery import run_discovery

    payload = payload or DiscoveryRunRequest()
    background_tasks.add_task(
        run_discovery,
        device_ids=payload.device_ids or None,
        hosts=payload.hosts or None,
    )
    return {
        "status": "discovery started",
        "device_ids": payload.device_ids,
        "hosts": payload.hosts,
        "message": "Check /api/devices and /api/topology in a few seconds",
    }
