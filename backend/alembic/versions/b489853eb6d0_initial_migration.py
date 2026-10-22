"""initial_migration

Revision ID: b489853eb6d0
Revises: 8bb9370c62c2
Create Date: 2026-10-19 20:52:03.165890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b489853eb6d0'
down_revision: Union[str, Sequence[str], None] = '8bb9370c62c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
