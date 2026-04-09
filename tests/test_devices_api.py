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

from app.db.models import Base
from app.db.session import async_engine
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
