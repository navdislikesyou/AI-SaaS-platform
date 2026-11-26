"""Meeting CRUD regression tests aligned with org-scoped attendee validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_settings_dep, require_manager
from app.core.config import Settings
from app.core.database import init_engine, shutdown_engine
from app.main import create_app


async def _run_with_db(db_url: str, fn):
    init_engine(db_url)
    try:
        await fn()
    finally:
        await shutdown_engine()


@pytest.mark.asyncio
async def test_create_meeting_with_valid_org_attendees(
    tmp_path: Path, make_organization, make_user
):
    org = await make_organization("TestOrg", "test-org")
    manager = await make_user(
        email="manager@test.com",
        role="manager",
        organization_id=org.id,
        full_name="Manager One",
    )
    attendee = await make_user(
        email="alice@test.com",
        role="employee",
        organization_id=org.id,
        full_name="Alice Test",
    )

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    settings = Settings(
        environment="test",
        log_level="WARNING",
        api_v1_prefix="/api/v1",
        database_url=db_url,
        jwt_secret_key="test-secret-key-with-at-least-32-bytes",
        trusted_origins=["http://testserver"],
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[require_manager] = lambda: manager

    async def run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            payload = {
                "title": "Sprint Planning",
                "description": "Q4 Sprint planning meeting",
                "starts_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "ends_at": (datetime.now(UTC) + timedelta(days=1, hours=2)).isoformat(),
                "timezone": "Asia/Kolkata",
                "venue": "Conference Room A",
                "attendees": [
                    {"email": attendee.email, "name": attendee.full_name, "user_id": attendee.id},
                ],
            }
            res = await client.post("/api/v1/meetings", json=payload)
            assert res.status_code == 201, res.text
            data = res.json()["data"]
            assert data["title"] == "Sprint Planning"
            assert data["status"] == "scheduled"

    await _run_with_db(db_url, run)


@pytest.mark.asyncio
async def test_create_meeting_rejects_cross_org_attendee(
    tmp_path: Path, make_organization, make_user
):
    org_a = await make_organization("OrgA", "org-a")
    org_b = await make_organization("OrgB", "org-b")
    manager = await make_user(email="manager-a@test.com", role="manager", organization_id=org_a.id)
    outsider = await make_user(email="outsider@test.com", role="employee", organization_id=org_b.id)

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    settings = Settings(
        environment="test",
        log_level="WARNING",
        api_v1_prefix="/api/v1",
        database_url=db_url,
        jwt_secret_key="test-secret-key-with-at-least-32-bytes",
        trusted_origins=["http://testserver"],
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[require_manager] = lambda: manager

    async def run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            payload = {
                "title": "Sprint Planning",
                "starts_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "ends_at": (datetime.now(UTC) + timedelta(days=1, hours=1)).isoformat(),
                "timezone": "UTC",
                "attendees": [
                    {"email": outsider.email, "name": outsider.full_name, "user_id": outsider.id}
                ],
            }
            res = await client.post("/api/v1/meetings", json=payload)
            assert res.status_code == 422, res.text

    await _run_with_db(db_url, run)
