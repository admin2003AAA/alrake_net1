"""
Tests for Telegram message formatters.
Pure unit tests — no network, DB, or bot needed.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Minimal env
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")

from app.bot.formatters import format_alert, format_recovery, format_device_summary
from app.db.models import Alert, AlertSeverity, AlertType, Device, DeviceStatus, DeviceType


def _make_device(**kwargs) -> Device:
    d = MagicMock(spec=Device)
    d.id = kwargs.get("id", 1)
    d.name = kwargs.get("name", "core-switch")
    d.ip_address = kwargs.get("ip_address", "10.0.0.1")
    d.device_type = kwargs.get("device_type", DeviceType.CISCO)
    d.status = kwargs.get("status", DeviceStatus.UP)
    d.vendor = kwargs.get("vendor", "Cisco")
    d.model = kwargs.get("model", "Catalyst 9300")
    d.software_version = kwargs.get("software_version", "16.12.5")
    d.is_bootstrap = kwargs.get("is_bootstrap", True)
    d.last_seen = kwargs.get("last_seen", datetime.now(timezone.utc))
    return d


def _make_alert(**kwargs) -> Alert:
    a = MagicMock(spec=Alert)
    a.id = kwargs.get("id", 42)
    a.device_id = kwargs.get("device_id", 1)
    a.alert_type = kwargs.get("alert_type", AlertType.INTERFACE_DOWN)
    a.severity = kwargs.get("severity", AlertSeverity.CRITICAL)
    a.interface_name = kwargs.get("interface_name", "GigabitEthernet1/0/1")
    a.message = kwargs.get("message", "Interface is down")
    a.details = kwargs.get("details", "Uplink to sector-alpha")
    a.is_active = kwargs.get("is_active", True)
    a.fired_at = kwargs.get("fired_at", datetime.now(timezone.utc))
    a.resolved_at = kwargs.get("resolved_at", None)
    return a


# ---------------------------------------------------------------------------
# format_alert
# ---------------------------------------------------------------------------

def test_format_alert_contains_device_name():
    device = _make_device()
    alert = _make_alert()
    text = format_alert(device, alert)
    assert "core-switch" in text


def test_format_alert_contains_ip():
    device = _make_device()
    alert = _make_alert()
    text = format_alert(device, alert)
    assert "10.0.0.1" in text


def test_format_alert_contains_interface_name():
    device = _make_device()
    alert = _make_alert(interface_name="Gi1/0/5")
    text = format_alert(device, alert)
    assert "Gi1/0/5" in text


def test_format_alert_contains_alert_type_label():
    device = _make_device()
    alert = _make_alert(alert_type=AlertType.INTERFACE_DOWN)
    text = format_alert(device, alert)
    assert "DOWN" in text.upper() or "منفذ" in text


def test_format_alert_critical_has_emoji():
    device = _make_device()
    alert = _make_alert(severity=AlertSeverity.CRITICAL)
    text = format_alert(device, alert)
    assert "🚨" in text


def test_format_alert_warning_has_emoji():
    device = _make_device()
    alert = _make_alert(severity=AlertSeverity.WARNING, alert_type=AlertType.HIGH_ERRORS)
    text = format_alert(device, alert)
    assert "⚠️" in text


def test_format_alert_no_interface_ok():
    """Alerts without interface_name should not crash."""
    device = _make_device()
    alert = _make_alert(alert_type=AlertType.DEVICE_DOWN, interface_name=None)
    text = format_alert(device, alert)
    assert "core-switch" in text


# ---------------------------------------------------------------------------
# format_recovery
# ---------------------------------------------------------------------------

def test_format_recovery_contains_check_mark():
    device = _make_device()
    alert = _make_alert(severity=AlertSeverity.RECOVERY)
    text = format_recovery(device, alert)
    assert "✅" in text


def test_format_recovery_contains_ip():
    device = _make_device()
    alert = _make_alert()
    text = format_recovery(device, alert)
    assert "10.0.0.1" in text


# ---------------------------------------------------------------------------
# format_device_summary
# ---------------------------------------------------------------------------

def test_format_device_summary_contains_name():
    device = _make_device()
    text = format_device_summary(device)
    assert "core-switch" in text


def test_format_device_summary_contains_ip():
    device = _make_device()
    text = format_device_summary(device)
    assert "10.0.0.1" in text


def test_format_device_summary_up_shows_green():
    device = _make_device(status=DeviceStatus.UP)
    text = format_device_summary(device)
    assert "🟢" in text


def test_format_device_summary_down_shows_red():
    device = _make_device(status=DeviceStatus.DOWN)
    text = format_device_summary(device)
    assert "🔴" in text
