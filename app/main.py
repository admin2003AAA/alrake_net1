"""
Network Monitor — Main Application Entry Point (FastAPI)
=========================================================
Starts:
  - FastAPI HTTP server (uvicorn)
  - Telegram Bot polling (aiogram)
  - APScheduler background tasks (polling + discovery)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    ),
)
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup + shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown lifecycle."""
    logger.info("Starting Network Monitor v1.0.0")

    # Start scheduler (polling + discovery)
    from app.monitoring.scheduler import start_scheduler, stop_scheduler
    start_scheduler()

    # Start Telegram bot in background
    bot_task = asyncio.create_task(_run_bot())

    logger.info(
        "Application startup complete. Listening on %s:%s",
        settings.app_host,
        settings.app_port,
    )

    yield  # Application runs here

    logger.info("Shutting down Network Monitor...")
    stop_scheduler()
    bot_task.cancel()
    try:
        await bot_task
    except (asyncio.CancelledError, Exception):
        pass
    from app.bot.bot import stop_bot
    await stop_bot()
    logger.info("Shutdown complete")


async def _run_bot() -> None:
    """Run aiogram bot polling as background task."""
    try:
        from app.bot.bot import start_bot
        await start_bot()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Telegram bot crashed: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Network Monitor",
    description="Professional network monitoring system with Telegram bot alerts",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

