"""
APScheduler-based background task scheduler.
Registers and manages periodic jobs for polling and discovery.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.services.runtime_state import distributed_lock, set_runtime_state

logger = logging.getLogger(__name__)
settings = get_settings()

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _discovery_job() -> None:
    from app.services.discovery import run_discovery
    async with distributed_lock("discovery", settings.discovery_lock_seconds) as acquired:
        if not acquired:
            logger.info("Skipping discovery job because another instance holds the lock")
            return
        await set_runtime_state(
            "discovery",
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            summary = await run_discovery()
            await set_runtime_state(
                "discovery",
                {
                    "status": "ok",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                },
            )
        except Exception as exc:
            await set_runtime_state(
                "discovery",
                {
                    "status": "failed",
                    "error": str(exc),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error("Discovery job failed: %s", exc)


async def _poll_job() -> None:
    from app.monitoring.poller import poll_all_devices
    async with distributed_lock("poller", settings.poll_lock_seconds) as acquired:
        if not acquired:
            logger.info("Skipping poll job because another instance holds the lock")
            return
        await set_runtime_state(
            "poller",
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            summary = await poll_all_devices()
            await set_runtime_state(
                "poller",
                {
                    "status": "ok",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                },
            )
        except Exception as exc:
            await set_runtime_state(
                "poller",
                {
                    "status": "failed",
                    "error": str(exc),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error("Poll job failed: %s", exc)


def start_scheduler() -> None:
    """Start the background scheduler with configured intervals."""
    scheduler = get_scheduler()
    if scheduler.running:
        return

    if settings.discovery_enabled:
        scheduler.add_job(
            _discovery_job,
            trigger=IntervalTrigger(seconds=settings.discovery_interval_seconds),
            id="discovery",
            name="Topology Discovery",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "Scheduled discovery every %ds", settings.discovery_interval_seconds
        )

    scheduler.add_job(
        _poll_job,
        trigger=IntervalTrigger(seconds=settings.poll_interval_seconds),
        id="poller",
        name="Device Poller",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled polling every %ds", settings.poll_interval_seconds)

    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
