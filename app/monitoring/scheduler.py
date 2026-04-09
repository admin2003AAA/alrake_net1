"""
APScheduler-based background task scheduler.
Registers and manages periodic jobs for polling and discovery.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Device, DeviceType
from app.db.session import AsyncSessionLocal
from app.services.runtime_state import distributed_lock, set_runtime_state

logger = logging.getLogger(__name__)
settings = get_settings()

_scheduler: AsyncIOScheduler | None = None
DISCOVERY_JOB_PREFIX = "discovery:"
POLLER_JOB_PREFIX = "poller:"


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def _set_job_runtime_state(
    name: str,
    group_key: str,
    payload: dict[str, Any],
) -> None:
    await set_runtime_state(f"{name}:{group_key}", payload)
    await set_runtime_state(name, payload)


async def _discovery_job(group_key: str, access_profiles: list[str]) -> None:
    from app.services.discovery import run_discovery

    state_name = "discovery"
    async with distributed_lock(f"{state_name}:{group_key}", settings.discovery_lock_seconds) as acquired:
        if not acquired:
            logger.info("Skipping discovery job for %s because another instance holds the lock", group_key)
            return
        await _set_job_runtime_state(
            state_name,
            group_key,
            {
                "status": "running",
                "group": group_key,
                "access_profiles": access_profiles,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            summary = await run_discovery(access_profiles=access_profiles)
            await _set_job_runtime_state(
                state_name,
                group_key,
                {
                    "status": "ok",
                    "group": group_key,
                    "access_profiles": access_profiles,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                },
            )
        except Exception as exc:
            await _set_job_runtime_state(
                state_name,
                group_key,
                {
                    "status": "failed",
                    "group": group_key,
                    "access_profiles": access_profiles,
                    "error": str(exc),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error("Discovery job failed for %s: %s", group_key, exc)


async def _poll_job(
    group_key: str,
    access_profiles: list[str],
    include_unassigned: bool = False,
) -> None:
    from app.monitoring.poller import poll_all_devices

    state_name = "poller"
    async with distributed_lock(f"{state_name}:{group_key}", settings.poll_lock_seconds) as acquired:
        if not acquired:
            logger.info("Skipping poll job for %s because another instance holds the lock", group_key)
            return
        await _set_job_runtime_state(
            state_name,
            group_key,
            {
                "status": "running",
                "group": group_key,
                "access_profiles": access_profiles,
                "include_unassigned": include_unassigned,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            summary = await poll_all_devices(
                access_profiles=access_profiles or None,
                include_unassigned=include_unassigned,
            )
            await _set_job_runtime_state(
                state_name,
                group_key,
                {
                    "status": "ok",
                    "group": group_key,
                    "access_profiles": access_profiles,
                    "include_unassigned": include_unassigned,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "summary": summary,
                },
            )
        except Exception as exc:
            await _set_job_runtime_state(
                state_name,
                group_key,
                {
                    "status": "failed",
                    "group": group_key,
                    "access_profiles": access_profiles,
                    "include_unassigned": include_unassigned,
                    "error": str(exc),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error("Poll job failed for %s: %s", group_key, exc)


async def _resolve_schedule_groups() -> list[dict[str, Any]]:
    configured_seed_profiles = {seed.access_profile for seed in settings.cisco_seed_devices}
    profile_device_counts: dict[str, int] = {}
    profile_bootstrap_counts: dict[str, int] = {}
    unassigned_device_count = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Device.device_type, Device.access_profile, Device.is_bootstrap)
        )
        rows = result.all()

    for device_type, access_profile, is_bootstrap in rows:
        if device_type == DeviceType.CISCO and access_profile:
            profile_device_counts[access_profile] = profile_device_counts.get(access_profile, 0) + 1
            if is_bootstrap:
                profile_bootstrap_counts[access_profile] = (
                    profile_bootstrap_counts.get(access_profile, 0) + 1
                )
        else:
            unassigned_device_count += 1

    groups: list[dict[str, Any]] = []
    scheduled_profiles = sorted(
        configured_seed_profiles
        | set(profile_device_counts)
        | set(profile_bootstrap_counts)
    )

    for access_profile in scheduled_profiles:
        groups.append(
            {
                "group_key": f"profile:{access_profile}",
                "access_profiles": [access_profile],
                "include_unassigned": False,
                "has_discovery": settings.discovery_enabled
                and (
                    access_profile in configured_seed_profiles
                    or profile_bootstrap_counts.get(access_profile, 0) > 0
                ),
                "has_polling": profile_device_counts.get(access_profile, 0) > 0,
            }
        )

    if unassigned_device_count > 0:
        groups.append(
            {
                "group_key": "unassigned",
                "access_profiles": [],
                "include_unassigned": True,
                "has_discovery": False,
                "has_polling": True,
            }
        )

    return groups


def describe_scheduler_jobs() -> list[dict[str, Any]]:
    scheduler = get_scheduler()
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "group_key": job.kwargs.get("group_key"),
            "access_profiles": job.kwargs.get("access_profiles", []),
            "include_unassigned": bool(job.kwargs.get("include_unassigned", False)),
            "runtime_state_key": job.id,
        }
        for job in scheduler.get_jobs()
    ]


async def refresh_scheduler(start_if_needed: bool = False) -> dict[str, Any]:
    scheduler = get_scheduler()

    for job in list(scheduler.get_jobs()):
        if job.id.startswith(DISCOVERY_JOB_PREFIX) or job.id.startswith(POLLER_JOB_PREFIX):
            scheduler.remove_job(job.id)

    groups = await _resolve_schedule_groups()

    for group in groups:
        if group["has_discovery"]:
            scheduler.add_job(
                _discovery_job,
                trigger=IntervalTrigger(seconds=settings.discovery_interval_seconds),
                id=f"{DISCOVERY_JOB_PREFIX}{group['group_key']}",
                name=f"Topology Discovery [{group['group_key']}]",
                kwargs={
                    "group_key": group["group_key"],
                    "access_profiles": group["access_profiles"],
                },
                replace_existing=True,
                max_instances=1,
            )
        if group["has_polling"]:
            scheduler.add_job(
                _poll_job,
                trigger=IntervalTrigger(seconds=settings.poll_interval_seconds),
                id=f"{POLLER_JOB_PREFIX}{group['group_key']}",
                name=f"Device Poller [{group['group_key']}]",
                kwargs={
                    "group_key": group["group_key"],
                    "access_profiles": group["access_profiles"],
                    "include_unassigned": group["include_unassigned"],
                },
                replace_existing=True,
                max_instances=1,
            )

    if start_if_needed and not scheduler.running:
        scheduler.start()

    return {
        "groups": groups,
        "jobs": [job["id"] for job in describe_scheduler_jobs()],
        "scheduler_running": scheduler.running,
    }


async def start_scheduler() -> None:
    """Start the background scheduler with configured grouped jobs."""
    scheduler = get_scheduler()
    if scheduler.running:
        return

    summary = await refresh_scheduler(start_if_needed=True)
    logger.info("Scheduler started")
    logger.info("Scheduled jobs: %s", summary["jobs"])


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
