"""Tenant isolation matrix tests (Phase 4).

Covers org scoping for employee retrieval, send_email, meeting scheduling,
inactive/unknown UUID rejection, client-supplied org ignored, missing org/session
safe handling, and DB-derived email addresses.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.registry import AgentRegistry
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_orchestrator,
    get_settings_dep,
    require_manager,
)
from app.core.config import Settings
from app.core.database import init_engine, shutdown_engine
from app.main import create_app
from app.services.orchestrator import Orchestrator


class CaptureSendService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_email(
        self, payload: dict[str, Any], user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append({"payload": payload, "user_context": user_context})
        return {
            "sent": True,
            "status": "sent",
            "recipients_count": len(payload.get("recipients", [])),
            "idempotency_key": payload.get("idempotency_key"),
            "duplicate": False,
        }


def _settings(db_url: str) -> Settings:
    return Settings(
        environment="test",
        log_level="WARNING",
        api_v1_prefix="/api/v1",
        database_url=db_url,
        jwt_secret_key="test-secret-key-with-at-least-32-bytes",
        trusted_origins=["http://testserver"],
    )


@pytest.mark.asyncio
async def test_tenant_isolation_employee_retrieval_and_client_org_ignored(
    tmp_path: Path, make_organization, make_user
):
    org_a = await make_organization("OrgA", "org-a-ti")
    org_b = await make_organization("OrgB", "org-b-ti")
    mgr_a = await make_user(
        email="mgr@a.com", role="manager", organization_id=org_a.id, full_name="Mgr A"
    )
    await make_user(email="a1@a.com", role="employee", organization_id=org_a.id, full_name="A1")
    await make_user(
        email="a2@a.com", role="employee", organization_id=org_a.id, full_name="A2", is_active=False
    )
    await make_user(email="b1@b.com", role="employee", organization_id=org_b.id, full_name="B1")

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    settings = _settings(db_url)
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: mgr_a

    init_engine(db_url)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get("/api/v1/automation/employees")
            assert res.status_code == 200, res.text
            emails = {e["email"] for e in res.json()["data"]}
            assert "a1@a.com" in emails
            assert "a2@a.com" not in emails  # inactive excluded
            assert "b1@b.com" not in emails  # cross-org excluded

            # Client-supplied org param ignored
            res = await client.get(f"/api/v1/automation/employees?organization_id={org_b.id}")
            assert res.status_code == 200, res.text
            emails = {e["email"] for e in res.json()["data"]}
            assert "b1@b.com" not in emails
    finally:
        await shutdown_engine()


@pytest.mark.asyncio
async def test_tenant_isolation_send_and_schedule_cross_org_rejected(
    tmp_path: Path, make_organization, make_user
):
    org_a = await make_organization("OrgA", "org-a-ti2")
    org_b = await make_organization("OrgB", "org-b-ti2")
    mgr_a = await make_user(
        email="mgr@a.com", role="manager", organization_id=org_a.id, full_name="Mgr A"
    )
    outsider = await make_user(
        email="out@b.com", role="employee", organization_id=org_b.id, full_name="Out B"
    )
    inactive = await make_user(
        email="inactive@a.com",
        role="employee",
        organization_id=org_a.id,
        full_name="Inactive",
        is_active=False,
    )

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    settings = _settings(db_url)
    svc = CaptureSendService()
    registry = AgentRegistry()
    registry.register(AutomationAgentAdapter(service=svc))
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: mgr_a
    app.dependency_overrides[require_manager] = lambda: mgr_a

    init_engine(db_url)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Send to cross-org UUID rejected
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent": "automation",
                    "operation": "send_email",
                    "payload": {
                        "employee_ids": [outsider.id],
                        "subject": "Hi",
                        "html_body": "<p>Hi</p>",
                        "confirm": True,
                        "idempotency_key": "k1",
                    },
                },
            )
            assert res.status_code == 422, res.text

            # Send to inactive rejected
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent": "automation",
                    "operation": "send_email",
                    "payload": {
                        "employee_ids": [inactive.id],
                        "subject": "Hi",
                        "html_body": "<p>Hi</p>",
                        "confirm": True,
                        "idempotency_key": "k2",
                    },
                },
            )
            assert res.status_code == 422, res.text

            # Unknown UUID rejected
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent": "automation",
                    "operation": "send_email",
                    "payload": {
                        "employee_ids": ["00000000-0000-0000-0000-000000000099"],
                        "subject": "Hi",
                        "html_body": "<p>Hi</p>",
                        "confirm": True,
                        "idempotency_key": "k3",
                    },
                },
            )
            assert res.status_code == 422, res.text

            # Schedule meeting with cross-org attendee rejected
            meeting_payload = {
                "title": "Meet",
                "starts_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "ends_at": (datetime.now(UTC) + timedelta(days=1, hours=1)).isoformat(),
                "timezone": "UTC",
                "attendees": [
                    {"email": outsider.email, "name": outsider.full_name, "user_id": outsider.id}
                ],
            }
            res = await client.post("/api/v1/meetings", json=meeting_payload)
            assert res.status_code == 422, res.text
    finally:
        await shutdown_engine()
    assert svc.calls == []


@pytest.mark.asyncio
async def test_tenant_isolation_missing_org_and_db_derived_email(
    tmp_path: Path, make_organization, make_user
):
    org = await make_organization("OrgA", "org-a-ti3")
    target = await make_user(
        email="real@a.com", role="employee", organization_id=org.id, full_name="Real Name"
    )
    mgr_no_org = await make_user(
        email="mgr@none.com", role="manager", organization_id=None, full_name="Mgr No Org"
    )

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    settings = _settings(db_url)

    # Missing org context - send should be rejected
    svc = CaptureSendService()
    registry = AgentRegistry()
    registry.register(AutomationAgentAdapter(service=svc))
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: mgr_no_org

    init_engine(db_url)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent": "automation",
                    "operation": "send_email",
                    "payload": {
                        "employee_ids": [target.id],
                        "subject": "Hi",
                        "html_body": "<p>Hi</p>",
                        "confirm": True,
                        "idempotency_key": "k-no-org",
                    },
                },
            )
            assert res.status_code in {403, 422}, res.text
    finally:
        await shutdown_engine()
    assert svc.calls == []

    # DB-derived email - even if payload includes arbitrary email, adapter uses DB record
    mgr = await make_user(
        email="mgr@a.com", role="manager", organization_id=org.id, full_name="Mgr"
    )
    svc2 = CaptureSendService()
    registry2 = AgentRegistry()
    registry2.register(AutomationAgentAdapter(service=svc2))
    app2 = create_app(settings)
    app2.dependency_overrides[get_settings_dep] = lambda: settings
    app2.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry2)
    app2.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: mgr

    init_engine(db_url)
    try:
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post(
                "/api/v1/agents/execute",
                json={
                    "agent": "automation",
                    "operation": "send_email",
                    "payload": {
                        "employee_ids": [target.id],
                        "subject": "Hi",
                        "html_body": "<p>Hi</p>",
                        "confirm": True,
                        "idempotency_key": "k-db-email",
                    },
                },
            )
            assert res.status_code == 200, res.text
            assert svc2.calls[0]["payload"]["recipients"][0]["email"] == "real@a.com"
    finally:
        await shutdown_engine()
