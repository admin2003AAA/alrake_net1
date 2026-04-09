"""
Devices API endpoints.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Device, DeviceType
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
    return _device_out(device)


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
