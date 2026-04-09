"""
Health check endpoint.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.services.runtime_state import get_runtime_state, ping_redis

router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    """Extended status with DB connectivity check."""
    from app.db.session import async_engine
    from app.monitoring.scheduler import get_scheduler
    db_ok = False
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    redis_ok = await ping_redis()
    scheduler = get_scheduler()
    poller_state = await get_runtime_state("poller")
    discovery_state = await get_runtime_state("discovery")

    overall_ok = db_ok and redis_ok

    return {
        "status": "ok" if overall_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "redis": "connected" if redis_ok else "unreachable",
        "scheduler_running": scheduler.running,
        "jobs": [job.id for job in scheduler.get_jobs()],
        "runtime_state": {
            "poller": poller_state,
            "discovery": discovery_state,
        },
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
