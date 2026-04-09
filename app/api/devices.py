"""
Devices API endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device
from app.db.session import get_db

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceOut(BaseModel):
    id: int
    name: str
    ip_address: str
    device_type: Optional[str]
    status: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    software_version: Optional[str]
    is_bootstrap: bool
    last_seen: Optional[str]
    last_polled: Optional[str]

    model_config = {"from_attributes": True}


@router.get("", response_model=List[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """List all discovered devices."""
    result = await db.execute(select(Device).offset(skip).limit(limit))
    devices = result.scalars().all()
    return [
        DeviceOut(
            id=d.id,
            name=d.name,
            ip_address=d.ip_address,
            device_type=d.device_type.value if d.device_type else None,
            status=d.status.value if d.status else None,
            vendor=d.vendor,
            model=d.model,
            software_version=d.software_version,
            is_bootstrap=d.is_bootstrap,
            last_seen=d.last_seen.isoformat() if d.last_seen else None,
            last_polled=d.last_polled.isoformat() if d.last_polled else None,
        )
        for d in devices
    ]


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a specific device by ID."""
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
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
        last_seen=device.last_seen.isoformat() if device.last_seen else None,
        last_polled=device.last_polled.isoformat() if device.last_polled else None,
    )
