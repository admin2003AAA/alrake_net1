"""
Base driver interface for all network device types.
Every vendor-specific driver must implement this abstract class.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterfaceInfo:
    """Represents a single interface collected from a device."""
    name: str
    description: str = ""
    status: str = "unknown"        # up / down / admin_down
    speed_mbps: int | None = None
    duplex: str | None = None
    vlan: str | None = None
    mac_address: str | None = None
    in_errors: int = 0
    out_errors: int = 0
    in_discards: int = 0
    out_discards: int = 0


@dataclass
class NeighborInfo:
    """Represents a discovered neighbor."""
    local_interface: str
    remote_hostname: str = ""
    remote_ip: str = ""
    remote_interface: str = ""
    remote_platform: str = ""
    protocol: str = "cdp"           # cdp / lldp


@dataclass
class DeviceInfo:
    """Summary information collected from a device."""
    hostname: str = ""
    vendor: str = ""
    model: str = ""
    software_version: str = ""
    serial_number: str = ""
    interfaces: list[InterfaceInfo] = field(default_factory=list)
    neighbors: list[NeighborInfo] = field(default_factory=list)
    arp_table: list[dict[str, str]] = field(default_factory=list)
    mac_table: list[dict[str, str]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class BaseDriver(abc.ABC):
    """Abstract base class for all device drivers."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        enable_password: str = "",
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.enable_password = enable_password
        self.timeout = timeout

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish connection to the device."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the device."""

    @abc.abstractmethod
    async def collect_device_info(self) -> DeviceInfo:
        """
        Collect full device information including interfaces,
        neighbors, ARP, and MAC tables.
        """

    @abc.abstractmethod
    async def get_interfaces(self) -> list[InterfaceInfo]:
        """Return current status of all interfaces."""

    @abc.abstractmethod
    async def get_neighbors(self) -> list[NeighborInfo]:
        """Return discovered neighbors (CDP/LLDP/etc)."""

    async def __aenter__(self) -> "BaseDriver":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()
