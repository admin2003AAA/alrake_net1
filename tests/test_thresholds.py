"""
Tests for threshold evaluation logic.
These are pure unit tests — no DB or network needed.
"""
from __future__ import annotations

import os

# Minimal env so settings can be loaded
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "123456")
os.environ.setdefault("CISCO_BOOTSTRAP_HOST", "192.0.2.1")
os.environ.setdefault("CISCO_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("CISCO_BOOTSTRAP_PASSWORD", "secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("THRESHOLD_CCQ_MIN", "70")
os.environ.setdefault("THRESHOLD_SIGNAL_MIN", "-75")
os.environ.setdefault("THRESHOLD_PACKET_LOSS_PERCENT", "20")
os.environ.setdefault("THRESHOLD_INTERFACE_ERROR_RATE", "50")
os.environ.setdefault("THRESHOLD_INTERFACE_DISCARDS", "20")
os.environ.setdefault("THRESHOLD_RECONNECT_COUNT", "5")

from app.monitoring.thresholds import (
    is_ccq_low,
    is_discard_rate_high,
    is_error_rate_high,
    is_packet_loss_high,
    is_reconnect_count_high,
    is_signal_weak,
)
from app.monitoring.poller import _counter_delta


# ---------------------------------------------------------------------------
# CCQ
# ---------------------------------------------------------------------------

def test_ccq_below_threshold_is_low():
    assert is_ccq_low(50) is True


def test_ccq_at_threshold_is_ok():
    """Exactly at threshold should NOT be considered low."""
    assert is_ccq_low(70) is False


def test_ccq_above_threshold_is_ok():
    assert is_ccq_low(90) is False


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

def test_signal_below_threshold_is_weak():
    """Signal of -80 dBm is weaker than -75 threshold."""
    assert is_signal_weak(-80) is True


def test_signal_at_threshold_is_ok():
    assert is_signal_weak(-75) is False


def test_signal_above_threshold_is_ok():
    assert is_signal_weak(-60) is False


# ---------------------------------------------------------------------------
# Packet Loss
# ---------------------------------------------------------------------------

def test_packet_loss_above_threshold():
    assert is_packet_loss_high(25) is True


def test_packet_loss_at_threshold():
    assert is_packet_loss_high(20) is False


def test_packet_loss_below_threshold():
    assert is_packet_loss_high(10) is False


# ---------------------------------------------------------------------------
# Error rate
# ---------------------------------------------------------------------------

def test_error_rate_above_threshold():
    assert is_error_rate_high(100) is True


def test_error_rate_at_threshold():
    assert is_error_rate_high(50) is False


def test_error_rate_below_threshold():
    assert is_error_rate_high(10) is False


# ---------------------------------------------------------------------------
# Discard rate
# ---------------------------------------------------------------------------

def test_discard_rate_above_threshold():
    assert is_discard_rate_high(30) is True


def test_discard_rate_at_threshold():
    assert is_discard_rate_high(20) is False


# ---------------------------------------------------------------------------
# Reconnect count
# ---------------------------------------------------------------------------

def test_reconnect_count_above_threshold():
    assert is_reconnect_count_high(10) is True


def test_reconnect_count_at_threshold():
    assert is_reconnect_count_high(5) is False


def test_counter_delta_handles_reset():
    assert _counter_delta(100, 5) == 5


def test_counter_delta_handles_normal_increment():
    assert _counter_delta(100, 125) == 25
