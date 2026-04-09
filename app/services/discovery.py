"""
Discovery Service
=================
Bootstraps topology discovery from the primary Cisco device.

Flow:
  1. Connect to bootstrap Cisco device via SSH.
  2. Collect device info (interfaces, CDP/LLDP neighbors, ARP, MAC table).
  3. Upsert bootstrap device in DB.
  4. For each discovered neighbor:
     a. Upsert device record.
     b. Upsert topology link.
     c. If auto-probe is enabled, attempt to connect and collect data.
  5. Save all interfaces to DB.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Device, DeviceType, DeviceStatus, Interface, InterfaceStatus, TopologyLink
from app.db.session import AsyncSessionLocal
from app.drivers.base import DeviceInfo, NeighborInfo
from app.drivers.cisco.ssh import CiscoSSHDriver

logger = logging.getLogger(__name__)

settings: Settings = get_settings()


def _classify_device_type(platform: str, hostname: str) -> DeviceType:
    """Heuristically determine device vendor from CDP/LLDP platform string."""
    combined = f"{platform} {hostname}".lower()
    if any(k in combined for k in ("cisco", "ios", "nx-os", "cat", "c9")):
        return DeviceType.CISCO
    if any(k in combined for k in ("mikrotik", "routeros", "chr")):
        return DeviceType.MIKROTIK
    if any(k in combined for k in ("ubnt", "ubiquiti", "airos", "airmax", "unifi")):
        return DeviceType.UBNT
    return DeviceType.UNKNOWN


def _vendor_label(device_type: DeviceType) -> str | None:
    mapping = {
        DeviceType.CISCO: "Cisco",
        DeviceType.MIKROTIK: "MikroTik",
        DeviceType.UBNT: "Ubiquiti",
    }
    return mapping.get(device_type)


async def _upsert_device(
    db: AsyncSession,
    ip: str,
    name: str,
    device_type: DeviceType = DeviceType.UNKNOWN,
    hostname: str | None = None,
    vendor: str | None = None,
    model: str | None = None,
    software_version: str | None = None,
    serial_number: str | None = None,
    is_bootstrap: bool = False,
) -> Device:
    """Insert or update a device record. Returns the device ORM object."""
    result = await db.execute(select(Device).where(Device.ip_address == ip))
    device = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if device is None:
        device = Device(
            ip_address=ip,
            name=name,
            hostname=hostname,
            device_type=device_type,
            status=DeviceStatus.UNKNOWN,
            vendor=vendor,
            model=model,
            software_version=software_version,
            serial_number=serial_number,
            is_bootstrap=is_bootstrap,
            last_seen=now,
        )
        db.add(device)
        await db.flush()
        logger.info("Created new device: %s (%s)", name, ip)
    else:
        if hostname:
            device.hostname = hostname
        if vendor:
            device.vendor = vendor
        if model:
            device.model = model
        if software_version:
            device.software_version = software_version
        if serial_number:
            device.serial_number = serial_number
        device.device_type = device_type
        device.last_seen = now
        if is_bootstrap:
            device.is_bootstrap = True
        await db.flush()
        logger.debug("Updated device: %s (%s)", name, ip)

    return device


async def _upsert_interfaces(
    db: AsyncSession, device: Device, device_info: DeviceInfo
) -> None:
    """Sync interfaces from collected data to DB."""
    now = datetime.now(timezone.utc)

    for iface_data in device_info.interfaces:
        result = await db.execute(
            select(Interface).where(
                Interface.device_id == device.id,
                Interface.name == iface_data.name,
            )
        )
        iface = result.scalar_one_or_none()

        status_map = {
            "up": InterfaceStatus.UP,
            "down": InterfaceStatus.DOWN,
            "admin_down": InterfaceStatus.ADMIN_DOWN,
        }
        status = status_map.get(iface_data.status, InterfaceStatus.UNKNOWN)

        if iface is None:
            iface = Interface(
                device_id=device.id,
                name=iface_data.name,
                description=iface_data.description,
                status=status,
                speed_mbps=iface_data.speed_mbps,
                duplex=iface_data.duplex,
                vlan=iface_data.vlan,
                mac_address=iface_data.mac_address,
                in_errors=iface_data.in_errors,
                out_errors=iface_data.out_errors,
                in_discards=iface_data.in_discards,
                out_discards=iface_data.out_discards,
                prev_in_errors=iface_data.in_errors,
                prev_out_errors=iface_data.out_errors,
                prev_in_discards=iface_data.in_discards,
                prev_out_discards=iface_data.out_discards,
                last_status_change=now,
            )
            db.add(iface)
        else:
            prev_status = iface.status
            # Store previous error counters for delta calculation
            iface.prev_in_errors = iface.in_errors
            iface.prev_out_errors = iface.out_errors
            iface.prev_in_discards = iface.in_discards
            iface.prev_out_discards = iface.out_discards

            iface.description = iface_data.description
            iface.status = status
            iface.speed_mbps = iface_data.speed_mbps
            iface.duplex = iface_data.duplex
            iface.vlan = iface_data.vlan
            iface.in_errors = iface_data.in_errors
            iface.out_errors = iface_data.out_errors
            iface.in_discards = iface_data.in_discards
            iface.out_discards = iface_data.out_discards

            if prev_status != status:
                iface.last_status_change = now

    await db.flush()


async def _upsert_topology_link(
    db: AsyncSession,
    local_device: Device,
    neighbor: NeighborInfo,
    remote_device: Device | None,
) -> None:
    """Upsert a topology link for a discovered neighbor."""
    result = await db.execute(
        select(TopologyLink).where(
            TopologyLink.local_device_id == local_device.id,
            TopologyLink.local_interface == neighbor.local_interface,
            TopologyLink.remote_hostname == neighbor.remote_hostname,
        )
    )
    link = result.scalar_one_or_none()

    if link is None:
        link = TopologyLink(
            local_device_id=local_device.id,
            local_interface=neighbor.local_interface,
            remote_device_id=remote_device.id if remote_device else None,
            remote_ip=neighbor.remote_ip,
            remote_hostname=neighbor.remote_hostname,
            remote_interface=neighbor.remote_interface,
            remote_platform=neighbor.remote_platform,
            protocol=neighbor.protocol,
            is_active=True,
        )
        db.add(link)
        logger.info(
            "New topology link: %s/%s -> %s",
            local_device.name,
            neighbor.local_interface,
            neighbor.remote_hostname,
        )
    else:
        link.is_active = True
        if remote_device:
            link.remote_device_id = remote_device.id
        link.remote_ip = neighbor.remote_ip
        link.remote_interface = neighbor.remote_interface

    await db.flush()


async def run_discovery() -> dict[str, int | str]:
    """
    Main discovery entry point.
    Connects to bootstrap Cisco and builds the topology.
    """
    logger.info("Starting topology discovery from bootstrap device: %s", settings.cisco_bootstrap_host)

    driver = CiscoSSHDriver(
        host=settings.cisco_bootstrap_host,
        username=settings.cisco_bootstrap_username,
        password=settings.cisco_bootstrap_password,
        port=settings.cisco_bootstrap_ssh_port,
        enable_password=settings.cisco_bootstrap_enable_password,
        device_type=settings.cisco_bootstrap_device_type,
        timeout=settings.ssh_timeout,
    )

    try:
        async with driver:
            device_info = await driver.collect_device_info()
    except Exception as exc:
        logger.error(
            "Failed to connect to bootstrap device %s: %s",
            settings.cisco_bootstrap_host,
            exc,
        )
        return {
            "bootstrap_host": settings.cisco_bootstrap_host,
            "interfaces_discovered": 0,
            "neighbors_discovered": 0,
            "devices_upserted": 0,
        }

    async with AsyncSessionLocal() as db:
        devices_upserted = 1
        # Upsert bootstrap device
        bootstrap = await _upsert_device(
            db=db,
            ip=settings.cisco_bootstrap_host,
            name=device_info.hostname or settings.cisco_bootstrap_name,
            device_type=DeviceType.CISCO,
            hostname=device_info.hostname,
            vendor=device_info.vendor,
            model=device_info.model,
            software_version=device_info.software_version,
            serial_number=device_info.serial_number,
            is_bootstrap=True,
        )
        bootstrap.status = DeviceStatus.UP
        bootstrap.last_polled = datetime.now(timezone.utc)

        # Upsert interfaces
        await _upsert_interfaces(db, bootstrap, device_info)

        # Process neighbors
        for neighbor in device_info.neighbors:
            if not neighbor.remote_ip and not neighbor.remote_hostname:
                continue

            dtype = _classify_device_type(
                neighbor.remote_platform, neighbor.remote_hostname
            )

            remote_device = None
            if neighbor.remote_ip:
                remote_device = await _upsert_device(
                    db=db,
                    ip=neighbor.remote_ip,
                    name=neighbor.remote_hostname or neighbor.remote_ip,
                    device_type=dtype,
                    hostname=neighbor.remote_hostname,
                    vendor=_vendor_label(dtype),
                )
                devices_upserted += 1

            await _upsert_topology_link(db, bootstrap, neighbor, remote_device)

        await db.commit()

    logger.info(
        "Discovery complete. Found %d interfaces and %d neighbors.",
        len(device_info.interfaces),
        len(device_info.neighbors),
    )
    return {
        "bootstrap_host": settings.cisco_bootstrap_host,
        "interfaces_discovered": len(device_info.interfaces),
        "neighbors_discovered": len(device_info.neighbors),
        "devices_upserted": devices_upserted,
    }
