"""
Tests for multi-seed discovery target selection helpers.
"""
from __future__ import annotations

from app.services.discovery import _merge_seed_targets


def test_merge_seed_targets_prefers_db_bootstrap_device():
    configured = [
        {
            "device_id": None,
            "name": "core-1",
            "host": "10.0.0.1",
            "access_profile": "dc1",
            "ssh_port": 22,
        }
    ]
    db_targets = [
        {
            "device_id": 7,
            "name": "core-1-db",
            "host": "10.0.0.1",
            "access_profile": "dc2",
            "ssh_port": 2222,
        }
    ]

    merged = _merge_seed_targets(configured, db_targets)

    assert len(merged) == 1
    assert merged[0]["device_id"] == 7
    assert merged[0]["access_profile"] == "dc2"
    assert merged[0]["ssh_port"] == 2222


def test_merge_seed_targets_filters_by_hosts():
    configured = [
        {
            "device_id": None,
            "name": "core-1",
            "host": "10.0.0.1",
            "access_profile": "dc1",
            "ssh_port": 22,
        },
        {
            "device_id": None,
            "name": "core-2",
            "host": "10.0.0.2",
            "access_profile": "dc1",
            "ssh_port": 22,
        },
    ]

    merged = _merge_seed_targets(configured, [], hosts=["10.0.0.2"])

    assert len(merged) == 1
    assert merged[0]["host"] == "10.0.0.2"
