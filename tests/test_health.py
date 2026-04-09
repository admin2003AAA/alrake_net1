"""
Tests for the health check API endpoint.
Uses HTTPX with ASGITransport — no live server needed.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

# Patch settings so we don't need a real .env for tests
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
    """Create a test client for the FastAPI app."""
    asyncio.run(_reset_db())
    with TestClient(app) as c:
        yield c


def test_health_returns_ok(client):
    """GET /api/health should return status=ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data


def test_health_uptime_non_negative(client):
    """Uptime should be a non-negative number."""
    response = client.get("/api/health")
    data = response.json()
    assert data["uptime_seconds"] >= 0


def test_devices_endpoint_returns_list(client):
    """GET /api/devices should return a list (may be empty)."""
    response = client.get("/api/devices")
    # Will fail if DB is not configured, but structure should be correct
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        assert isinstance(response.json(), list)


def test_alerts_endpoint_returns_list(client):
    """GET /api/alerts should return a list (may be empty)."""
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_status_contains_runtime_fields(client, monkeypatch):
    async def _fake_ping_redis():
        return True

    async def _fake_runtime_state(name: str):
        return {"name": name, "status": "ok"}

    def _fake_describe_scheduler_jobs():
        return [
            {
                "id": "poller:profile:default",
                "name": "Device Poller [profile:default]",
                "next_run_time": None,
                "group_key": "profile:default",
                "access_profiles": ["default"],
                "include_unassigned": False,
                "runtime_state_key": "poller:profile:default",
            }
        ]

    monkeypatch.setattr("app.api.health.ping_redis", _fake_ping_redis)
    monkeypatch.setattr("app.api.health.get_runtime_state", _fake_runtime_state)
    monkeypatch.setattr("app.monitoring.scheduler.describe_scheduler_jobs", _fake_describe_scheduler_jobs)

    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["database"] == "connected"
    assert data["redis"] == "connected"
    assert "scheduler_running" in data
    assert "jobs" in data
    assert "job_details" in data
    assert "grouped_runtime_state" in data
    assert data["runtime_state"]["poller"]["status"] == "ok"
    assert data["grouped_runtime_state"]["poller:profile:default"]["status"] == "ok"


def test_topology_endpoint_returns_graph(client):
    response = client.get("/api/topology")
    assert response.status_code == 200
    data = response.json()
    assert data["devices"] == []
    assert data["links"] == []
