"""
Alerts API endpoints.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert
from app.db.session import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    id: int
    device_id: int
    alert_type: str
    severity: str
    interface_name: str | None
    message: str
    is_active: bool
    fired_at: str | None
    resolved_at: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """List alerts. Use ?active_only=true to filter only active ones."""
    query = select(Alert).order_by(Alert.fired_at.desc()).offset(skip).limit(limit)
    if active_only:
        query = query.where(Alert.is_active == True)
    result = await db.execute(query)
    alerts = result.scalars().all()
    return [
        AlertOut(
            id=a.id,
            device_id=a.device_id,
            alert_type=a.alert_type.value,
            severity=a.severity.value,
            interface_name=a.interface_name,
            message=a.message,
            is_active=a.is_active,
            fired_at=a.fired_at.isoformat() if a.fired_at else None,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        )
        for a in alerts
    ]


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return AlertOut(
        id=alert.id,
        device_id=alert.device_id,
        alert_type=alert.alert_type.value,
        severity=alert.severity.value,
        interface_name=alert.interface_name,
        message=alert.message,
        is_active=alert.is_active,
        fired_at=alert.fired_at.isoformat() if alert.fired_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
    )
