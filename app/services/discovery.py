"""
Discovery Service
=================
Bootstraps topology discovery from one or more Cisco seed devices.

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

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CiscoAccessProfile, Settings, get_settings
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
    access_profile: str | None = None,
    ssh_port: int | None = None,
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
            access_profile=access_profile,
            ssh_port=ssh_port or 22,
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
        if access_profile:
            device.access_profile = access_profile
        if ssh_port:
            device.ssh_port = ssh_port
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


def _serialize_seed_target(
    name: str,
    host: str,
    access_profile: str,
    ssh_port: int,
    device_id: int | None = None,
) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "name": name,
        "host": host,
        "access_profile": access_profile,
        "ssh_port": ssh_port,
    }


def get_configured_seed_targets() -> list[dict[str, Any]]:
    return [
        _serialize_seed_target(
            name=seed.name,
            host=seed.host,
            access_profile=seed.access_profile,
            ssh_port=seed.ssh_port or settings.resolve_cisco_profile(seed.access_profile).ssh_port,
        )
        for seed in settings.cisco_seed_devices
        if settings.resolve_cisco_profile(seed.access_profile) is not None
    ]


async def _get_db_seed_targets(
    device_ids: list[int] | None = None,
    hosts: list[str] | None = None,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        query = select(Device).where(
            Device.is_bootstrap.is_(True),
            Device.device_type == DeviceType.CISCO,
        )
        result = await db.execute(query)
        devices = list(result.scalars().all())

    selected: list[dict[str, Any]] = []
    for device in devices:
        if device_ids and device.id not in device_ids:
            continue
        if hosts and device.ip_address not in hosts:
            continue
        selected.append(
            _serialize_seed_target(
                device_id=device.id,
                name=device.name,
                host=device.ip_address,
                access_profile=device.access_profile or "default",
                ssh_port=device.ssh_port,
            )
        )
    return selected


def _merge_seed_targets(
    configured_targets: list[dict[str, Any]],
    db_targets: list[dict[str, Any]],
    device_ids: list[int] | None = None,
    hosts: list[str] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for target in configured_targets:
        if hosts and target["host"] not in hosts:
            continue
        merged[target["host"]] = target
    for target in db_targets:
        merged[target["host"]] = target

    targets = list(merged.values())
    if hosts:
        targets = [target for target in targets if target["host"] in hosts]
    if device_ids:
        targets = [
            target for target in targets
            if target.get("device_id") in device_ids
        ]
    return sorted(targets, key=lambda target: (target["name"], target["host"]))


def _build_cisco_driver(
    host: str,
    ssh_port: int,
    profile: CiscoAccessProfile,
) -> CiscoSSHDriver:
    driver = CiscoSSHDriver(
        host=host,
        username=profile.username,
        password=profile.password,
        port=ssh_port,
        enable_password=profile.enable_password,
        device_type=profile.device_type,
        timeout=settings.ssh_timeout,
    )
    return driver


async def _run_discovery_for_target(target: dict[str, Any]) -> dict[str, Any]:
    profile = settings.resolve_cisco_profile(target["access_profile"])
    if profile is None:
        logger.warning(
            "Skipping discovery for %s because access profile %s is undefined",
            target["host"],
            target["access_profile"],
        )
        return {
            "bootstrap_host": target["host"],
            "bootstrap_name": target["name"],
            "access_profile": target["access_profile"],
            "interfaces_discovered": 0,
            "neighbors_discovered": 0,
            "devices_upserted": 0,
            "status": "skipped",
            "error": "missing access profile",
        }

    logger.info(
        "Starting topology discovery from bootstrap device: %s (%s)",
        target["host"],
        target["access_profile"],
    )
    driver = _build_cisco_driver(
        host=target["host"],
        ssh_port=target["ssh_port"],
        profile=profile,
    )

    try:
        async with driver:
            device_info = await driver.collect_device_info()
    except Exception as exc:
        logger.error(
            "Failed to connect to bootstrap device %s: %s",
            target["host"],
            exc,
        )
        return {
            "bootstrap_host": target["host"],
            "bootstrap_name": target["name"],
            "access_profile": target["access_profile"],
            "interfaces_discovered": 0,
            "neighbors_discovered": 0,
            "devices_upserted": 0,
            "status": "failed",
            "error": str(exc),
        }

    async with AsyncSessionLocal() as db:
        devices_upserted = 1
        bootstrap = await _upsert_device(
            db=db,
            ip=target["host"],
            name=device_info.hostname or target["name"],
            device_type=DeviceType.CISCO,
            hostname=device_info.hostname,
            vendor=device_info.vendor,
            model=device_info.model,
            software_version=device_info.software_version,
            serial_number=device_info.serial_number,
            is_bootstrap=True,
            access_profile=target["access_profile"],
            ssh_port=target["ssh_port"],
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
                    access_profile=bootstrap.access_profile if dtype == DeviceType.CISCO else None,
                    ssh_port=bootstrap.ssh_port if dtype == DeviceType.CISCO else None,
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
        "bootstrap_host": target["host"],
        "bootstrap_name": bootstrap.name,
        "access_profile": target["access_profile"],
        "interfaces_discovered": len(device_info.interfaces),
        "neighbors_discovered": len(device_info.neighbors),
        "devices_upserted": devices_upserted,
        "status": "ok",
    }


async def run_discovery(
    device_ids: list[int] | None = None,
    hosts: list[str] | None = None,
    access_profiles: list[str] | None = None,
) -> dict[str, Any]:
    """
    Main discovery entry point.
    Connects to all configured/bootstrap Cisco seed devices and builds topology.
    """
    configured_targets = get_configured_seed_targets()
    db_targets = await _get_db_seed_targets(device_ids=device_ids, hosts=hosts)
    targets = _merge_seed_targets(
        configured_targets=configured_targets,
        db_targets=db_targets,
        device_ids=device_ids,
        hosts=hosts,
    )
    if access_profiles:
        targets = [
            target for target in targets if target["access_profile"] in access_profiles
        ]
    if not targets:
        return {
            "status": "skipped",
            "bootstrap_devices_total": 0,
            "successful_bootstrap_devices": 0,
            "failed_bootstrap_devices": 0,
            "access_profiles": access_profiles or [],
            "results": [],
        }

    concurrency = max(1, min(settings.discovery_concurrency, len(targets)))
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded_target_run(target: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _run_discovery_for_target(target)

    results = await asyncio.gather(*(_bounded_target_run(target) for target in targets))
    successful = sum(1 for result in results if result["status"] == "ok")
    failed = sum(1 for result in results if result["status"] == "failed")
    return {
        "status": "ok" if successful else "degraded",
        "bootstrap_devices_total": len(targets),
        "successful_bootstrap_devices": successful,
        "failed_bootstrap_devices": failed,
        "access_profiles": access_profiles or [],
        "results": results,
    }
