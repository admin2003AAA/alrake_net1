"""
Ubiquiti (airOS/airMAX/UniFi) driver stub.
Full implementation will use SNMP + SSH.
"""
from __future__ import annotations

import logging

from app.drivers.base import BaseDriver, DeviceInfo, InterfaceInfo, NeighborInfo

logger = logging.getLogger(__name__)


class UbiquitiSNMPDriver(BaseDriver):
    """
    Connects to Ubiquiti airOS / airMAX devices via SNMP.
    This is a stub implementation — full support coming in v2.

    To extend: use pysnmp / easysnmp to collect:
    - Interface status
    - Signal level / Noise / CCQ
    - Connected stations
    - Tx/Rx rates
    """

    def __init__(
        self,
        host: str,
        username: str = "",
        password: str = "",
        port: int = 161,
        enable_password: str = "",
        timeout: int = 30,
        community: str = "public",
        snmp_version: str = "2c",
    ) -> None:
        super().__init__(host, username, password, port, enable_password, timeout)
        self.community = community
        self.snmp_version = snmp_version

    async def connect(self) -> None:
        logger.info("[STUB] UBNT SNMP connect to %s (not yet implemented)", self.host)

    async def disconnect(self) -> None:
        logger.info("[STUB] UBNT SNMP disconnect from %s", self.host)

    async def collect_device_info(self) -> DeviceInfo:
        logger.warning(
            "[STUB] UBNT driver not fully implemented — returning empty DeviceInfo"
        )
        return DeviceInfo(hostname=self.host, vendor="Ubiquiti")

    async def get_interfaces(self) -> list[InterfaceInfo]:
        return []

    async def get_neighbors(self) -> list[NeighborInfo]:
        return []
