"""
Polling Service
===============
Polls all known devices on a schedule and evaluates thresholds.
Raises / resolves alerts based on current vs. previous state.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    Alert,
    AlertSeverity,
    AlertType,
    Device,
    DeviceStatus,
    DeviceType,
    Interface,
    InterfaceStatus,
)
from app.db.session import AsyncSessionLocal
from app.drivers.cisco.ssh import CiscoSSHDriver
from app.monitoring import alert_manager
from app.monitoring.thresholds import is_error_rate_high, is_discard_rate_high

logger = logging.getLogger(__name__)
settings = get_settings()


async def poll_device(device: Device) -> None:
    """Poll a single device: collect interfaces and evaluate alerts."""
    logger.debug("Polling device: %s (%s)", device.name, device.ip_address)

    if device.device_type == DeviceType.CISCO:
        await _poll_cisco(device)
    elif device.device_type == DeviceType.MIKROTIK:
        await _poll_mikrotik_stub(device)
    elif device.device_type == DeviceType.UBNT:
        await _poll_ubnt_stub(device)
    else:
        logger.debug("No driver for device type: %s", device.device_type)


async def _poll_cisco(device: Device) -> None:
    """Poll a Cisco device and evaluate interface alerts."""
    driver = CiscoSSHDriver(
        host=device.ip_address,
        username=settings.cisco_bootstrap_username,
        password=settings.cisco_bootstrap_password,
        port=device.ssh_port,
        enable_password=settings.cisco_bootstrap_enable_password,
        device_type=settings.cisco_bootstrap_device_type,
        timeout=settings.ssh_timeout,
    )

    try:
        async with driver:
            interfaces = await driver.get_interfaces()
    except Exception as exc:
        logger.warning("Cannot reach device %s: %s", device.name, exc)
        await _handle_device_unreachable(device)
        return

    async with AsyncSessionLocal() as db:
        device_obj = await db.get(Device, device.id)
        if device_obj is None:
            return

        prev_status = device_obj.status
        device_obj.status = DeviceStatus.UP
        device_obj.last_polled = datetime.now(timezone.utc)

        # Resolve device-down alert if device was down
        if prev_status == DeviceStatus.DOWN:
            await alert_manager.resolve_alert(
                device_obj,
                AlertType.DEVICE_DOWN,
                f"✅ الجهاز {device_obj.name} ({device_obj.ip_address}) عاد للعمل",
            )

        for iface_data in interfaces:
            result = await db.execute(
                select(Interface).where(
                    Interface.device_id == device_obj.id,
                    Interface.name == iface_data.name,
                )
            )
            iface = result.scalar_one_or_none()

            status_map = {
                "up": InterfaceStatus.UP,
                "down": InterfaceStatus.DOWN,
                "admin_down": InterfaceStatus.ADMIN_DOWN,
            }
            new_status = status_map.get(iface_data.status, InterfaceStatus.UNKNOWN)

            if iface is None:
                iface = Interface(
                    device_id=device_obj.id,
                    name=iface_data.name,
                    description=iface_data.description,
                    status=new_status,
                    in_errors=iface_data.in_errors,
                    out_errors=iface_data.out_errors,
                    in_discards=iface_data.in_discards,
                    out_discards=iface_data.out_discards,
                    prev_in_errors=iface_data.in_errors,
                    prev_out_errors=iface_data.out_errors,
                    prev_in_discards=iface_data.in_discards,
                    prev_out_discards=iface_data.out_discards,
                    last_status_change=datetime.now(timezone.utc),
                )
                db.add(iface)
                await db.flush()
            else:
                prev_iface_status = iface.status

                # Check for interface state changes
                if prev_iface_status == InterfaceStatus.UP and new_status == InterfaceStatus.DOWN:
                    await alert_manager.raise_alert(
                        device=device_obj,
                        alert_type=AlertType.INTERFACE_DOWN,
                        message=(
                            f"منفذ {iface.name} على الجهاز {device_obj.name} "
                            f"({device_obj.ip_address}) أصبح DOWN"
                        ),
                        severity=AlertSeverity.CRITICAL,
                        interface_name=iface.name,
                        details=iface.description or None,
                    )
                elif prev_iface_status == InterfaceStatus.DOWN and new_status == InterfaceStatus.UP:
                    await alert_manager.resolve_alert(
                        device=device_obj,
                        alert_type=AlertType.INTERFACE_DOWN,
                        recovery_message=(
                            f"✅ منفذ {iface.name} على الجهاز {device_obj.name} عاد للعمل"
                        ),
                        interface_name=iface.name,
                    )

                # Check error/discard deltas
                in_err_delta = max(0, iface_data.in_errors - iface.in_errors)
                out_err_delta = max(0, iface_data.out_errors - iface.out_errors)
                in_disc_delta = max(0, iface_data.in_discards - iface.in_discards)
                out_disc_delta = max(0, iface_data.out_discards - iface.out_discards)

                if is_error_rate_high(in_err_delta + out_err_delta):
                    await alert_manager.raise_alert(
                        device=device_obj,
                        alert_type=AlertType.HIGH_ERRORS,
                        message=(
                            f"ارتفاع أخطاء على منفذ {iface.name} "
                            f"({device_obj.name}): {in_err_delta + out_err_delta} errors"
                        ),
                        severity=AlertSeverity.WARNING,
                        interface_name=iface.name,
                    )

                if is_discard_rate_high(in_disc_delta + out_disc_delta):
                    await alert_manager.raise_alert(
                        device=device_obj,
                        alert_type=AlertType.HIGH_DISCARDS,
                        message=(
                            f"ارتفاع discards على منفذ {iface.name} "
                            f"({device_obj.name}): {in_disc_delta + out_disc_delta} discards"
                        ),
                        severity=AlertSeverity.WARNING,
                        interface_name=iface.name,
                    )

                # Update counters
                iface.prev_in_errors = iface.in_errors
                iface.prev_out_errors = iface.out_errors
                iface.prev_in_discards = iface.in_discards
                iface.prev_out_discards = iface.out_discards
                iface.in_errors = iface_data.in_errors
                iface.out_errors = iface_data.out_errors
                iface.in_discards = iface_data.in_discards
                iface.out_discards = iface_data.out_discards

                if prev_iface_status != new_status:
                    iface.last_status_change = datetime.now(timezone.utc)
                iface.status = new_status
                iface.description = iface_data.description

        await db.commit()


async def _handle_device_unreachable(device: Device) -> None:
    """Mark device as down and raise alert."""
    async with AsyncSessionLocal() as db:
        device_obj = await db.get(Device, device.id)
        if device_obj is None:
            return
        if device_obj.status != DeviceStatus.DOWN:
            device_obj.status = DeviceStatus.DOWN
            await db.commit()
            await alert_manager.raise_alert(
                device=device_obj,
                alert_type=AlertType.DEVICE_DOWN,
                message=(
                    f"الجهاز {device_obj.name} ({device_obj.ip_address}) "
                    f"غير متاح / لا يمكن الوصول إليه"
                ),
                severity=AlertSeverity.CRITICAL,
            )


async def _poll_mikrotik_stub(device: Device) -> None:
    """Placeholder polling for MikroTik devices."""
    logger.debug("MikroTik polling stub for %s (not implemented)", device.name)


async def _poll_ubnt_stub(device: Device) -> None:
    """Placeholder polling for UBNT devices."""
    logger.debug("UBNT polling stub for %s (not implemented)", device.name)


async def poll_all_devices() -> dict[str, int]:
    """Fetch all devices from DB and poll each one."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device))
        devices: list[Device] = sorted(
            list(result.scalars().all()),
            key=lambda device: (not device.is_bootstrap, device.id),
        )

    logger.info("Starting poll cycle for %d devices", len(devices))
    if not devices:
        return {"devices_total": 0, "poll_concurrency": 0}

    concurrency = max(1, min(settings.poll_concurrency, len(devices)))
    semaphore = asyncio.Semaphore(concurrency)
    failures = 0

    async def _bounded_poll(device: Device) -> None:
        nonlocal failures
        async with semaphore:
            try:
                await poll_device(device)
            except Exception as exc:
                failures += 1
                logger.error("Unhandled error polling device %s: %s", device.name, exc)

    await asyncio.gather(*(_bounded_poll(device) for device in devices))
    logger.info("Poll cycle complete")
    return {
        "devices_total": len(devices),
        "poll_concurrency": concurrency,
        "failures": failures,
    }
