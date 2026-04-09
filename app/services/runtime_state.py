"""
Redis-backed runtime state and distributed lock helpers.
Falls back gracefully when Redis is unavailable.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: Redis | None = None


def _state_key(name: str) -> str:
    return f"{settings.redis_key_prefix}:state:{name}"


def _lock_key(name: str) -> str:
    return f"{settings.redis_key_prefix}:lock:{name}"


def _alert_key(name: str) -> str:
    return f"{settings.redis_key_prefix}:alert:{name}"


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def ping_redis() -> bool:
    try:
        return bool(await get_redis_client().ping())
    except RedisError as exc:
        logger.debug("Redis ping failed: %s", exc)
        return False


async def set_runtime_state(name: str, payload: dict[str, Any]) -> bool:
    try:
        await get_redis_client().set(
            _state_key(name),
            json.dumps(payload, ensure_ascii=False, default=str),
            ex=settings.redis_state_ttl_seconds,
        )
        return True
    except RedisError as exc:
        logger.debug("Failed to set runtime state %s: %s", name, exc)
        return False


async def get_runtime_state(name: str) -> dict[str, Any] | None:
    try:
        value = await get_redis_client().get(_state_key(name))
    except RedisError as exc:
        logger.debug("Failed to get runtime state %s: %s", name, exc)
        return None
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


async def acquire_alert_debounce(key: str, ttl_seconds: int) -> bool:
    try:
        return bool(
            await get_redis_client().set(
                _alert_key(key),
                "1",
                ex=ttl_seconds,
                nx=True,
            )
        )
    except RedisError as exc:
        logger.debug("Redis debounce unavailable for %s: %s", key, exc)
        return True


async def clear_alert_debounce(key: str) -> None:
    try:
        await get_redis_client().delete(_alert_key(key))
    except RedisError as exc:
        logger.debug("Failed to clear alert debounce for %s: %s", key, exc)


@asynccontextmanager
async def distributed_lock(name: str, ttl_seconds: int) -> AsyncIterator[bool]:
    token = str(uuid4())
    key = _lock_key(name)
    acquired = False
    try:
        acquired = bool(
            await get_redis_client().set(
                key,
                token,
                ex=ttl_seconds,
                nx=True,
            )
        )
    except RedisError as exc:
        logger.debug("Redis lock unavailable for %s: %s", name, exc)
        acquired = True

    try:
        yield acquired
    finally:
        if not acquired:
            return
        try:
            current = await get_redis_client().get(key)
            if current == token:
                await get_redis_client().delete(key)
        except RedisError:
            return
