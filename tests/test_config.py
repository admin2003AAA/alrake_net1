"""
Tests for multi-Cisco configuration parsing and validation.
"""
from __future__ import annotations

from app.config import Settings


def test_settings_parse_multiple_cisco_profiles_and_seeds():
    settings = Settings(
        telegram_bot_token="test:token",
        telegram_admin_chat_id="123456",
        secret_key="super-secret-key",
        database_url="sqlite+aiosqlite:///:memory:",
        database_sync_url="sqlite:///:memory:",
        cisco_bootstrap_host="",
        cisco_bootstrap_username="",
        cisco_bootstrap_password="",
        default_device_username="",
        default_device_password="",
        cisco_access_profiles_json=(
            '[{"name":"dc1","username":"admin1","password":"pass1","device_type":"cisco_ios","ssh_port":22},'
            '{"name":"dc2","username":"admin2","password":"pass2","device_type":"cisco_xe","ssh_port":2222}]'
        ),
        cisco_seed_devices_json=(
            '[{"name":"core-1","host":"10.0.0.1","access_profile":"dc1"},'
            '{"name":"core-2","host":"10.0.0.2","access_profile":"dc2","ssh_port":2200}]'
        ),
    )

    profiles = settings.cisco_access_profiles
    seeds = settings.cisco_seed_devices

    assert {"dc1", "dc2"}.issubset(set(profiles))
    assert profiles["dc2"].ssh_port == 2222
    assert len(seeds) == 2
    assert seeds[1].ssh_port == 2200
    assert settings.resolve_cisco_profile("dc1").username == "admin1"


def test_validate_required_for_run_accepts_multi_seed_configuration():
    settings = Settings(
        telegram_bot_token="test:token",
        telegram_admin_chat_id="123456",
        secret_key="super-secret-key",
        database_url="sqlite+aiosqlite:///:memory:",
        database_sync_url="sqlite:///:memory:",
        cisco_bootstrap_host="",
        cisco_bootstrap_username="",
        cisco_bootstrap_password="",
        default_device_username="",
        default_device_password="",
        cisco_access_profiles_json='[{"name":"dc1","username":"admin1","password":"pass1"}]',
        cisco_seed_devices_json='[{"name":"core-1","host":"10.0.0.1","access_profile":"dc1"}]',
    )

    settings.validate_required_for_run()
