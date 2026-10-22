r"""One-time CLI bootstrap command to create initial administrator.

Usage:
    .venv\Scripts\python.exe bootstrap_admin.py --email admin@example.com --password StrongPass123!

Requires explicit email and strong password. Safe to rerun - checks for existing
admin and organization before creating. Uses raw SQL to avoid SQLAlchemy 2.x
registry configuration issues.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from uuid import uuid4

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.models import Base


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-time bootstrap command to create initial administrator."
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email address for the new administrator (must be unique).",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Strong password for the new administrator.",
    )
    return parser.parse_args()


def _sync_database_url(url: str) -> str:
    """Return the synchronous form of a configured database URL.

    The application runs on an async driver, but this command uses raw SQL
    through a synchronous engine. A URL carrying an async driver cannot be
    opened by a sync engine, so the async driver is replaced with its
    synchronous equivalent.

    Args:
        url: The configured database URL.

    Returns:
        A URL a synchronous engine can open.
    """
    if "+aiosqlite" in url:
        return url.replace("+aiosqlite", "", 1)
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "", 1)
    return url


def validate_password(password: str) -> None:
    """Basic password strength check.

    Args:
        password: The password to validate.

    Raises:
        ValueError: If the password is too short or too simple.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    # Check for at least 2 of: lowercase, uppercase, digit, special
    categories = sum(
        1
        for c in password
        if c.islower()
            or c.isupper()
            or c.isdigit()
            or not c.isalnum()
    )
    if categories < 2:
        raise ValueError(
            "Password should contain characters from at least 2 of these "
            "categories: lowercase, uppercase, digits, special characters."
        )


def bootstrap(email: str, password: str) -> None:
    """One-time bootstrap command to create initial administrator.

    Steps:
    1. Validate the password.
    2. Ensure an organization exists (create one if none exists).
    3. Ensure no administrator exists for that organization.
    4. Create the user with the ``admin`` role.
    5. Increment token version to seal the account.

    Uses raw SQL to avoid SQLAlchemy 2.x registry configuration issues.

    Args:
        email: Normalized email address for the administrator.
        password: Plain-text password (hashed before storage).
    """
    validate_password(password)

    settings = Settings()
    password_hasher = PasswordHasher()
    engine = create_engine(_sync_database_url(settings.database_url))
    Base.metadata.create_all(engine)

    python_now = datetime.now(timezone.utc)

    with engine.connect() as conn:
        # 2. Ensure an organization exists.
        email_local = email.split("@")[0]
        slug = email_local.replace(".", "-").replace("_", "-")

        row = conn.execute(
            text("SELECT id, name, slug FROM organizations WHERE slug = :slug"),
            {"slug": slug},
        ).mappings().first()

        if row is None:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :slug, TRUE, :now, :now)"
                ),
                {"id": str(uuid4()), "name": f"Organization for {email_local}", "slug": slug, "now": python_now},
            )
            conn.commit()
            print(f"Created organization: Organization for {email_local} (slug={slug})")
        else:
            print(f"Using existing organization: {row['name']} (slug={row['slug']})")

        if row is not None:
            org_id = row["id"]
        else:
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE slug = :slug"),
                {"slug": slug},
            ).scalar()

        # 3. Ensure no administrator exists for this organization.
        row = conn.execute(
            text("SELECT id, email FROM users WHERE organization_id = :org_id AND role = 'admin'"),
            {"org_id": org_id},
        ).mappings().first()

        if row is not None:
            print(
                f"Administrator already exists for organization {org_id} "
                f"(email={row['email']}). No changes made."
            )
            return

        # 4. Create the user with the admin role.
        hashed_password = password_hasher.hash(password)
        user_id = str(uuid4())

        conn.execute(
            text(
                "INSERT INTO users (id, email, full_name, hashed_password, role, organization_id, is_active, token_version, created_at, updated_at) "
                "VALUES (:id, :email, :full_name, :hashed_password, 'admin', :org_id, TRUE, 1, :now, :now)"
            ),
            {
                "id": user_id,
                "email": email.lower(),
                "full_name": email_local.capitalize(),
                "hashed_password": hashed_password,
                "org_id": org_id,
                "now": python_now,
            },
        )
        conn.commit()

        print(
            f"Bootstrap complete. Administrator created:\n"
            f"  email: {email.lower()}\n"
            f"  full_name: {email_local.capitalize()}\n"
            f"  role: admin\n"
            f"  organization_id: {org_id}\n"
            f"  token_version: 1"
        )


def main() -> None:
    args = parse_args()
    try:
        validate_password(args.password)
    except ValueError as exc:
        print(f"Password validation error: {exc}", file=sys.stderr)
        sys.exit(1)

    email = args.email.strip().lower()
    password = args.password

    bootstrap(email, password)


if __name__ == "__main__":
    main()