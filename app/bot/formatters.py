"""
Professional Telegram alert message formatters.
All messages are in Arabic with English technical terms.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Alert, AlertSeverity, AlertType, Device

# Emoji map per severity
SEVERITY_EMOJI = {
    AlertSeverity.CRITICAL: "🚨",
    AlertSeverity.WARNING: "⚠️",
    AlertSeverity.INFO: "ℹ️",
    AlertSeverity.RECOVERY: "✅",
}

# Alert type labels in Arabic
ALERT_TYPE_LABEL = {
    AlertType.INTERFACE_DOWN: "منفذ DOWN",
    AlertType.INTERFACE_UP: "منفذ UP (استعادة)",
    AlertType.DEVICE_DOWN: "جهاز غير متاح",
    AlertType.DEVICE_UP: "جهاز عاد للعمل",
    AlertType.HIGH_ERRORS: "ارتفاع أخطاء (Errors)",
    AlertType.HIGH_DISCARDS: "ارتفاع Discards",
    AlertType.NEIGHBOR_LOST: "فقدان Neighbor",
    AlertType.NEIGHBOR_RESTORED: "استعادة Neighbor",
    AlertType.LOW_CCQ: "انخفاض CCQ",
    AlertType.WEAK_SIGNAL: "إشارة ضعيفة",
    AlertType.HIGH_PACKET_LOSS: "Packet Loss مرتفع",
}

# Probable cause suggestions per alert type
PROBABLE_CAUSE = {
    AlertType.INTERFACE_DOWN: (
        "تحقق من الكابل / الجهاز المتصل على هذا المنفذ. "
        "قد يكون الجهاز مغلقًا أو انقطع الكابل."
    ),
    AlertType.DEVICE_DOWN: (
        "الجهاز غير متاح عبر الشبكة. "
        "تحقق من الطاقة والاتصال والبوابة الافتراضية."
    ),
    AlertType.HIGH_ERRORS: (
        "قد يكون بسبب تلف الكابل، duplex mismatch، أو تداخل كهرومغناطيسي."
    ),
    AlertType.HIGH_DISCARDS: (
        "قد يكون بسبب congestion في الشبكة، buffer overflow، أو إعدادات QoS."
    ),
    AlertType.NEIGHBOR_LOST: (
        "تحقق من حالة الجهاز المجاور وحالة البروتوكول (CDP/LLDP)."
    ),
    AlertType.LOW_CCQ: (
        "تداخل لاسلكي، مواءمة هوائي ضعيفة، أو عائق فيزيائي."
    ),
    AlertType.WEAK_SIGNAL: (
        "تحقق من مواءمة الهوائي، المسافة، أو وجود عوائق."
    ),
    AlertType.HIGH_PACKET_LOSS: (
        "تحقق من حالة الرابط، التداخل اللاسلكي، أو ازدحام الشبكة."
    ),
}


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_alert(device: Device, alert: Alert) -> str:
    """
    Format a professional Arabic/English alert message for Telegram.
    """
    emoji = SEVERITY_EMOJI.get(alert.severity, "🔔")
    type_label = ALERT_TYPE_LABEL.get(alert.alert_type, alert.alert_type.value)
    cause = PROBABLE_CAUSE.get(alert.alert_type, "")

    lines = [
        f"{emoji} *تنبيه شبكة — {type_label}*",
        "",
        f"🖥 *الجهاز:* `{device.name}`",
        f"🌐 *IP:* `{device.ip_address}`",
        f"🏷 *النوع:* {device.device_type.value.upper() if device.device_type else 'N/A'}",
    ]

    if device.model:
        lines.append(f"🔧 *الموديل:* {device.model}")

    if alert.interface_name:
        lines.append(f"🔌 *المنفذ:* `{alert.interface_name}`")

    if alert.details:
        lines.append(f"📝 *الوصف:* {alert.details}")

    lines += [
        "",
        f"❌ *المشكلة:* {alert.message}",
    ]

    if cause:
        lines.append(f"🔍 *السبب المرجح:* {cause}")

    lines += [
        "",
        f"🕒 *الوقت:* {_now_str()}",
        f"🆔 *Alert ID:* `{alert.id or 'N/A'}`",
    ]

    return "\n".join(lines)


def format_recovery(device: Device, alert: Alert) -> str:
    """Format a recovery / resolution message."""
    lines = [
        f"✅ *استعادة — {ALERT_TYPE_LABEL.get(alert.alert_type, alert.alert_type.value)}*",
        "",
        f"🖥 *الجهاز:* `{device.name}`",
        f"🌐 *IP:* `{device.ip_address}`",
    ]

    if alert.interface_name:
        lines.append(f"🔌 *المنفذ:* `{alert.interface_name}`")

    lines += [
        "",
        f"✔️ *التفاصيل:* {alert.message}",
        "",
        f"🕒 *الوقت:* {_now_str()}",
    ]

    return "\n".join(lines)


def format_device_summary(device: Device) -> str:
    """Format a device status summary message."""
    status_emoji = "🟢" if device.status and device.status.value == "up" else "🔴"
    lines = [
        f"📊 *معلومات الجهاز*",
        "",
        f"🖥 *الاسم:* `{device.name}`",
        f"🌐 *IP:* `{device.ip_address}`",
        f"{status_emoji} *الحالة:* {device.status.value.upper() if device.status else 'N/A'}",
        f"🏷 *النوع:* {device.device_type.value.upper() if device.device_type else 'N/A'}",
    ]
    if device.vendor:
        lines.append(f"🏭 *المصنّع:* {device.vendor}")
    if device.model:
        lines.append(f"🔧 *الموديل:* {device.model}")
    if device.software_version:
        lines.append(f"📦 *الإصدار:* {device.software_version}")
    if device.last_seen:
        lines.append(
            f"👁 *آخر ظهور:* {device.last_seen.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    return "\n".join(lines)
