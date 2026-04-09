"""
Telegram bot command and message handlers.
"""
from __future__ import annotations

import logging
from typing import List

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, func

from app.config import get_settings
from app.db.models import Alert, Device, DeviceStatus
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    text = (
        "👋 *مرحبًا! أنا بوت مراقبة الشبكة*\n\n"
        "📡 أقوم بمراقبة أجهزة الشبكة وإرسال التنبيهات تلقائيًا.\n\n"
        "*الأوامر المتاحة:*\n"
        "/status — حالة النظام\n"
        "/devices — قائمة الأجهزة\n"
        "/alerts — آخر التنبيهات النشطة\n"
        "/discover — بدء اكتشاف الشبكة يدويًا\n"
        "/help — قائمة الأوامر"
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "📖 *قائمة الأوامر:*\n\n"
        "/status — حالة النظام والإحصائيات\n"
        "/devices — قائمة الأجهزة المكتشفة\n"
        "/alerts — آخر التنبيهات النشطة\n"
        "/discover — تشغيل اكتشاف الشبكة يدويًا\n"
    )
    await message.answer(text)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    async with AsyncSessionLocal() as db:
        device_count = await db.scalar(select(func.count()).select_from(Device))
        up_count = await db.scalar(
            select(func.count()).select_from(Device).where(
                Device.status == DeviceStatus.UP
            )
        )
        down_count = await db.scalar(
            select(func.count()).select_from(Device).where(
                Device.status == DeviceStatus.DOWN
            )
        )
        active_alerts = await db.scalar(
            select(func.count()).select_from(Alert).where(Alert.is_active == True)
        )

    text = (
        "📊 *حالة النظام*\n\n"
        f"🖥 إجمالي الأجهزة: *{device_count}*\n"
        f"🟢 أجهزة UP: *{up_count}*\n"
        f"🔴 أجهزة DOWN: *{down_count}*\n"
        f"🚨 تنبيهات نشطة: *{active_alerts}*\n"
    )
    await message.answer(text)


@router.message(Command("devices"))
async def cmd_devices(message: Message) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).limit(20))
        devices: List[Device] = list(result.scalars().all())

    if not devices:
        await message.answer("لا توجد أجهزة مكتشفة بعد. جرّب /discover أولًا.")
        return

    lines = ["📋 *الأجهزة المكتشفة:*\n"]
    for d in devices:
        status_emoji = "🟢" if d.status and d.status.value == "up" else "🔴"
        bootstrap = " ⭐" if d.is_bootstrap else ""
        lines.append(
            f"{status_emoji} `{d.name}` — `{d.ip_address}` "
            f"[{d.device_type.value.upper() if d.device_type else '?'}]{bootstrap}"
        )

    await message.answer("\n".join(lines))


@router.message(Command("alerts"))
async def cmd_alerts(message: Message) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert)
            .where(Alert.is_active == True)
            .order_by(Alert.fired_at.desc())
            .limit(10)
        )
        alerts: List[Alert] = list(result.scalars().all())

    if not alerts:
        await message.answer("✅ لا توجد تنبيهات نشطة حاليًا.")
        return

    lines = ["🚨 *آخر التنبيهات النشطة:*\n"]
    for a in alerts:
        lines.append(
            f"• [{a.severity.value.upper()}] {a.alert_type.value} — "
            f"جهاز ID: {a.device_id} / منفذ: {a.interface_name or 'N/A'}\n"
            f"  {a.fired_at.strftime('%Y-%m-%d %H:%M UTC') if a.fired_at else ''}"
        )

    await message.answer("\n".join(lines))


@router.message(Command("discover"))
async def cmd_discover(message: Message) -> None:
    await message.answer("🔍 جارٍ بدء اكتشاف الشبكة...")
    try:
        from app.services.discovery import run_discovery
        await run_discovery()
        await message.answer("✅ اكتمل الاكتشاف. استخدم /devices لرؤية الأجهزة.")
    except Exception as exc:
        logger.error("Discovery failed from bot command: %s", exc)
        await message.answer(f"❌ فشل الاكتشاف: `{exc}`")


def register(dp: Dispatcher) -> None:
    """Register all routers with the dispatcher."""
    dp.include_router(router)
