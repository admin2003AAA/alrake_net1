"""
Tests for discovery stats API endpoints.
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

from app.db.models import Base, Device, DeviceStatus, DeviceType, Interface, TopologyLink
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


async def _seed_bootstrap_device() -> None:
    async with AsyncSessionLocal() as db:
        device = Device(
            name="seed-1",
            ip_address="10.0.2.1",
            device_type=DeviceType.CISCO,
            status=DeviceStatus.UP,
            is_bootstrap=True,
            access_profile="default",
            ssh_port=22,
        )
        db.add(device)
        await db.flush()
        db.add_all(
            [
                Interface(device_id=device.id, name="Gi0/1"),
                Interface(device_id=device.id, name="Gi0/2"),
                TopologyLink(
                    local_device_id=device.id,
                    local_interface="Gi0/1",
                    remote_hostname="neighbor-1",
                    protocol="cdp",
                    is_active=True,
                ),
            ]
        )
        await db.commit()


def test_discovery_stats_returns_seed_metrics(client):
    asyncio.run(_seed_bootstrap_device())

    response = client.get("/api/discovery/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["bootstrap_devices_total"] == 1
    assert data["by_access_profile"]["default"] == 1
    assert len(data["seeds"]) == 1
    assert data["seeds"][0]["interfaces_total"] == 2
    assert data["seeds"][0]["topology_links"] == 1
