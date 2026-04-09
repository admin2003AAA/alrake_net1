"""
Discovery trigger endpoint.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device, DeviceType, Interface, TopologyLink
from app.db.session import get_db

router = APIRouter(prefix="/discovery", tags=["discovery"])


class DiscoveryRunRequest(BaseModel):
    device_ids: list[int] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    access_profiles: list[str] = Field(default_factory=list)


class DiscoverySeedOut(BaseModel):
    name: str
    host: str
    access_profile: str
    ssh_port: int


class DiscoverySeedStatsOut(BaseModel):
    device_id: int
    name: str
    host: str
    access_profile: str | None
    status: str | None
    ssh_port: int
    last_polled: str | None
    interfaces_total: int
    topology_links: int


class DiscoveryStatsOut(BaseModel):
    bootstrap_devices_total: int
    by_access_profile: dict[str, int]
    seeds: list[DiscoverySeedStatsOut]


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


@router.get("/stats", response_model=DiscoveryStatsOut)
async def get_discovery_stats(db: AsyncSession = Depends(get_db)) -> Any:
    """Return precise statistics for bootstrap Cisco seeds."""
    result = await db.execute(
        select(Device).where(
            Device.device_type == DeviceType.CISCO,
            Device.is_bootstrap.is_(True),
        )
    )
    devices = list(result.scalars().all())

    by_access_profile: dict[str, int] = {}
    seeds: list[DiscoverySeedStatsOut] = []
    for device in devices:
        profile_key = device.access_profile or "unassigned"
        by_access_profile[profile_key] = by_access_profile.get(profile_key, 0) + 1

        interfaces_total = await db.scalar(
            select(func.count(Interface.id)).where(Interface.device_id == device.id)
        )
        topology_links = await db.scalar(
            select(func.count(TopologyLink.id)).where(
                TopologyLink.local_device_id == device.id
            )
        )
        seeds.append(
            DiscoverySeedStatsOut(
                device_id=device.id,
                name=device.name,
                host=device.ip_address,
                access_profile=device.access_profile,
                status=device.status.value if device.status else None,
                ssh_port=device.ssh_port,
                last_polled=device.last_polled.isoformat() if device.last_polled else None,
                interfaces_total=int(interfaces_total or 0),
                topology_links=int(topology_links or 0),
            )
        )

    return DiscoveryStatsOut(
        bootstrap_devices_total=len(devices),
        by_access_profile=by_access_profile,
        seeds=seeds,
    )


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
        access_profiles=payload.access_profiles or None,
    )
    return {
        "status": "discovery started",
        "device_ids": payload.device_ids,
        "hosts": payload.hosts,
        "access_profiles": payload.access_profiles,
        "message": "Check /api/devices and /api/topology in a few seconds",
    }
