"""Tests for the Automation Agent's HTML drafting path (Phase 4).

Covers AutomationService.execute_html with org-scoped roster supplied explicitly.
No packaged fallback; tests provide employees + user_context.
No model is involved.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_ollama")

from app.core.config import Settings  # noqa: E402
from automation_agent.service import AutomationService  # noqa: E402

ORG_ID = "org-test-1"
USER_CTX = {"user_id": "u1", "organization_id": ORG_ID, "role": "manager"}
ROSTER = [
    {
        "id": "e1",
        "full_name": "Navneet Verma",
        "name": "Navneet Verma",
        "email": "navneet.verma2023@ssipmt.com",
        "organization_id": ORG_ID,
        "is_active": True,
    }
]


class _ExplodingLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("draft_html must not call the model")


@pytest.fixture
def service() -> AutomationService:
    return AutomationService(Settings(environment="test"))


def test_execute_html_returns_a_rendered_draft(service: AutomationService) -> None:
    result = service.execute_html(
        "Schedule sprint planning on 5 March at 10 AM with Navneet",
        employees=ROSTER,
        user_context=USER_CTX,
        session=None,
    )

    assert set(result) >= {
        "meeting",
        "recipients",
        "subject",
        "html_body",
        "template",
        "employee_count",
    }
    assert result["html_body"].lstrip().startswith("<!DOCTYPE html>")
    assert result["subject"] == "Meeting Invitation: Sprint Planning"
    assert result["template"] == "meeting_invitation"
    assert result["employee_count"] == 1


def test_execute_html_resolves_recipients_against_supplied_roster(
    service: AutomationService,
) -> None:
    result = service.execute_html(
        "Schedule a standup with Navneet Verma",
        employees=ROSTER,
        user_context=USER_CTX,
        session=None,
    )
    assert [person.get("name") or person.get("full_name") for person in result["recipients"]] == [
        "Navneet Verma"
    ]


def test_execute_html_uses_the_supplied_roster_when_one_is_given(
    service: AutomationService,
) -> None:
    roster = [
        {
            "id": "e2",
            "name": "Aarti Rao",
            "email": "aarti@example.com",
            "organization_id": ORG_ID,
            "is_active": True,
        }
    ]
    result = service.execute_html(
        "Schedule a standup with Aarti",
        employees=roster,
        user_context=USER_CTX,
        session=None,
    )
    assert [person["name"] for person in result["recipients"]] == ["Aarti Rao"]
    assert result["employee_count"] == 1


def test_execute_html_defaults_a_blank_template(service: AutomationService) -> None:
    result = service.execute_html(
        "Schedule a standup with Navneet",
        employees=ROSTER,
        user_context=USER_CTX,
        session=None,
        template="",
    )
    assert result["template"] == "meeting_invitation"
    assert result["subject"].startswith("Meeting Invitation:")


@pytest.mark.parametrize(
    ("template", "expected"),
    [("reminder_24h", "Reminder:"), ("reminder_30m", "Upcoming Meeting:")],
)
def test_execute_html_renders_the_requested_template(
    service: AutomationService, template: str, expected: str
) -> None:
    result = service.execute_html(
        "Schedule a standup with Navneet",
        employees=ROSTER,
        user_context=USER_CTX,
        session=None,
        template=template,
    )
    assert result["template"] == template
    assert result["subject"].startswith(expected)


def test_execute_html_rejects_an_unknown_template(service: AutomationService) -> None:
    with pytest.raises(ValueError, match="Unknown template"):
        service.execute_html(
            "Schedule a standup",
            employees=ROSTER,
            user_context=USER_CTX,
            session=None,
            template="invoice",
        )


def test_execute_html_never_calls_the_model(service: AutomationService) -> None:
    service._agent.llm = _ExplodingLLM()
    result = service.execute_html(
        "Schedule sprint planning on 5 March with Navneet",
        employees=ROSTER,
        user_context=USER_CTX,
        session=None,
    )
    assert result["html_body"]


def test_execute_html_does_not_swap_the_shared_roster(service: AutomationService) -> None:
    packaged = list(service._agent.employees or [])
    uploaded = [
        {
            "id": "e2",
            "name": "Aarti Rao",
            "email": "aarti@example.com",
            "organization_id": ORG_ID,
            "is_active": True,
        }
    ]
    service.execute_html(
        "Schedule a standup with Aarti", employees=uploaded, user_context=USER_CTX, session=None
    )
    assert list(service._agent.employees or []) == packaged
