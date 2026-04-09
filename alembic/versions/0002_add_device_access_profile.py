"""add device access profile

Revision ID: 0002_add_device_access_profile
Revises: 0001_initial_schema
Create Date: 2026-04-09 22:58:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_device_access_profile"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("access_profile", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "access_profile")
