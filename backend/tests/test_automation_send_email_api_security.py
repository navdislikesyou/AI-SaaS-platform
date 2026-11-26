"""API-level integration tests for AutomationAgent send_email security.

Covers /api/v1/agents/execute -> Orchestrator -> AutomationAdapter -> send_email.
Gmail is never called; the adapter service seam is used to capture validated payloads.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.registry import AgentRegistry
from app.api.deps import (
    get_async_session,
    get_current_user_from_token_optional_principal,
    get_orchestrator,
    get_settings_dep,
)
from app.core.config import Settings
from app.core.database import init_engine, shutdown_engine
from app.main import create_app
from app.services.orchestrator import Orchestrator


class CaptureSendService:
    """Service seam that captures send_email calls without external I/O."""

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


@asynccontextmanager
async def _app_client(
    *,
    db_url: str,
    user: Any,
    service: CaptureSendService,
    session_override: Any = ...,
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        environment="test",
        log_level="WARNING",
        api_v1_prefix="/api/v1",
        database_url=db_url,
        jwt_secret_key="test-secret-key-with-at-least-32-bytes",
        trusted_origins=["http://testserver"],
    )
    registry = AgentRegistry()
    registry.register(AutomationAgentAdapter(service=service))
    app = create_app(settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: user
    if session_override is not ...:
        app.dependency_overrides[get_async_session] = lambda: session_override

    init_engine(db_url)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        await shutdown_engine()


async def _post_send(client: AsyncClient, payload: dict[str, Any]) -> Any:
    return await client.post(
        "/api/v1/agents/execute",
        json={"agent": "automation", "operation": "send_email", "payload": payload},
    )


@pytest.mark.asyncio
async def test_send_email_api_valid_org_uuid_derived_from_db(
    tmp_path: Path, make_organization, make_user
):
    org = await make_organization("OrgA", "org-a")
    manager = await make_user(
        email="mgr@a.com", role="manager", organization_id=org.id, full_name="Mgr"
    )
    target = await make_user(
        email="alice@a.com", role="employee", organization_id=org.id, full_name="Alice"
    )
    svc = CaptureSendService()
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"

    async with _app_client(db_url=db_url, user=manager, service=svc) as client:
        res = await _post_send(
            client,
            {
                "employee_ids": [target.id],
                "subject": "Hello",
                "html_body": "<p>Hello</p>",
                "confirm": True,
                "idempotency_key": "k-ok",
            },
        )
        assert res.status_code == 200, res.text
        assert len(svc.calls) == 1
        recipients = svc.calls[0]["payload"]["recipients"]
        assert recipients[0]["name"] == "Alice"
        assert recipients[0]["email"] == "alice@a.com"
        assert svc.calls[0]["user_context"]["organization_id"] == org.id


@pytest.mark.asyncio
async def test_send_email_api_rejects_unknown_cross_org_inactive_and_arbitrary_email(
    tmp_path: Path, make_organization, make_user
):
    org_a = await make_organization("OrgA", "org-a2")
    org_b = await make_organization("OrgB", "org-b2")
    manager = await make_user(
        email="mgr@a.com", role="manager", organization_id=org_a.id, full_name="Mgr"
    )
    outsider = await make_user(
        email="out@b.com", role="employee", organization_id=org_b.id, full_name="Out"
    )
    inactive = await make_user(
        email="inactive@a.com",
        role="employee",
        organization_id=org_a.id,
        full_name="Inactive",
        is_active=False,
    )
    svc = CaptureSendService()
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"

    async with _app_client(db_url=db_url, user=manager, service=svc) as client:
        base = {"subject": "Hi", "html_body": "<p>Hi</p>", "confirm": True}
        for key, payload_extra in [
            ("k-unknown", {"employee_ids": ["00000000-0000-0000-0000-000000000099"]}),
            ("k-cross", {"employee_ids": [outsider.id]}),
            ("k-inactive", {"employee_ids": [inactive.id]}),
            ("k-arb", {"recipients": [{"name": "X", "email": "random@evil.com"}]}),
        ]:
            res = await _post_send(client, {**base, "idempotency_key": key, **payload_extra})
            assert res.status_code == 422, f"{key}: {res.text}"
    assert svc.calls == []


@pytest.mark.asyncio
async def test_send_email_api_rejects_missing_org_context(
    tmp_path: Path, make_organization, make_user
):
    org = await make_organization("OrgA", "org-a3")
    target = await make_user(
        email="t@a.com", role="employee", organization_id=org.id, full_name="T"
    )
    # Manager with no organization context
    manager_no_org = await make_user(
        email="mgr@none.com", role="manager", organization_id=None, full_name="Mgr"
    )
    svc = CaptureSendService()
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"

    async with _app_client(db_url=db_url, user=manager_no_org, service=svc) as client:
        res = await _post_send(
            client,
            {
                "employee_ids": [target.id],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k-no-org",
            },
        )
        assert res.status_code in {403, 422}, res.text
    assert svc.calls == []


@pytest.mark.asyncio
async def test_send_email_api_rbac_confirmation_and_idempotency(
    tmp_path: Path, make_organization, make_user
):
    org = await make_organization("OrgA", "org-a4")
    employee = await make_user(
        email="emp@a.com", role="employee", organization_id=org.id, full_name="Emp"
    )
    manager = await make_user(
        email="mgr@a.com", role="manager", organization_id=org.id, full_name="Mgr"
    )
    admin = await make_user(
        email="admin@a.com", role="admin", organization_id=org.id, full_name="Admin"
    )
    target = await make_user(
        email="t@a.com", role="employee", organization_id=org.id, full_name="T"
    )
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"

    # RBAC: employee denied
    svc = CaptureSendService()
    async with _app_client(db_url=db_url, user=employee, service=svc) as client:
        res = await _post_send(
            client,
            {
                "employee_ids": [target.id],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k-rbac",
            },
        )
        assert res.status_code == 403, res.text
    assert svc.calls == []

    # Confirmation required
    svc = CaptureSendService()
    async with _app_client(db_url=db_url, user=manager, service=svc) as client:
        res = await _post_send(
            client,
            {
                "employee_ids": [target.id],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": False,
                "idempotency_key": "k-confirm",
            },
        )
        assert res.status_code == 422, res.text
    assert svc.calls == []

    # Manager allowed
    svc = CaptureSendService()
    async with _app_client(db_url=db_url, user=manager, service=svc) as client:
        res = await _post_send(
            client,
            {
                "employee_ids": [target.id],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k-mgr",
            },
        )
        assert res.status_code == 200, res.text
    assert len(svc.calls) == 1

    # Admin allowed + idempotency key passed through
    svc = CaptureSendService()
    async with _app_client(db_url=db_url, user=admin, service=svc) as client:
        res = await _post_send(
            client,
            {
                "employee_ids": [target.id],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k-admin",
            },
        )
        assert res.status_code == 200, res.text
    assert svc.calls[0]["payload"]["idempotency_key"] == "k-admin"
