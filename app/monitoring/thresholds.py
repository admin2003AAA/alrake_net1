"""
Threshold evaluation logic.
Each function returns True when a threshold is breached.
"""
from __future__ import annotations

from app.config import get_settings

settings = get_settings()


def is_ccq_low(ccq_percent: float) -> bool:
    """Return True if CCQ is below the configured minimum threshold."""
    return ccq_percent < settings.threshold_ccq_min


def is_signal_weak(signal_dbm: float) -> bool:
    """Return True if signal is weaker (more negative) than the threshold."""
    return signal_dbm < settings.threshold_signal_min


def is_packet_loss_high(loss_percent: float) -> bool:
    """Return True if packet loss percentage exceeds the threshold."""
    return loss_percent > settings.threshold_packet_loss_percent


def is_error_rate_high(error_delta: int) -> bool:
    """Return True if the number of new errors since last poll is too high."""
    return error_delta > settings.threshold_interface_error_rate


def is_discard_rate_high(discard_delta: int) -> bool:
    """Return True if the number of new discards since last poll is too high."""
    return discard_delta > settings.threshold_interface_discards


def is_reconnect_count_high(reconnect_count: int) -> bool:
    """Return True if the reconnect/flap count exceeds the threshold."""
    return reconnect_count > settings.threshold_reconnect_count
