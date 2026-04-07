"""create base schema

Revision ID: 20260408_0000
Revises:
Create Date: 2026-04-08 00:00:00
"""

from __future__ import annotations

from alembic import op

from app.db import Base
from app.models import (  # noqa: F401
    action_log,
    attachment,
    contact,
    email,
    mailbox_account,
    runtime_setting,
    session_token,
    task,
    user,
)


revision = "20260408_0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
