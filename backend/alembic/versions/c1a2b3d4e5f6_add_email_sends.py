"""add email_sends audit and idempotency table for Gmail sending.

Revision ID: c1a2b3d4e5f6
Revises: 96fc4d86d6e6
Create Date: 2026-11-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "96fc4d86d6e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_sends",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("sender_user_id", sa.String(), nullable=True),
        sa.Column("sender_mailbox", sa.String(length=191), nullable=False),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_email_sends_organization_idempotency_key",
        ),
    )
    op.create_index("ix_email_sends_organization_id", "email_sends", ["organization_id"])
    op.create_index("ix_email_sends_status", "email_sends", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_sends_status", table_name="email_sends")
    op.drop_index("ix_email_sends_organization_id", table_name="email_sends")
    op.drop_table("email_sends")