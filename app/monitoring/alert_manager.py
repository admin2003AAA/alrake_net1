"""
Alert Manager
=============
Responsible for:
  - Creating alerts with deduplication (same alert type + device + interface)
  - Debounce: do not re-send alerts within ALERT_DEBOUNCE_SECONDS
  - Recovery alerts: send "resolved" notification when issue clears
  - Sending Telegram notifications

Public API:
  alert_manager.raise_alert(...)   -- call when a problem is detected
  alert_manager.resolve_alert(...) -- call when a problem clears
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Alert, AlertSeverity, AlertType, Device
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()


def _make_dedup_key(
    device_id: int,
    alert_type: AlertType,
    interface_name: Optional[str] = None,
) -> str:
    """Build a unique key for alert deduplication."""
    parts = [str(device_id), alert_type.value]
    if interface_name:
        parts.append(interface_name)
    return ":".join(parts)


async def raise_alert(
    device: Device,
    alert_type: AlertType,
    message: str,
    severity: AlertSeverity = AlertSeverity.WARNING,
    interface_name: Optional[str] = None,
    details: Optional[str] = None,
) -> Optional[Alert]:
    """
    Create a new alert (if not already active) and trigger a Telegram notification.
    Implements debounce: will not re-fire if an identical active alert was sent
    within ALERT_DEBOUNCE_SECONDS.
    Returns the Alert object if a new alert was raised, else None.
    """
    dedup_key = _make_dedup_key(device.id, alert_type, interface_name)
    now = datetime.now(timezone.utc)
    debounce_cutoff = now - timedelta(seconds=settings.alert_debounce_seconds)

    async with AsyncSessionLocal() as db:
        # Check for an existing active alert within the debounce window
        result = await db.execute(
            select(Alert).where(
                and_(
                    Alert.dedup_key == dedup_key,
                    Alert.is_active == True,
                    Alert.last_sent_at >= debounce_cutoff,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            logger.debug(
                "Alert suppressed (debounce): %s for device %s",
                alert_type.value,
                device.name,
            )
            return None

        # Check for an existing active alert (to update rather than create new)
        result2 = await db.execute(
            select(Alert).where(
                and_(
                    Alert.dedup_key == dedup_key,
                    Alert.is_active == True,
                )
            )
        )
        alert = result2.scalar_one_or_none()

        if alert is None:
            alert = Alert(
                device_id=device.id,
                alert_type=alert_type,
                severity=severity,
                interface_name=interface_name,
                message=message,
                details=details,
                dedup_key=dedup_key,
                is_active=True,
                is_sent=False,
                fired_at=now,
            )
            db.add(alert)
            await db.flush()

        alert.last_sent_at = now
        alert.is_sent = True
        await db.commit()
        await db.refresh(alert)

    # Notify via Telegram (import here to avoid circular import)
    try:
        from app.bot.bot import send_alert_message
        from app.bot.formatters import format_alert

        text = format_alert(device, alert)
        await send_alert_message(text)
    except Exception as exc:
        logger.error("Failed to send Telegram alert: %s", exc)

    logger.info(
        "Alert raised: [%s] %s on device %s (interface: %s)",
        severity.value.upper(),
        alert_type.value,
        device.name,
        interface_name or "N/A",
    )
    return alert


async def resolve_alert(
    device: Device,
    alert_type: AlertType,
    recovery_message: str,
    interface_name: Optional[str] = None,
) -> None:
    """
    Mark active alert as resolved and send a recovery notification.
    Uses a grace period (RECOVERY_GRACE_SECONDS) to avoid flapping.
    """
    dedup_key = _make_dedup_key(device.id, alert_type, interface_name)
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert).where(
                and_(
                    Alert.dedup_key == dedup_key,
                    Alert.is_active == True,
                )
            )
        )
        alert = result.scalar_one_or_none()

        if alert is None:
            return

        # Check grace period: don't fire recovery if alert just started
        grace_cutoff = now - timedelta(seconds=settings.recovery_grace_seconds)
        if alert.fired_at > grace_cutoff:
            logger.debug(
                "Recovery suppressed (grace period): %s on %s",
                alert_type.value,
                device.name,
            )
            return

        alert.is_active = False
        alert.resolved_at = now
        await db.commit()

    # Send recovery notification
    try:
        from app.bot.bot import send_alert_message
        from app.bot.formatters import format_recovery

        _recovery_type_map = {
            AlertType.INTERFACE_DOWN: AlertType.INTERFACE_UP,
            AlertType.DEVICE_DOWN: AlertType.DEVICE_UP,
        }
        recovery_alert_type = _recovery_type_map.get(alert_type, alert_type)

        recovery_alert = Alert(
            device_id=device.id,
            alert_type=recovery_alert_type,
            severity=AlertSeverity.RECOVERY,
            interface_name=interface_name,
            message=recovery_message,
            dedup_key=dedup_key + ":recovery",
            fired_at=now,
        )
        text = format_recovery(device, recovery_alert)
        await send_alert_message(text)
    except Exception as exc:
        logger.error("Failed to send Telegram recovery: %s", exc)

    logger.info(
        "Alert resolved: %s on device %s (interface: %s)",
        alert_type.value,
        device.name,
        interface_name or "N/A",
    )
