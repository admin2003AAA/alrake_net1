"""
SQLAlchemy ORM models.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DeviceType(str, enum.Enum):
    CISCO = "cisco"
    MIKROTIK = "mikrotik"
    UBNT = "ubnt"
    UNKNOWN = "unknown"


class DeviceStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class InterfaceStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "admin_down"
    UNKNOWN = "unknown"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    RECOVERY = "recovery"


class AlertType(str, enum.Enum):
    INTERFACE_DOWN = "interface_down"
    INTERFACE_UP = "interface_up"
    DEVICE_DOWN = "device_down"
    DEVICE_UP = "device_up"
    HIGH_ERRORS = "high_errors"
    HIGH_DISCARDS = "high_discards"
    NEIGHBOR_LOST = "neighbor_lost"
    NEIGHBOR_RESTORED = "neighbor_restored"
    LOW_CCQ = "low_ccq"
    WEAK_SIGNAL = "weak_signal"
    HIGH_PACKET_LOSS = "high_packet_loss"


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_type: Mapped[DeviceType] = mapped_column(
        Enum(DeviceType), default=DeviceType.UNKNOWN
    )
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus), default=DeviceStatus.UNKNOWN
    )
    is_bootstrap: Mapped[bool] = mapped_column(Boolean, default=False)
    vendor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    software_version: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    snmp_community: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    snmp_port: Mapped[int] = mapped_column(Integer, default=161)
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_polled: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    interfaces: Mapped[List["Interface"]] = relationship(
        "Interface", back_populates="device", cascade="all, delete-orphan"
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert", back_populates="device", cascade="all, delete-orphan"
    )
    metrics: Mapped[List["Metric"]] = relationship(
        "Metric", back_populates="device", cascade="all, delete-orphan"
    )
    outgoing_links: Mapped[List["TopologyLink"]] = relationship(
        "TopologyLink",
        foreign_keys="TopologyLink.local_device_id",
        back_populates="local_device",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Device {self.name} ({self.ip_address})>"


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class Interface(Base):
    __tablename__ = "interfaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[InterfaceStatus] = mapped_column(
        Enum(InterfaceStatus), default=InterfaceStatus.UNKNOWN
    )
    speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duplex: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    vlan: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    in_errors: Mapped[int] = mapped_column(BigInteger, default=0)
    out_errors: Mapped[int] = mapped_column(BigInteger, default=0)
    in_discards: Mapped[int] = mapped_column(BigInteger, default=0)
    out_discards: Mapped[int] = mapped_column(BigInteger, default=0)
    prev_in_errors: Mapped[int] = mapped_column(BigInteger, default=0)
    prev_out_errors: Mapped[int] = mapped_column(BigInteger, default=0)
    prev_in_discards: Mapped[int] = mapped_column(BigInteger, default=0)
    prev_out_discards: Mapped[int] = mapped_column(BigInteger, default=0)
    last_status_change: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="interfaces")

    def __repr__(self) -> str:
        return f"<Interface {self.name} on device_id={self.device_id}>"


# ---------------------------------------------------------------------------
# TopologyLink
# ---------------------------------------------------------------------------


class TopologyLink(Base):
    __tablename__ = "topology_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    local_device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    local_interface: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    remote_device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    remote_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    remote_hostname: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    remote_interface: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    remote_platform: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    protocol: Mapped[str] = mapped_column(String(16), default="cdp")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    local_device: Mapped["Device"] = relationship(
        "Device",
        foreign_keys=[local_device_id],
        back_populates="outgoing_links",
    )

    def __repr__(self) -> str:
        return (
            f"<TopologyLink {self.local_device_id}/{self.local_interface} "
            f"-> {self.remote_hostname}>"
        )


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), index=True)
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity), default=AlertSeverity.WARNING
    )
    interface_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    dedup_key: Mapped[str] = mapped_column(String(512), index=True)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert {self.alert_type} device_id={self.device_id}>"


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    interface_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    metric_name: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relationships
    device: Mapped["Device"] = relationship("Device", back_populates="metrics")

    def __repr__(self) -> str:
        return (
            f"<Metric {self.metric_name}={self.value} device_id={self.device_id}>"
        )
