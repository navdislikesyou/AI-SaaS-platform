"""initial schema: organizations, users, refresh_tokens

Revision ID: a7d3c1e5b204
Revises: b489853eb6d0
Create Date: 2026-10-21

Why this revision exists
------------------------

The two earlier revisions in this directory (``8bb9370c62c2`` and
``b489853eb6d0``) are empty: their ``upgrade()`` bodies are ``pass``. They
were generated before ``alembic/env.py`` was bound to ``app.models.Base``, so
Alembic compared an empty target metadata against an empty database, saw no
difference, and wrote a revision that creates nothing.

They are left in place, unmodified, so the revision chain and any database
that already carries their ``alembic_version`` stamp stay valid. This revision
sits on top of them and creates the actual schema.

Creating tables conditionally
-----------------------------

Each table is created only when it is absent. That keeps ``alembic upgrade
head`` safe on a database that was built by ``Base.metadata.create_all`` (which
is what ``bootstrap_admin.py`` does) as well as on an empty one, so an operator
never has to choose between "the tables exist" and "the migration history is
correct".

The DDL mirrors ``app/models.py`` exactly: same column types, same nullability,
same unique constraints, and the same indexes. ``alembic check`` against a
migrated database reports no remaining differences.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d3c1e5b204"
down_revision: Union[str, Sequence[str], None] = "b489853eb6d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    """Return the names of the tables already present in the target database.

    In offline mode there is no connection to inspect, so nothing is reported
    as existing and the statements are emitted for a fresh database. That is
    the point of offline mode: the script is generated, not run.

    Returns:
        The set of table names the database already holds.
    """
    bind = op.get_bind()

    try:
        return set(sa.inspect(bind).get_table_names())
    except sa.exc.NoInspectionAvailable:
        return set()


def upgrade() -> None:
    """Create the organizations, users, and refresh_tokens tables."""
    existing = _existing_tables()

    if "organizations" not in existing:
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=191), nullable=False),
            sa.Column("slug", sa.String(length=191), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("email", sa.String(length=191), nullable=False),
            sa.Column("full_name", sa.String(length=191), nullable=False),
            sa.Column("hashed_password", sa.String(length=128), nullable=False),
            sa.Column(
                "role",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'employee'"),
            ),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("manager_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["manager_id"],
                ["users.id"],
                name=op.f("fk_users_manager_id_users"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["organization_id"],
                ["organizations.id"],
                name=op.f("fk_users_organization_id_organizations"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False)

    if "refresh_tokens" not in existing:
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["organization_id"],
                ["organizations.id"],
                name=op.f("fk_refresh_tokens_organization_id_organizations"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name=op.f("fk_refresh_tokens_user_id_users"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)
        op.create_index(
            "ix_refresh_tokens_token_hash",
            "refresh_tokens",
            ["token_hash"],
            unique=True,
        )
        op.create_index(
            "ix_refresh_tokens_user_id",
            "refresh_tokens",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop the tables created by this revision."""
    existing = _existing_tables()

    if "refresh_tokens" in existing:
        op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
        op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
        op.drop_index("ix_refresh_tokens_hash", table_name="refresh_tokens")
        op.drop_table("refresh_tokens")

    if "users" in existing:
        op.drop_index("ix_users_organization_id", table_name="users")
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")

    if "organizations" in existing:
        op.drop_table("organizations")
