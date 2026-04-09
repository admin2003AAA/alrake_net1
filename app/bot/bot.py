"""
Telegram Bot instance and message sender.
Uses aiogram 3.x.
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global Bot instance (initialized once at startup)
_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
        )
    return _bot


def get_dispatcher() -> Dispatcher:
    global _dp
    if _dp is None:
        _dp = Dispatcher()
        # Register handlers
        from app.bot import handlers
        handlers.register(_dp)
    return _dp


async def send_alert_message(text: str) -> None:
    """Send a message to the admin chat."""
    if not settings.telegram_admin_chat_id:
        logger.warning("TELEGRAM_ADMIN_CHAT_ID not set; skipping notification")
        return

    try:
        bot = get_bot()
        await bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text=text,
        )
        logger.debug("Telegram message sent to %s", settings.telegram_admin_chat_id)
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)


async def start_bot() -> None:
    """Start polling the Telegram Bot API."""
    bot = get_bot()
    dp = get_dispatcher()
    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


async def stop_bot() -> None:
    """Gracefully stop the bot."""
    global _bot
    if _bot is not None:
        await _bot.session.close()
        logger.info("Telegram bot stopped")
