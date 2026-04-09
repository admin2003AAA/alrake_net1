"""
Central configuration management using pydantic-settings.
All values are loaded from environment variables / .env file.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache

from pydantic import BaseModel, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CiscoAccessProfile(BaseModel):
    name: str
    username: str
    password: str
    enable_password: str = ""
    device_type: str = "cisco_ios"
    ssh_port: int = 22


class CiscoSeedDevice(BaseModel):
    name: str
    host: str
    access_profile: str = "default"
    ssh_port: int | None = None


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
    redis_key_prefix: str = "network_monitor"
    redis_state_ttl_seconds: int = 86400

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
    cisco_access_profiles_json: str = "[]"
    cisco_seed_devices_json: str = "[]"

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
    poll_concurrency: int = 10
    discovery_concurrency: int = 5
    ssh_timeout: int = 30
    ssh_retries: int = 3
    discovery_lock_seconds: int = 1800
    poll_lock_seconds: int = 300

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

    @field_validator(
        "app_port",
        "discovery_interval_seconds",
        "poll_interval_seconds",
        "poll_concurrency",
        "discovery_concurrency",
        "ssh_timeout",
        "ssh_retries",
        "alert_debounce_seconds",
        "recovery_grace_seconds",
        "max_alerts_per_device",
        "redis_state_ttl_seconds",
        "discovery_lock_seconds",
        "poll_lock_seconds",
    )
    @classmethod
    def validate_positive_ints(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("value must be greater than 0")
        return v

    def _parse_json_config(self, raw_value: str, field_name: str) -> list[dict]:
        try:
            payload = json.loads(raw_value or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must contain valid JSON") from exc
        if not isinstance(payload, list):
            raise ValueError(f"{field_name} must be a JSON array")
        return payload

    @property
    def cisco_access_profiles(self) -> dict[str, CiscoAccessProfile]:
        profiles: dict[str, CiscoAccessProfile] = {}

        if self.cisco_bootstrap_username and self.cisco_bootstrap_password:
            profiles["default"] = CiscoAccessProfile(
                name="default",
                username=self.cisco_bootstrap_username,
                password=self.cisco_bootstrap_password,
                enable_password=self.cisco_bootstrap_enable_password,
                device_type=self.cisco_bootstrap_device_type,
                ssh_port=self.cisco_bootstrap_ssh_port,
            )

        for item in self._parse_json_config(
            self.cisco_access_profiles_json,
            "CISCO_ACCESS_PROFILES_JSON",
        ):
            profile = CiscoAccessProfile.model_validate(item)
            profiles[profile.name] = profile

        if (
            "default" not in profiles
            and self.default_device_username
            and self.default_device_password
        ):
            profiles["default"] = CiscoAccessProfile(
                name="default",
                username=self.default_device_username,
                password=self.default_device_password,
                enable_password=self.default_device_enable_password,
                device_type=self.cisco_bootstrap_device_type,
                ssh_port=self.cisco_bootstrap_ssh_port,
            )

        return profiles

    @property
    def cisco_seed_devices(self) -> list[CiscoSeedDevice]:
        seeds: list[CiscoSeedDevice] = []
        seen_hosts: set[str] = set()

        if self.cisco_bootstrap_host:
            legacy_seed = CiscoSeedDevice(
                name=self.cisco_bootstrap_name,
                host=self.cisco_bootstrap_host,
                access_profile="default",
                ssh_port=self.cisco_bootstrap_ssh_port,
            )
            seeds.append(legacy_seed)
            seen_hosts.add(legacy_seed.host)

        for item in self._parse_json_config(
            self.cisco_seed_devices_json,
            "CISCO_SEED_DEVICES_JSON",
        ):
            seed = CiscoSeedDevice.model_validate(item)
            if seed.host in seen_hosts:
                continue
            seeds.append(seed)
            seen_hosts.add(seed.host)
        return seeds

    def resolve_cisco_profile(self, profile_name: str | None) -> CiscoAccessProfile | None:
        profiles = self.cisco_access_profiles
        if profile_name and profile_name in profiles:
            return profiles[profile_name]
        return profiles.get("default")

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
        if self.secret_key == "change_me_to_a_random_secret":
            errors.append("SECRET_KEY must be changed from the default placeholder")
        try:
            seeds = self.cisco_seed_devices
            profiles = self.cisco_access_profiles
        except (ValidationError, ValueError) as exc:
            errors.append(str(exc))
            seeds = []
            profiles = {}
        if not seeds:
            errors.append(
                "At least one Cisco bootstrap seed must be configured via legacy CISCO_BOOTSTRAP_* or CISCO_SEED_DEVICES_JSON"
            )
        if not profiles:
            errors.append(
                "At least one Cisco access profile must be configured via legacy CISCO_BOOTSTRAP_* credentials, DEFAULT_DEVICE_* credentials, or CISCO_ACCESS_PROFILES_JSON"
            )
        for seed in seeds:
            if seed.access_profile not in profiles:
                errors.append(
                    f"Cisco seed {seed.host} references unknown access profile: {seed.access_profile}"
                )

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
