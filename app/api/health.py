"""
Health check endpoint.
"""
from __future__ import annotations

import time
from typing import Dict, Any

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/status")
async def status() -> Dict[str, Any]:
    """Extended status with DB connectivity check."""
    from app.db.session import async_engine
    db_ok = False
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
