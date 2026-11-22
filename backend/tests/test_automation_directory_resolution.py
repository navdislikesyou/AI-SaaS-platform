"""Tests for organization-scoped AutomationAgent roster resolution.

These tests validate the new architecture where the authenticated organization's
active registered employees are the single authoritative source. Packaged and
uploaded directory selection are no longer supported in the AutomationAgent path.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.adapters.automation import AutomationAgentAdapter
from app.core.exceptions import ValidationFailedError


class RecordingService:
    """Records calls made by the adapter."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        instruction: str,
        employees: list[dict[str, Any]] | None = None,
        user_context: dict[str, Any] | None = None,
        session: Any | None = None,
        selected_employee_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        from app.core.exceptions import ValidationFailedError

        if not (user_context or {}).get("organization_id"):
            raise ValidationFailedError("Organization context required for automation.")
        self.calls.append(
            {
                "instruction": instruction,
                "employees": employees,
                "user_context": user_context,
                "session": session,
                "selected_employee_ids": selected_employee_ids,
            }
        )
        roster = employees or []
        return {
            "meeting": {
                "title": "Sprint Planning",
                "date": "5 March",
                "time": "10 AM",
                "venue": "Conference Room A",
                "attendees": [p.get("name") or p.get("full_name") for p in roster],
            },
            "recipients": list(roster),
            "email": "Dear Team,\n\nSprint planning is scheduled for 5 March.",
            "employee_count": len(roster),
        }

    def execute_html(
        self,
        instruction: str,
        employees: list[dict[str, Any]] | None = None,
        user_context: dict[str, Any] | None = None,
        template: str = "invitation",
        reason: str = "",
        session: Any | None = None,
        selected_employee_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "instruction": instruction,
                "employees": employees,
                "user_context": user_context,
                "template": template,
                "reason": reason,
                "session": session,
                "selected_employee_ids": selected_employee_ids,
            }
        )
        roster = employees or []
        return {
            "meeting": {
                "title": "Sprint Planning",
                "date": "5 March",
                "time": "10 AM",
                "venue": "Conference Room A",
                "attendees": [p.get("name") or p.get("full_name") for p in roster],
            },
            "recipients": list(roster),
            "subject": "Sprint Planning",
            "html_body": "<p>Draft</p>",
            "template": template or "invitation",
            "employee_count": len(roster),
        }


PRINCIPAL = {"user_id": "u1", "organization_id": "org-1", "role": "manager"}


@pytest.mark.asyncio
async def test_draft_uses_org_context_and_session() -> None:
    service = RecordingService()
    adapter = AutomationAgentAdapter(service=service)

    result = await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup"},
        user_context=PRINCIPAL,
        session=object(),
    )

    assert result["directory"]["source"] == "organization"
    assert service.calls[0]["user_context"] == PRINCIPAL
    assert service.calls[0]["session"] is not None


@pytest.mark.asyncio
async def test_selected_employee_ids_are_forwarded() -> None:
    service = RecordingService()
    adapter = AutomationAgentAdapter(service=service)

    await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup", "employee_ids": ["e1", "e2"]},
        user_context=PRINCIPAL,
        session=object(),
    )

    assert service.calls[0]["selected_employee_ids"] == ["e1", "e2"]


@pytest.mark.asyncio
async def test_missing_org_context_returns_validation_error() -> None:
    service = RecordingService()
    adapter = AutomationAgentAdapter(service=service)

    with pytest.raises(ValidationFailedError):
        await adapter.execute(
            "draft_action",
            {"instruction": "Draft a standup"},
            user_context=None,
            session=object(),
        )


@pytest.mark.asyncio
async def test_directory_id_is_ignored_no_uploaded_resolution() -> None:
    service = RecordingService()
    adapter = AutomationAgentAdapter(service=service)

    result = await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup", "directory_id": "uploaded-1"},
        user_context=PRINCIPAL,
        session=object(),
    )

    assert result["directory"]["source"] == "organization"
    assert result["directory"]["directory_id"] is None


@pytest.mark.asyncio
async def test_recipients_are_whitelisted() -> None:
    class LeakyService(RecordingService):
        def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "meeting": {"title": "T"},
                "recipients": [{"name": "A", "email": "a@x.com", "salary": "secret"}],
                "email": "body",
                "employee_count": 1,
            }

    adapter = AutomationAgentAdapter(service=LeakyService())
    result = await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup"},
        user_context=PRINCIPAL,
        session=object(),
    )

    assert result["recipients"] == [{"name": "A", "email": "a@x.com"}]