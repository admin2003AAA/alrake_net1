"""
Tests for grouped scheduler resolution.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.db.models import Base, Device, DeviceType
from app.db.session import AsyncSessionLocal, async_engine
from app.monitoring import scheduler


async def _reset_db() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_resolve_schedule_groups_builds_profile_and_unassigned_groups():
    await _reset_db()
    async with AsyncSessionLocal() as db:
        db.add_all(
            [
                Device(
                    name="core-1",
                    ip_address="10.0.3.1",
                    device_type=DeviceType.CISCO,
                    access_profile="default",
                    is_bootstrap=True,
                ),
                Device(
                    name="core-2",
                    ip_address="10.0.3.2",
                    device_type=DeviceType.CISCO,
                    access_profile="default",
                    is_bootstrap=False,
                ),
                Device(
                    name="mt-1",
                    ip_address="10.0.3.3",
                    device_type=DeviceType.MIKROTIK,
                    is_bootstrap=False,
                ),
            ]
        )
        await db.commit()

    groups = await scheduler._resolve_schedule_groups()
    keys = {group["group_key"] for group in groups}

    assert "profile:default" in keys
    assert "unassigned" in keys
    default_group = next(group for group in groups if group["group_key"] == "profile:default")
    assert default_group["has_discovery"] is True
    assert default_group["has_polling"] is True
