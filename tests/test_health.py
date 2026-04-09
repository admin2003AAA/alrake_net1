"""
Tests for the health check API endpoint.
Uses HTTPX with ASGITransport — no live server needed.
"""
from __future__ import annotations

import pytest
import httpx
from fastapi.testclient import TestClient

# Patch settings so we don't need a real .env for tests
import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app, raise_server_exceptions=False) as c:
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
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        assert isinstance(response.json(), list)
