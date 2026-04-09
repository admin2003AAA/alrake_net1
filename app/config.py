"""
Central configuration management using pydantic-settings.
All values are loaded from environment variables / .env file.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_env: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    secret_key: str = "change_me_to_a_random_secret"

    # -------------------------------------------------------------------------
    # Telegram
    # -------------------------------------------------------------------------
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/network_monitor"
    )
    database_sync_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/network_monitor"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # -------------------------------------------------------------------------
    # Cisco Bootstrap Device
    # -------------------------------------------------------------------------
    cisco_bootstrap_name: str = "core-switch"
    cisco_bootstrap_host: str = ""
    cisco_bootstrap_ssh_port: int = 22
    cisco_bootstrap_username: str = ""
    cisco_bootstrap_password: str = ""
    cisco_bootstrap_enable_password: str = ""
    cisco_bootstrap_device_type: str = "cisco_ios"

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------
    discovery_enabled: bool = True
    discovery_interval_seconds: int = 3600

    enable_cdp_discovery: bool = True
    enable_lldp_discovery: bool = True
    enable_arp_discovery: bool = True
    enable_mac_table_discovery: bool = True

    auto_probe_mikrotik: bool = True
    auto_probe_ubnt: bool = True
    auto_probe_cisco: bool = True

    default_device_username: str = ""
    default_device_password: str = ""
    default_device_enable_password: str = ""

    # -------------------------------------------------------------------------
    # Polling
    # -------------------------------------------------------------------------
    poll_interval_seconds: int = 60
    ssh_timeout: int = 30
    ssh_retries: int = 3

    # -------------------------------------------------------------------------
    # Alert Thresholds
    # -------------------------------------------------------------------------
    threshold_ccq_min: int = 70
    threshold_signal_min: int = -75
    threshold_packet_loss_percent: int = 20
    threshold_reconnect_count: int = 5
    threshold_interface_error_rate: int = 50
    threshold_interface_discards: int = 20

    # -------------------------------------------------------------------------
    # Alert Deduplication & Debounce
    # -------------------------------------------------------------------------
    alert_debounce_seconds: int = 300
    recovery_grace_seconds: int = 120
    max_alerts_per_device: int = 1000

    # -------------------------------------------------------------------------
    # MikroTik Defaults
    # -------------------------------------------------------------------------
    mikrotik_default_api_port: int = 8728
    mikrotik_default_api_ssl_port: int = 8729
    mikrotik_default_ssh_port: int = 22

    # -------------------------------------------------------------------------
    # UBNT Defaults
    # -------------------------------------------------------------------------
    ubnt_default_ssh_port: int = 22
    ubnt_default_snmp_port: int = 161
    ubnt_default_snmp_version: str = "2c"
    ubnt_default_snmp_community: str = "public"

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v

    def validate_required_for_run(self) -> None:
        """
        Check that the minimum required settings are configured.
        Called at application startup.
        """
        errors: list[str] = []

        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is not set")
        if not self.telegram_admin_chat_id:
            errors.append("TELEGRAM_ADMIN_CHAT_ID is not set")
        if not self.cisco_bootstrap_host:
            errors.append("CISCO_BOOTSTRAP_HOST is not set")
        if not self.cisco_bootstrap_username:
            errors.append("CISCO_BOOTSTRAP_USERNAME is not set")
        if not self.cisco_bootstrap_password:
            errors.append("CISCO_BOOTSTRAP_PASSWORD is not set")

        if errors:
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            raise SystemExit(
                f"Missing {len(errors)} required configuration value(s). "
                "Please review your .env file. See errors above."
            )

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
