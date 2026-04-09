"""
MikroTik driver stub.
Full implementation will use the RouterOS API library.
Currently provides base structure and placeholder methods.
"""
from __future__ import annotations

import logging
from typing import List

from app.drivers.base import BaseDriver, DeviceInfo, InterfaceInfo, NeighborInfo

logger = logging.getLogger(__name__)


class MikroTikAPIDriver(BaseDriver):
    """
    Connects to MikroTik RouterOS via the RouterOS API (port 8728/8729).
    This is a stub implementation — full support coming in v2.

    To extend: implement _connect_sync / collect_device_info using
    the 'routeros-api' or 'librouteros' library.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 8728,
        enable_password: str = "",
        timeout: int = 30,
        use_ssl: bool = False,
    ) -> None:
        super().__init__(host, username, password, port, enable_password, timeout)
        self.use_ssl = use_ssl
        self._api: object = None

    async def connect(self) -> None:
        logger.info(
            "[STUB] MikroTik API connect to %s:%s (not yet implemented)",
            self.host,
            self.port,
        )

    async def disconnect(self) -> None:
        logger.info("[STUB] MikroTik API disconnect from %s", self.host)

    async def collect_device_info(self) -> DeviceInfo:
        logger.warning(
            "[STUB] MikroTik driver not fully implemented — returning empty DeviceInfo"
        )
        return DeviceInfo(hostname=self.host, vendor="MikroTik")

    async def get_interfaces(self) -> List[InterfaceInfo]:
        return []

    async def get_neighbors(self) -> List[NeighborInfo]:
        return []
