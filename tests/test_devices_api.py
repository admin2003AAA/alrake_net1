"""
Tests for managed Cisco device API endpoints.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.db.models import (
    Alert,
    AlertSeverity,
    AlertType,
    Base,
    Device,
    Interface,
    InterfaceStatus,
    TopologyLink,
)
from app.db.session import AsyncSessionLocal, async_engine
from app.main import app


async def _reset_db() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def client():
    asyncio.run(_reset_db())
    with TestClient(app) as c:
        yield c


def test_create_cisco_bootstrap_device(client):
    response = client.post(
        "/api/devices/cisco",
        json={
            "name": "edge-core-1",
            "ip_address": "10.10.10.1",
            "access_profile": "default",
            "ssh_port": 2222,
            "is_bootstrap": True,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "edge-core-1"
    assert data["ip_address"] == "10.10.10.1"
    assert data["access_profile"] == "default"
    assert data["ssh_port"] == 2222
    assert data["is_bootstrap"] is True


def test_list_bootstrap_devices_filter(client):
    client.post(
        "/api/devices/cisco",
        json={
            "name": "bootstrap-1",
            "ip_address": "10.10.10.10",
            "access_profile": "default",
            "is_bootstrap": True,
        },
    )
    client.post(
        "/api/devices/cisco",
        json={
            "name": "non-bootstrap-1",
            "ip_address": "10.10.10.20",
            "access_profile": "default",
            "is_bootstrap": False,
        },
    )

    response = client.get("/api/devices?bootstrap_only=true")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "bootstrap-1"


def test_update_cisco_device(client):
    created = client.post(
        "/api/devices/cisco",
        json={
            "name": "core-1",
            "ip_address": "10.0.0.1",
            "access_profile": "default",
            "ssh_port": 22,
            "is_bootstrap": True,
        },
    ).json()

    response = client.put(
        f"/api/devices/cisco/{created['id']}",
        json={
            "name": "core-1-renamed",
            "ip_address": "10.0.0.11",
            "access_profile": "default",
            "ssh_port": 2200,
            "is_bootstrap": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "core-1-renamed"
    assert data["ip_address"] == "10.0.0.11"
    assert data["ssh_port"] == 2200
    assert data["is_bootstrap"] is False


def test_delete_cisco_device(client):
    created = client.post(
        "/api/devices/cisco",
        json={
            "name": "core-delete",
            "ip_address": "10.0.0.50",
            "access_profile": "default",
            "is_bootstrap": True,
        },
    ).json()

    response = client.delete(f"/api/devices/cisco/{created['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    missing = client.get(f"/api/devices/{created['id']}")
    assert missing.status_code == 404


async def _seed_device_stats(device_id: int) -> None:
    async with AsyncSessionLocal() as db:
        device = await db.get(Device, device_id)
        device.description = "seed stats"
        db.add_all(
            [
                Interface(
                    device_id=device_id,
                    name="Gi0/1",
                    status=InterfaceStatus.UP,
                    in_errors=3,
                    out_errors=1,
                    in_discards=2,
                    out_discards=0,
                ),
                Interface(
                    device_id=device_id,
                    name="Gi0/2",
                    status=InterfaceStatus.DOWN,
                    in_errors=0,
                    out_errors=4,
                    in_discards=0,
                    out_discards=5,
                ),
                Alert(
                    device_id=device_id,
                    alert_type=AlertType.DEVICE_DOWN,
                    severity=AlertSeverity.CRITICAL,
                    message="down",
                    dedup_key=f"device:{device_id}:down",
                    is_active=True,
                ),
                TopologyLink(
                    local_device_id=device_id,
                    local_interface="Gi0/1",
                    remote_hostname="neighbor-1",
                    protocol="cdp",
                    is_active=True,
                ),
            ]
        )
        await db.commit()


def test_device_summary_and_device_stats_endpoints(client):
    created = client.post(
        "/api/devices/cisco",
        json={
            "name": "core-stats",
            "ip_address": "10.0.1.1",
            "access_profile": "default",
            "is_bootstrap": True,
        },
    ).json()
    asyncio.run(_seed_device_stats(created["id"]))

    summary = client.get("/api/devices/stats/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["total_devices"] >= 1
    assert summary_data["bootstrap_devices"] >= 1
    assert summary_data["by_access_profile"]["default"] >= 1

    device_stats = client.get(f"/api/devices/{created['id']}/stats")
    assert device_stats.status_code == 200
    stats_data = device_stats.json()
    assert stats_data["interfaces_total"] == 2
    assert stats_data["interfaces_up"] == 1
    assert stats_data["interfaces_down"] == 1
    assert stats_data["active_alerts"] == 1
    assert stats_data["topology_links"] == 1
    assert stats_data["total_in_errors"] == 3
    assert stats_data["total_out_errors"] == 5
