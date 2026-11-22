"""Security tests for AutomationAgent send_email recipient validation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.adapters.automation import AutomationAgentAdapter
from app.core.exceptions import ValidationFailedError


class FakeSendService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_email(
        self, payload: dict[str, Any], user_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append({"payload": payload, "user_context": user_context})
        recipients = payload.get("recipients", [])
        return {"sent": True, "status": "sent", "recipients_count": len(recipients)}


class FakeSession:
    def __init__(self, users: list[Any]):
        self.users = users

    async def execute(self, _query: Any) -> Any:
        class Result:
            def __init__(self, users: list[Any]):
                self._users = users

            def scalars(self) -> Any:
                class Scalars:
                    def __init__(self, users: list[Any]):
                        self._users = users

                    def all(self) -> list[Any]:
                        return self._users

                return Scalars(self._users)

        return Result(self.users)


PRINCIPAL = {"user_id": "mgr-1", "organization_id": "org-1", "role": "manager"}


@pytest.mark.asyncio
async def test_send_email_rejects_unknown_employee_id() -> None:
    adapter = AutomationAgentAdapter(service=FakeSendService())
    session = FakeSession(users=[])
    with pytest.raises(ValidationFailedError) as exc:
        await adapter.execute(
            "send_email",
            {
                "employee_ids": ["missing-id"],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k1",
            },
            user_context=PRINCIPAL,
            session=session,
        )
    assert exc.value.details.get("reason") == "unknown_employee"


@pytest.mark.asyncio
async def test_send_email_rejects_cross_org_employee() -> None:
    user = SimpleNamespace(
        id="u2",
        organization_id="org-2",
        is_active=True,
        email="x@x.com",
        full_name="X",
    )
    adapter = AutomationAgentAdapter(service=FakeSendService())
    session = FakeSession(users=[user])
    with pytest.raises(ValidationFailedError) as exc:
        await adapter.execute(
            "send_email",
            {
                "employee_ids": ["u2"],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k2",
            },
            user_context=PRINCIPAL,
            session=session,
        )
    assert exc.value.details.get("reason") == "cross_organization_employee"


@pytest.mark.asyncio
async def test_send_email_rejects_inactive_employee() -> None:
    user = SimpleNamespace(
        id="u3",
        organization_id="org-1",
        is_active=False,
        email="x@x.com",
        full_name="X",
    )
    adapter = AutomationAgentAdapter(service=FakeSendService())
    session = FakeSession(users=[user])
    with pytest.raises(ValidationFailedError) as exc:
        await adapter.execute(
            "send_email",
            {
                "employee_ids": ["u3"],
                "subject": "Hi",
                "html_body": "<p>Hi</p>",
                "confirm": True,
                "idempotency_key": "k3",
            },
            user_context=PRINCIPAL,
            session=session,
        )
    assert exc.value.details.get("reason") == "inactive_employee"


@pytest.mark.asyncio
async def test_send_email_resolves_emails_from_db() -> None:
    service = FakeSendService()
    user = SimpleNamespace(
        id="u4",
        organization_id="org-1",
        is_active=True,
        email="ok@org.com",
        full_name="OK",
    )
    adapter = AutomationAgentAdapter(service=service)
    session = FakeSession(users=[user])
    await adapter.execute(
        "send_email",
        {
            "employee_ids": ["u4"],
            "subject": "Hi",
            "html_body": "<p>Hi</p>",
            "confirm": True,
            "idempotency_key": "k4",
        },
        user_context=PRINCIPAL,
        session=session,
    )
    assert service.calls
    recipients = service.calls[0]["payload"]["recipients"]
    assert recipients[0]["email"] == "ok@org.com"
