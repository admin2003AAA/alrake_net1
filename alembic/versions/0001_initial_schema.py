"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-09 22:45:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


device_type_enum = sa.Enum("CISCO", "MIKROTIK", "UBNT", "UNKNOWN", name="devicetype")
device_status_enum = sa.Enum("UP", "DOWN", "UNREACHABLE", "UNKNOWN", name="devicestatus")
interface_status_enum = sa.Enum("UP", "DOWN", "ADMIN_DOWN", "UNKNOWN", name="interfacestatus")
alert_severity_enum = sa.Enum("INFO", "WARNING", "CRITICAL", "RECOVERY", name="alertseverity")
alert_type_enum = sa.Enum(
    "INTERFACE_DOWN",
    "INTERFACE_UP",
    "DEVICE_DOWN",
    "DEVICE_UP",
    "HIGH_ERRORS",
    "HIGH_DISCARDS",
    "NEIGHBOR_LOST",
    "NEIGHBOR_RESTORED",
    "LOW_CCQ",
    "WEAK_SIGNAL",
    "HIGH_PACKET_LOSS",
    name="alerttype",
)


def upgrade() -> None:
    bind = op.get_bind()
    device_type_enum.create(bind, checkfirst=True)
    device_status_enum.create(bind, checkfirst=True)
    interface_status_enum.create(bind, checkfirst=True)
    alert_severity_enum.create(bind, checkfirst=True)
    alert_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("device_type", device_type_enum, nullable=False, server_default="UNKNOWN"),
        sa.Column("status", device_status_enum, nullable=False, server_default="UNKNOWN"),
        sa.Column("is_bootstrap", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vendor", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("software_version", sa.String(length=256), nullable=True),
        sa.Column("serial_number", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("snmp_community", sa.String(length=128), nullable=True),
        sa.Column("snmp_port", sa.Integer(), nullable=False, server_default="161"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("ip_address"),
    )
    op.create_index("ix_devices_id", "devices", ["id"])
    op.create_index("ix_devices_name", "devices", ["name"])
    op.create_index("ix_devices_ip_address", "devices", ["ip_address"])

    op.create_table(
        "interfaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("status", interface_status_enum, nullable=False, server_default="UNKNOWN"),
        sa.Column("speed_mbps", sa.Integer(), nullable=True),
        sa.Column("duplex", sa.String(length=32), nullable=True),
        sa.Column("vlan", sa.String(length=64), nullable=True),
        sa.Column("mac_address", sa.String(length=32), nullable=True),
        sa.Column("in_errors", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("out_errors", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("in_discards", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("out_discards", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("prev_in_errors", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("prev_out_errors", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("prev_in_discards", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("prev_out_discards", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_status_change", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_interfaces_id", "interfaces", ["id"])
    op.create_index("ix_interfaces_device_id", "interfaces", ["device_id"])

    op.create_table(
        "topology_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("local_device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_interface", sa.String(length=128), nullable=True),
        sa.Column("remote_device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("remote_ip", sa.String(length=64), nullable=True),
        sa.Column("remote_hostname", sa.String(length=255), nullable=True),
        sa.Column("remote_interface", sa.String(length=128), nullable=True),
        sa.Column("remote_platform", sa.String(length=128), nullable=True),
        sa.Column("protocol", sa.String(length=16), nullable=False, server_default="cdp"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_topology_links_id", "topology_links", ["id"])
    op.create_index("ix_topology_links_local_device_id", "topology_links", ["local_device_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", alert_type_enum, nullable=False),
        sa.Column("severity", alert_severity_enum, nullable=False, server_default="WARNING"),
        sa.Column("interface_name", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dedup_key", sa.String(length=512), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_id", "alerts", ["id"])
    op.create_index("ix_alerts_device_id", "alerts", ["device_id"])
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["dedup_key"])

    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interface_name", sa.String(length=128), nullable=True),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_metrics_id", "metrics", ["id"])
    op.create_index("ix_metrics_device_id", "metrics", ["device_id"])
    op.create_index("ix_metrics_metric_name", "metrics", ["metric_name"])
    op.create_index("ix_metrics_recorded_at", "metrics", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_metrics_recorded_at", table_name="metrics")
    op.drop_index("ix_metrics_metric_name", table_name="metrics")
    op.drop_index("ix_metrics_device_id", table_name="metrics")
    op.drop_index("ix_metrics_id", table_name="metrics")
    op.drop_table("metrics")

    op.drop_index("ix_alerts_dedup_key", table_name="alerts")
    op.drop_index("ix_alerts_alert_type", table_name="alerts")
    op.drop_index("ix_alerts_device_id", table_name="alerts")
    op.drop_index("ix_alerts_id", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_topology_links_local_device_id", table_name="topology_links")
    op.drop_index("ix_topology_links_id", table_name="topology_links")
    op.drop_table("topology_links")

    op.drop_index("ix_interfaces_device_id", table_name="interfaces")
    op.drop_index("ix_interfaces_id", table_name="interfaces")
    op.drop_table("interfaces")

    op.drop_index("ix_devices_ip_address", table_name="devices")
    op.drop_index("ix_devices_name", table_name="devices")
    op.drop_index("ix_devices_id", table_name="devices")
    op.drop_table("devices")

    bind = op.get_bind()
    alert_type_enum.drop(bind, checkfirst=True)
    alert_severity_enum.drop(bind, checkfirst=True)
    interface_status_enum.drop(bind, checkfirst=True)
    device_status_enum.drop(bind, checkfirst=True)
    device_type_enum.drop(bind, checkfirst=True)
