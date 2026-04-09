"""
Cisco SSH Driver using Netmiko.
Supports IOS, IOS-XE, and NX-OS device types.
Collects interfaces, CDP/LLDP neighbors, ARP, and MAC tables.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from app.drivers.base import BaseDriver, DeviceInfo, InterfaceInfo, NeighborInfo

logger = logging.getLogger(__name__)


class CiscoSSHDriver(BaseDriver):
    """
    Connects to a Cisco IOS/IOS-XE/NX-OS device via SSH using Netmiko
    (run in a thread executor to avoid blocking the event loop).
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        enable_password: str = "",
        device_type: str = "cisco_ios",
        timeout: int = 30,
    ) -> None:
        super().__init__(host, username, password, port, enable_password, timeout)
        self.device_type = device_type
        self._connection: Any = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open SSH connection in a thread pool."""
        await asyncio.get_event_loop().run_in_executor(None, self._connect_sync)

    def _connect_sync(self) -> None:
        try:
            from netmiko import ConnectHandler  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "netmiko is required for Cisco SSH. "
                "Install it with: pip install netmiko"
            ) from exc

        params: Dict[str, Any] = {
            "device_type": self.device_type,
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "timeout": self.timeout,
            "conn_timeout": self.timeout,
            "auth_timeout": self.timeout,
        }
        if self.enable_password:
            params["secret"] = self.enable_password

        logger.info("Connecting to Cisco device %s (%s)", self.host, self.device_type)
        self._connection = ConnectHandler(**params)
        if self.enable_password:
            self._connection.enable()
        logger.info("Connected to %s", self.host)

    async def disconnect(self) -> None:
        if self._connection is not None:
            await asyncio.get_event_loop().run_in_executor(
                None, self._disconnect_sync
            )

    def _disconnect_sync(self) -> None:
        try:
            if self._connection:
                self._connection.disconnect()
                logger.info("Disconnected from %s", self.host)
        except Exception as exc:
            logger.warning("Error disconnecting from %s: %s", self.host, exc)
        finally:
            self._connection = None

    # ------------------------------------------------------------------
    # High-level collection
    # ------------------------------------------------------------------

    async def collect_device_info(self) -> DeviceInfo:
        info = DeviceInfo()

        try:
            version_raw = await self._run_command("show version")
            self._parse_version(version_raw, info)
        except Exception as exc:
            logger.warning("Failed to get version from %s: %s", self.host, exc)

        try:
            info.interfaces = await self.get_interfaces()
        except Exception as exc:
            logger.warning("Failed to get interfaces from %s: %s", self.host, exc)

        try:
            info.neighbors = await self.get_neighbors()
        except Exception as exc:
            logger.warning("Failed to get neighbors from %s: %s", self.host, exc)

        try:
            info.arp_table = await self._get_arp_table()
        except Exception as exc:
            logger.warning("Failed to get ARP table from %s: %s", self.host, exc)

        try:
            info.mac_table = await self._get_mac_table()
        except Exception as exc:
            logger.warning("Failed to get MAC table from %s: %s", self.host, exc)

        return info

    # ------------------------------------------------------------------
    # Interfaces
    # ------------------------------------------------------------------

    async def get_interfaces(self) -> List[InterfaceInfo]:
        """Collect interface status and error counters."""
        status_raw = await self._run_command("show interfaces status")
        counters_raw = await self._run_command("show interfaces counters errors")
        return self._parse_interfaces(status_raw, counters_raw)

    def _parse_interfaces(
        self, status_output: str, counters_output: str
    ) -> List[InterfaceInfo]:
        interfaces: List[InterfaceInfo] = []

        # Parse "show interfaces status" output
        # Example line:
        # Gi1/0/1    uplink-core       connected    1         a-full a-1000 10/100/1000BaseTX
        for line in status_output.splitlines():
            m = re.match(
                r"^(\S+)\s+(.*?)\s+(connected|notconnect|disabled|err-disabled|"
                r"inactive|monitoring)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$",
                line.strip(),
            )
            if not m:
                continue
            intf_name = m.group(1)
            description = m.group(2).strip()
            raw_status = m.group(3).lower()
            vlan = m.group(4)
            duplex = m.group(5)
            speed = m.group(6)

            status_map = {
                "connected": "up",
                "notconnect": "down",
                "disabled": "admin_down",
                "err-disabled": "admin_down",
                "inactive": "down",
                "monitoring": "up",
            }
            status = status_map.get(raw_status, "unknown")

            speed_mbps: Optional[int] = None
            speed_match = re.search(r"(\d+)", speed)
            if speed_match:
                raw_speed = int(speed_match.group(1))
                # Cisco shows speed in Mbps (10, 100, 1000, 10000)
                speed_mbps = raw_speed

            iface = InterfaceInfo(
                name=intf_name,
                description=description,
                status=status,
                speed_mbps=speed_mbps,
                duplex=duplex if duplex != "auto" else None,
                vlan=vlan if vlan not in ("trunk", "routed") else None,
            )
            interfaces.append(iface)

        # Parse counters and merge
        error_map: Dict[str, Dict[str, int]] = {}
        # show interfaces counters errors format (IOS):
        # Port        Align-Err     FCS-Err    Xmit-Err    Rcv-Err  UnderSize OutDiscards
        for line in counters_output.splitlines():
            parts = line.split()
            if len(parts) >= 7 and re.match(r"^[A-Z][a-z]", parts[0]):
                try:
                    error_map[parts[0]] = {
                        "in_errors": int(parts[4]),
                        "out_errors": int(parts[3]),
                        "in_discards": 0,
                        "out_discards": int(parts[6]),
                    }
                except (ValueError, IndexError):
                    pass

        for iface in interfaces:
            if iface.name in error_map:
                e = error_map[iface.name]
                iface.in_errors = e.get("in_errors", 0)
                iface.out_errors = e.get("out_errors", 0)
                iface.in_discards = e.get("in_discards", 0)
                iface.out_discards = e.get("out_discards", 0)

        return interfaces

    # ------------------------------------------------------------------
    # Neighbors
    # ------------------------------------------------------------------

    async def get_neighbors(self) -> List[NeighborInfo]:
        neighbors: List[NeighborInfo] = []
        neighbors.extend(await self._get_cdp_neighbors())
        neighbors.extend(await self._get_lldp_neighbors())
        return neighbors

    async def _get_cdp_neighbors(self) -> List[NeighborInfo]:
        try:
            raw = await self._run_command("show cdp neighbors detail")
            return self._parse_cdp_neighbors(raw)
        except Exception as exc:
            logger.debug("CDP neighbors not available on %s: %s", self.host, exc)
            return []

    def _parse_cdp_neighbors(self, output: str) -> List[NeighborInfo]:
        neighbors: List[NeighborInfo] = []
        # Split on separator line
        blocks = re.split(r"-{5,}", output)
        for block in blocks:
            if not block.strip():
                continue
            device_id_m = re.search(r"Device ID:\s*(\S+)", block)
            if not device_id_m:
                continue
            hostname = device_id_m.group(1).strip()

            ip_m = re.search(r"IP(?:v4)? address:\s*(\d+\.\d+\.\d+\.\d+)", block)
            remote_ip = ip_m.group(1) if ip_m else ""

            platform_m = re.search(r"Platform:\s*(.+?),", block)
            platform = platform_m.group(1).strip() if platform_m else ""

            local_intf_m = re.search(
                r"Interface:\s*([^,]+),\s*Port ID \(outgoing port\):\s*(\S+)", block
            )
            local_intf = ""
            remote_intf = ""
            if local_intf_m:
                local_intf = local_intf_m.group(1).strip()
                remote_intf = local_intf_m.group(2).strip()

            neighbors.append(
                NeighborInfo(
                    local_interface=local_intf,
                    remote_hostname=hostname,
                    remote_ip=remote_ip,
                    remote_interface=remote_intf,
                    remote_platform=platform,
                    protocol="cdp",
                )
            )
        return neighbors

    async def _get_lldp_neighbors(self) -> List[NeighborInfo]:
        try:
            raw = await self._run_command("show lldp neighbors detail")
            return self._parse_lldp_neighbors(raw)
        except Exception as exc:
            logger.debug("LLDP neighbors not available on %s: %s", self.host, exc)
            return []

    def _parse_lldp_neighbors(self, output: str) -> List[NeighborInfo]:
        neighbors: List[NeighborInfo] = []
        blocks = re.split(r"-{5,}", output)
        for block in blocks:
            if not block.strip():
                continue
            sys_name_m = re.search(r"System Name:\s*(\S+)", block)
            if not sys_name_m:
                continue
            hostname = sys_name_m.group(1).strip()

            ip_m = re.search(r"IP:\s*(\d+\.\d+\.\d+\.\d+)", block)
            remote_ip = ip_m.group(1) if ip_m else ""

            local_intf_m = re.search(r"Local Intf:\s*(\S+)", block)
            local_intf = local_intf_m.group(1) if local_intf_m else ""

            port_id_m = re.search(r"Port id:\s*(\S+)", block)
            remote_intf = port_id_m.group(1) if port_id_m else ""

            system_desc_m = re.search(r"System Description:\s*(.+?)(?:\n|$)", block)
            platform = system_desc_m.group(1).strip() if system_desc_m else ""

            neighbors.append(
                NeighborInfo(
                    local_interface=local_intf,
                    remote_hostname=hostname,
                    remote_ip=remote_ip,
                    remote_interface=remote_intf,
                    remote_platform=platform,
                    protocol="lldp",
                )
            )
        return neighbors

    # ------------------------------------------------------------------
    # ARP
    # ------------------------------------------------------------------

    async def _get_arp_table(self) -> List[Dict[str, str]]:
        raw = await self._run_command("show ip arp")
        return self._parse_arp(raw)

    def _parse_arp(self, output: str) -> List[Dict[str, str]]:
        entries: List[Dict[str, str]] = []
        # Internet  10.0.0.1  -  aabb.cc00.0100  ARPA  GigabitEthernet0/0
        for line in output.splitlines():
            m = re.match(
                r"Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+"
                r"([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+\S+\s+(\S+)",
                line.strip(),
                re.IGNORECASE,
            )
            if m:
                entries.append(
                    {
                        "ip": m.group(1),
                        "mac": m.group(2),
                        "interface": m.group(3),
                    }
                )
        return entries

    # ------------------------------------------------------------------
    # MAC Table
    # ------------------------------------------------------------------

    async def _get_mac_table(self) -> List[Dict[str, str]]:
        raw = await self._run_command("show mac address-table")
        return self._parse_mac_table(raw)

    def _parse_mac_table(self, output: str) -> List[Dict[str, str]]:
        entries: List[Dict[str, str]] = []
        #   10  aabb.cc00.0100  DYNAMIC  Gi1/0/1
        for line in output.splitlines():
            m = re.match(
                r"\s*(\d+)\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+"
                r"(\S+)\s+(\S+)",
                line.strip(),
                re.IGNORECASE,
            )
            if m:
                entries.append(
                    {
                        "vlan": m.group(1),
                        "mac": m.group(2),
                        "type": m.group(3),
                        "interface": m.group(4),
                    }
                )
        return entries

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def _parse_version(self, output: str, info: DeviceInfo) -> None:
        hostname_m = re.search(r"^(\S+)\s+uptime", output, re.MULTILINE)
        if hostname_m:
            info.hostname = hostname_m.group(1)

        version_m = re.search(r"Cisco IOS.*?Version\s+(\S+)", output)
        if version_m:
            info.software_version = version_m.group(1)

        model_m = re.search(r"cisco\s+(\S+(?:\s+\S+)?)\s+\(", output, re.IGNORECASE)
        if model_m:
            info.model = model_m.group(1)
            info.vendor = "Cisco"

        serial_m = re.search(r"Processor board ID\s+(\S+)", output)
        if serial_m:
            info.serial_number = serial_m.group(1)

    # ------------------------------------------------------------------
    # Internal command runner
    # ------------------------------------------------------------------

    async def _run_command(self, command: str) -> str:
        """Run a command in a thread pool and return the output."""
        if self._connection is None:
            raise RuntimeError("Not connected")
        return await asyncio.get_event_loop().run_in_executor(
            None, self._run_command_sync, command
        )

    def _run_command_sync(self, command: str) -> str:
        logger.debug("Running command on %s: %s", self.host, command)
        output: str = self._connection.send_command(
            command,
            read_timeout=self.timeout,
        )
        return output
