"""
Devices API endpoints.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Alert, Device, DeviceStatus, DeviceType, Interface, InterfaceStatus, TopologyLink
from app.db.session import get_db

router = APIRouter(prefix="/devices", tags=["devices"])
settings = get_settings()


class DeviceOut(BaseModel):
    id: int
    name: str
    ip_address: str
    device_type: str | None
    status: str | None
    vendor: str | None
    model: str | None
    software_version: str | None
    is_bootstrap: bool
    access_profile: str | None
    ssh_port: int
    last_seen: str | None
    last_polled: str | None

    model_config = {"from_attributes": True}


class CiscoDeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ip_address: str = Field(min_length=1, max_length=64)
    access_profile: str = Field(min_length=1, max_length=128)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    description: str | None = Field(default=None, max_length=2000)
    is_bootstrap: bool = True


class DeviceSummaryStatsOut(BaseModel):
    total_devices: int
    bootstrap_devices: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_access_profile: dict[str, int]


class DeviceStatsOut(BaseModel):
    device_id: int
    name: str
    ip_address: str
    access_profile: str | None
    is_bootstrap: bool
    status: str | None
    interfaces_total: int
    interfaces_up: int
    interfaces_down: int
    interfaces_admin_down: int
    interfaces_unknown: int
    active_alerts: int
    topology_links: int
    total_in_errors: int
    total_out_errors: int
    total_in_discards: int
    total_out_discards: int


def _device_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        ip_address=device.ip_address,
        device_type=device.device_type.value if device.device_type else None,
        status=device.status.value if device.status else None,
        vendor=device.vendor,
        model=device.model,
        software_version=device.software_version,
        is_bootstrap=device.is_bootstrap,
        access_profile=device.access_profile,
        ssh_port=device.ssh_port,
        last_seen=device.last_seen.isoformat() if device.last_seen else None,
        last_polled=device.last_polled.isoformat() if device.last_polled else None,
    )


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    bootstrap_only: bool = False,
) -> Any:
    """List all discovered devices."""
    query = select(Device).offset(skip).limit(limit)
    if bootstrap_only:
        query = query.where(Device.is_bootstrap.is_(True))
    result = await db.execute(query)
    devices = result.scalars().all()
    return [_device_out(d) for d in devices]


@router.get("/stats/summary", response_model=DeviceSummaryStatsOut)
async def get_devices_summary(db: AsyncSession = Depends(get_db)) -> Any:
    """Return aggregated inventory statistics."""
    result = await db.execute(select(Device))
    devices = list(result.scalars().all())

    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_access_profile: dict[str, int] = {}

    for device in devices:
        status_key = device.status.value if device.status else "unknown"
        type_key = device.device_type.value if device.device_type else "unknown"
        profile_key = device.access_profile or "unassigned"
        by_status[status_key] = by_status.get(status_key, 0) + 1
        by_type[type_key] = by_type.get(type_key, 0) + 1
        by_access_profile[profile_key] = by_access_profile.get(profile_key, 0) + 1

    return DeviceSummaryStatsOut(
        total_devices=len(devices),
        bootstrap_devices=sum(1 for device in devices if device.is_bootstrap),
        by_status=by_status,
        by_type=by_type,
        by_access_profile=by_access_profile,
    )


@router.post(
    "/cisco",
    response_model=DeviceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_cisco_device(
    payload: CiscoDeviceCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create or update a managed Cisco device/seed using a named access profile."""
    if settings.resolve_cisco_profile(payload.access_profile) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown Cisco access profile: {payload.access_profile}",
        )
    profile = settings.resolve_cisco_profile(payload.access_profile)

    result = await db.execute(
        select(Device).where(
            or_(
                Device.ip_address == payload.ip_address,
                Device.name == payload.name,
            )
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        device = Device(
            name=payload.name,
            ip_address=payload.ip_address,
            device_type=DeviceType.CISCO,
            access_profile=payload.access_profile,
            ssh_port=payload.ssh_port or profile.ssh_port,
            description=payload.description,
            is_bootstrap=payload.is_bootstrap,
        )
        db.add(device)
    else:
        device.name = payload.name
        device.ip_address = payload.ip_address
        device.device_type = DeviceType.CISCO
        device.access_profile = payload.access_profile
        device.ssh_port = payload.ssh_port or profile.ssh_port
        device.description = payload.description
        device.is_bootstrap = payload.is_bootstrap

    await db.commit()
    await db.refresh(device)
    from app.monitoring.scheduler import refresh_scheduler

    await refresh_scheduler()
    return _device_out(device)


@router.put("/cisco/{device_id}", response_model=DeviceOut)
async def update_cisco_device(
    device_id: int,
    payload: CiscoDeviceCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update an existing managed Cisco device."""
    if settings.resolve_cisco_profile(payload.access_profile) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown Cisco access profile: {payload.access_profile}",
        )

    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    if device.device_type != DeviceType.CISCO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Cisco devices can be updated via this endpoint",
        )

    profile = settings.resolve_cisco_profile(payload.access_profile)
    duplicate = await db.execute(
        select(Device).where(
            Device.id != device_id,
            or_(Device.name == payload.name, Device.ip_address == payload.ip_address),
        )
    )
    if duplicate.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another device already uses this name or IP address",
        )

    device.name = payload.name
    device.ip_address = payload.ip_address
    device.access_profile = payload.access_profile
    device.ssh_port = payload.ssh_port or profile.ssh_port
    device.description = payload.description
    device.is_bootstrap = payload.is_bootstrap

    await db.commit()
    await db.refresh(device)
    from app.monitoring.scheduler import refresh_scheduler

    await refresh_scheduler()
    return _device_out(device)


@router.delete("/cisco/{device_id}", status_code=status.HTTP_200_OK)
async def delete_cisco_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete a managed Cisco device."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    if device.device_type != DeviceType.CISCO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Cisco devices can be deleted via this endpoint",
        )

    deleted_name = device.name
    deleted_ip = device.ip_address
    await db.delete(device)
    await db.commit()

    from app.monitoring.scheduler import refresh_scheduler

    await refresh_scheduler()
    return {
        "status": "deleted",
        "device_id": device_id,
        "name": deleted_name,
        "ip_address": deleted_ip,
    }


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a specific device by ID."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return _device_out(device)


@router.get("/{device_id}/stats", response_model=DeviceStatsOut)
async def get_device_stats(
    device_id: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return detailed operational stats for one device."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    interfaces_result = await db.execute(
        select(Interface).where(Interface.device_id == device_id)
    )
    interfaces = list(interfaces_result.scalars().all())

    active_alerts = await db.scalar(
        select(func.count(Alert.id)).where(
            Alert.device_id == device_id,
            Alert.is_active.is_(True),
        )
    )
    topology_links = await db.scalar(
        select(func.count(TopologyLink.id)).where(
            TopologyLink.local_device_id == device_id
        )
    )

    return DeviceStatsOut(
        device_id=device.id,
        name=device.name,
        ip_address=device.ip_address,
        access_profile=device.access_profile,
        is_bootstrap=device.is_bootstrap,
        status=device.status.value if device.status else None,
        interfaces_total=len(interfaces),
        interfaces_up=sum(1 for iface in interfaces if iface.status == InterfaceStatus.UP),
        interfaces_down=sum(1 for iface in interfaces if iface.status == InterfaceStatus.DOWN),
        interfaces_admin_down=sum(
            1 for iface in interfaces if iface.status == InterfaceStatus.ADMIN_DOWN
        ),
        interfaces_unknown=sum(
            1 for iface in interfaces if iface.status == InterfaceStatus.UNKNOWN
        ),
        active_alerts=int(active_alerts or 0),
        topology_links=int(topology_links or 0),
        total_in_errors=sum(iface.in_errors for iface in interfaces),
        total_out_errors=sum(iface.out_errors for iface in interfaces),
        total_in_discards=sum(iface.in_discards for iface in interfaces),
        total_out_discards=sum(iface.out_discards for iface in interfaces),
    )
