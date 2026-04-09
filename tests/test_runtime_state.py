"""
Tests for Redis-backed runtime state helpers.
"""
from __future__ import annotations

import os

import pytest
from redis.exceptions import RedisError

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.services import runtime_state


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.storage:
            return None
        self.storage[key] = value
        return True

    async def get(self, key: str):
        return self.storage.get(key)

    async def delete(self, key: str):
        self.storage.pop(key, None)
        return 1

    async def ping(self):
        return True


class FailingRedis:
    async def set(self, *args, **kwargs):
        raise RedisError("redis unavailable")

    async def get(self, *args, **kwargs):
        raise RedisError("redis unavailable")

    async def delete(self, *args, **kwargs):
        raise RedisError("redis unavailable")

    async def ping(self):
        raise RedisError("redis unavailable")


@pytest.mark.asyncio
async def test_runtime_state_round_trip(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(runtime_state, "get_redis_client", lambda: fake)

    ok = await runtime_state.set_runtime_state("poller", {"status": "ok", "count": 2})
    data = await runtime_state.get_runtime_state("poller")

    assert ok is True
    assert data == {"status": "ok", "count": 2}


@pytest.mark.asyncio
async def test_alert_debounce_falls_back_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(runtime_state, "get_redis_client", lambda: FailingRedis())

    acquired = await runtime_state.acquire_alert_debounce("device:1", 60)

    assert acquired is True


@pytest.mark.asyncio
async def test_distributed_lock_blocks_second_holder(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(runtime_state, "get_redis_client", lambda: fake)

    async with runtime_state.distributed_lock("poller", 60) as first:
        async with runtime_state.distributed_lock("poller", 60) as second:
            assert first is True
            assert second is False
