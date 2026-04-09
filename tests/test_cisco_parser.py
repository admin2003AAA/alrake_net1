"""
Tests for the Cisco SSH driver output parsers.
No live SSH connection needed — uses captured output strings.
"""
from __future__ import annotations

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")

from app.drivers.cisco.ssh import CiscoSSHDriver

# ---------------------------------------------------------------------------
# Sample output strings (from a real Cisco Catalyst)
# ---------------------------------------------------------------------------

SHOW_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   uplink-isp         connected    1          a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   sector-alpha       notconnect   1          auto    auto   10/100/1000BaseTX
Gi1/0/3   disabled-port      disabled     1          auto    auto   10/100/1000BaseTX
Gi1/0/4                      connected    trunk      a-full  a-1000 10/100/1000BaseTX
"""

SHOW_INTERFACES_COUNTERS_ERRORS = """\
Port        Align-Err     FCS-Err    Xmit-Err    Rcv-Err  UnderSize OutDiscards
Gi1/0/1             0           0           0          5          0          10
Gi1/0/2             0           0           0          0          0           0
Gi1/0/3             0           0           0          0          0           0
Gi1/0/4             0           0         100         80          0          30
"""

SHOW_CDP_NEIGHBORS_DETAIL = """\
-------------------------
Device ID: sw-floor-2.example.com
Entry address(es): 
  IP address: 10.1.1.2
Platform: cisco WS-C2960X-48FPD-L,  Capabilities: Switch IGMP 
Interface: GigabitEthernet1/0/4,  Port ID (outgoing port): GigabitEthernet0/1
...

-------------------------
Device ID: ubnt-sector-a
Entry address(es): 
  IP address: 10.1.1.10
Platform: Ubiquiti AirMAX AC,  Capabilities: Trans-Bridge 
Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): eth0
...
"""

SHOW_IP_ARP = """\
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.1.1.1                -   aabb.cc00.0100  ARPA   Vlan1
Internet  10.1.1.2               10   aabb.cc00.0200  ARPA   GigabitEthernet1/0/4
Internet  10.1.1.10              15   aabb.cc00.0a00  ARPA   GigabitEthernet1/0/2
"""

SHOW_VERSION = """\
Cisco IOS XE Software, Version 16.12.5
...
core-switch uptime is 10 weeks, 2 days, 3 hours, 14 minutes
...
cisco WS-C3750X-24T (PowerPC405) processor
...
Processor board ID FDO1234X5678
"""


# ---------------------------------------------------------------------------
# Helper: create a driver instance without connecting
# ---------------------------------------------------------------------------

def make_driver() -> CiscoSSHDriver:
    return CiscoSSHDriver(
        host="192.0.2.1",
        username="admin",
        password="secret",
        enable_password="enable",
    )


# ---------------------------------------------------------------------------
# Interface parser
# ---------------------------------------------------------------------------

def test_parse_interfaces_count():
    driver = make_driver()
    ifaces = driver._parse_interfaces(SHOW_INTERFACES_STATUS, SHOW_INTERFACES_COUNTERS_ERRORS)
    assert len(ifaces) == 4


def test_parse_interface_status_connected_is_up():
    driver = make_driver()
    ifaces = driver._parse_interfaces(SHOW_INTERFACES_STATUS, "")
    gi1 = next(i for i in ifaces if i.name == "Gi1/0/1")
    assert gi1.status == "up"


def test_parse_interface_status_notconnect_is_down():
    driver = make_driver()
    ifaces = driver._parse_interfaces(SHOW_INTERFACES_STATUS, "")
    gi2 = next(i for i in ifaces if i.name == "Gi1/0/2")
    assert gi2.status == "down"


def test_parse_interface_status_disabled_is_admin_down():
    driver = make_driver()
    ifaces = driver._parse_interfaces(SHOW_INTERFACES_STATUS, "")
    gi3 = next(i for i in ifaces if i.name == "Gi1/0/3")
    assert gi3.status == "admin_down"


def test_parse_interface_description():
    driver = make_driver()
    ifaces = driver._parse_interfaces(SHOW_INTERFACES_STATUS, "")
    gi1 = next(i for i in ifaces if i.name == "Gi1/0/1")
    assert "uplink-isp" in gi1.description


def test_parse_interface_error_counters():
    driver = make_driver()
    ifaces = driver._parse_interfaces(SHOW_INTERFACES_STATUS, SHOW_INTERFACES_COUNTERS_ERRORS)
    gi1 = next(i for i in ifaces if i.name == "Gi1/0/1")
    # in_errors = Rcv-Err = 5
    assert gi1.in_errors == 5
    # out_discards = OutDiscards = 10
    assert gi1.out_discards == 10


# ---------------------------------------------------------------------------
# CDP neighbor parser
# ---------------------------------------------------------------------------

def test_parse_cdp_neighbors_count():
    driver = make_driver()
    neighbors = driver._parse_cdp_neighbors(SHOW_CDP_NEIGHBORS_DETAIL)
    assert len(neighbors) == 2


def test_parse_cdp_neighbor_hostname():
    driver = make_driver()
    neighbors = driver._parse_cdp_neighbors(SHOW_CDP_NEIGHBORS_DETAIL)
    hostnames = [n.remote_hostname for n in neighbors]
    assert "sw-floor-2.example.com" in hostnames


def test_parse_cdp_neighbor_ip():
    driver = make_driver()
    neighbors = driver._parse_cdp_neighbors(SHOW_CDP_NEIGHBORS_DETAIL)
    ips = [n.remote_ip for n in neighbors]
    assert "10.1.1.2" in ips


def test_parse_cdp_neighbor_protocol():
    driver = make_driver()
    neighbors = driver._parse_cdp_neighbors(SHOW_CDP_NEIGHBORS_DETAIL)
    assert all(n.protocol == "cdp" for n in neighbors)


# ---------------------------------------------------------------------------
# ARP parser
# ---------------------------------------------------------------------------

def test_parse_arp_count():
    driver = make_driver()
    arp = driver._parse_arp(SHOW_IP_ARP)
    assert len(arp) == 3


def test_parse_arp_entry_fields():
    driver = make_driver()
    arp = driver._parse_arp(SHOW_IP_ARP)
    entry = next(e for e in arp if e["ip"] == "10.1.1.2")
    assert entry["mac"] == "aabb.cc00.0200"
    assert "GigabitEthernet" in entry["interface"]


# ---------------------------------------------------------------------------
# Version parser
# ---------------------------------------------------------------------------

def test_parse_version_hostname():
    from app.drivers.base import DeviceInfo
    driver = make_driver()
    info = DeviceInfo()
    driver._parse_version(SHOW_VERSION, info)
    assert info.hostname == "core-switch"


def test_parse_version_software():
    from app.drivers.base import DeviceInfo
    driver = make_driver()
    info = DeviceInfo()
    driver._parse_version(SHOW_VERSION, info)
    assert "16.12.5" in info.software_version


def test_parse_version_serial():
    from app.drivers.base import DeviceInfo
    driver = make_driver()
    info = DeviceInfo()
    driver._parse_version(SHOW_VERSION, info)
    assert "FDO1234X5678" in info.serial_number
