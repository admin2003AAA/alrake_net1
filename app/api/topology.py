"""
Topology API endpoints.
"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device, TopologyLink
from app.db.session import get_db

router = APIRouter(prefix="/topology", tags=["topology"])


class TopologyNodeOut(BaseModel):
    id: int
    name: str
    ip_address: str
    device_type: Optional[str]
    status: Optional[str]


class TopologyLinkOut(BaseModel):
    id: int
    local_device_id: int
    local_interface: Optional[str]
    remote_device_id: Optional[int]
    remote_ip: Optional[str]
    remote_hostname: Optional[str]
    remote_interface: Optional[str]
    remote_platform: Optional[str]
    protocol: str
    is_active: bool


class TopologyGraphOut(BaseModel):
    devices: List[TopologyNodeOut]
    links: List[TopologyLinkOut]


@router.get("", response_model=TopologyGraphOut)
async def get_topology(db: AsyncSession = Depends(get_db)) -> Any:
    device_result = await db.execute(select(Device).order_by(Device.name.asc()))
    link_result = await db.execute(
        select(TopologyLink).order_by(TopologyLink.local_device_id.asc(), TopologyLink.id.asc())
    )
    devices = list(device_result.scalars().all())
    links = list(link_result.scalars().all())
    return TopologyGraphOut(
        devices=[
            TopologyNodeOut(
                id=device.id,
                name=device.name,
                ip_address=device.ip_address,
                device_type=device.device_type.value if device.device_type else None,
                status=device.status.value if device.status else None,
            )
            for device in devices
        ],
        links=[
            TopologyLinkOut(
                id=link.id,
                local_device_id=link.local_device_id,
                local_interface=link.local_interface,
                remote_device_id=link.remote_device_id,
                remote_ip=link.remote_ip,
                remote_hostname=link.remote_hostname,
                remote_interface=link.remote_interface,
                remote_platform=link.remote_platform,
                protocol=link.protocol,
                is_active=link.is_active,
            )
            for link in links
        ],
    )
