"""Unit tests for the Automation Agent's instruction parser.

These cover :meth:`AutomationAgent.parse_instruction`, which is pure string and
regex work. No LLM is involved: a stub client stands in, so these run on CPU
with no Ollama server, no model download, and no network.

Two parser bugs are pinned here.

**A time was read as the date.** The date pattern was a day number followed by
a word, so ``"9 AM"`` matched it and the instruction
``"Schedule a standup tomorrow at 9 AM with Omkar"`` returned
``date="9 AM"``. AM and PM are words, which is what let the time through. The
pattern now rejects them.

**A shared surname matched the wrong people.** Attendees were matched by any
part of a name, so ``"invite Navneet Verma"`` also matched ``"Pulkita Verma"``
because both contain ``"verma"``. Full names now take precedence, with
first-name matching as a fallback so ``"Omkar"`` still resolves.

The module under test imports ``langchain_ollama`` at module scope, which is an
optional agent dependency. It is stubbed here so these regression tests run in a
plain CI environment.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


def _stub_optional_llm_dependency() -> None:
    """Install a minimal ``langchain_ollama`` stub if the real one is absent.

    ``automation_agent.automation_agent`` imports ``LocalLLM`` at module scope,
    and that import reaches ``langchain_ollama``. Stubbing it lets the parser
    be tested without the optional agent dependencies installed. A real
    installation is left untouched.
    """
    if "langchain_ollama" in sys.modules:
        return

    try:
        import langchain_ollama  # noqa: F401
    except ImportError:
        module = types.ModuleType("langchain_ollama")

        class _ChatOllama:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            def invoke(self, prompt: str) -> Any:
                return types.SimpleNamespace(content="Dear Team,")

        module.ChatOllama = _ChatOllama  # type: ignore[attr-defined]
        sys.modules["langchain_ollama"] = module


_stub_optional_llm_dependency()

from automation_agent.automation_agent import AutomationAgent  # noqa: E402


class StubLLM:
    """Stands in for ``LocalLLM``.

    ``parse_instruction`` never calls the model, so this only needs to exist.
    """

    def generate(self, prompt: str) -> str:
        """Return a fixed body without contacting a model.

        Args:
            prompt: The prompt that would be sent to Ollama.

        Returns:
            A placeholder email body.
        """
        return "Dear Team,"


@pytest.fixture
def agent() -> AutomationAgent:
    """Return an AutomationAgent with a stub LLM and the real roster.

    The employee directory is the packaged ``employees.json``, so the attendee
    tests reflect the names the agent actually ships with.

    Returns:
        An agent ready to parse instructions.
    """
    return AutomationAgent(llm=StubLLM())


# --------------------------------------------------------------------------
# Date parsing: a time is not a date
# --------------------------------------------------------------------------


@pytest.mark.parametrize("meridiem", ["AM", "PM", "am", "pm"])
def test_time_is_not_parsed_as_a_date(
    agent: AutomationAgent,
    meridiem: str,
) -> None:
    """A clock time must leave the date unspecified.

    Regression test: ``"9 AM"`` matched the old date pattern because ``AM`` is
    a word, so the date came back as the time.
    """
    meeting = agent.parse_instruction(f"Schedule a standup tomorrow at 9 {meridiem} with Omkar")

    assert meeting["date"] == "Not Specified"
    assert meeting["time"] == f"9 {meridiem}"


def test_colon_time_is_not_parsed_as_a_date(agent: AutomationAgent) -> None:
    """A ``HH:MM`` time does not become the date either."""
    meeting = agent.parse_instruction("Standup tomorrow at 2:30 PM with Omkar")

    assert meeting["date"] == "Not Specified"
    assert meeting["time"] == "2:30 PM"


@pytest.mark.parametrize(
    "instruction,expected_date",
    [
        pytest.param(
            "Schedule a sprint planning on 5 March at 10 AM with Navneet Verma",
            "5 March",
            id="day_and_month",
        ),
        pytest.param(
            "Project review on 12 April 2026 at 2:30 PM",
            "12 April 2026",
            id="day_month_and_year",
        ),
        pytest.param("Standup on 3 June with the team", "3 June", id="day_and_month_no_time"),
        pytest.param(
            "Client meeting on 28 December 2026 at 11 AM in Board Room",
            "28 December 2026",
            id="two_digit_day",
        ),
    ],
)
def test_numeric_dates_are_still_parsed(
    agent: AutomationAgent,
    instruction: str,
    expected_date: str,
) -> None:
    """The intended date format still parses after the fix.

    Guards against a fix that breaks real dates while rejecting times.
    """
    assert agent.parse_instruction(instruction)["date"] == expected_date


def test_date_and_time_are_parsed_independently(agent: AutomationAgent) -> None:
    """A date and a time in one instruction are captured separately."""
    meeting = agent.parse_instruction(
        "Schedule a sprint planning on 5 March at 10 AM in Conference Room A"
    )

    assert meeting["date"] == "5 March"
    assert meeting["time"] == "10 AM"
    assert meeting["venue"] == "Conference Room A"


def test_non_numeric_date_is_left_unspecified(agent: AutomationAgent) -> None:
    """A natural-language date is not guessed at.

    The parser only understands numeric dates. Returning "Not Specified" is
    correct; inventing "tomorrow" would be a guess.
    """
    meeting = agent.parse_instruction("Schedule a standup tomorrow at 9 AM")

    assert meeting["date"] == "Not Specified"
    assert meeting["time"] == "9 AM"


# --------------------------------------------------------------------------
# Attendee matching: a full name must not match a namesake
# --------------------------------------------------------------------------


def test_full_name_does_not_match_a_namesake(agent: AutomationAgent) -> None:
    """Naming one employee must not invite the one who shares a surname.

    Regression test: both ``Navneet Verma`` and ``Pulkita Verma`` contain
    ``"verma"``, so matching any name part invited both.
    """
    meeting = agent.parse_instruction("invite Navneet Verma")

    assert meeting["attendees"] == ["Navneet Verma"]


def test_two_full_names_with_a_shared_surname_both_match(
    agent: AutomationAgent,
) -> None:
    """Naming both employees explicitly invites both.

    Confirms the fix rejects accidental matches without rejecting real ones.
    """
    meeting = agent.parse_instruction(
        "Schedule a sprint planning with Navneet Verma and Pulkita Verma"
    )

    assert meeting["attendees"] == ["Navneet Verma", "Pulkita Verma"]


def test_full_three_part_name_matches(agent: AutomationAgent) -> None:
    """A three-part name matches on its complete form."""
    meeting = agent.parse_instruction("invite Mohammed Ashhar Khan")

    assert meeting["attendees"] == ["Mohammed Ashhar Khan"]


def test_first_name_still_matches(agent: AutomationAgent) -> None:
    """First-name matching survives the fix.

    Unambiguous, so it is a useful shorthand and is preserved deliberately.
    """
    meeting = agent.parse_instruction("Schedule a standup at 9 AM with Omkar")

    assert meeting["attendees"] == ["Omkar Shenwai"]


def test_first_name_of_a_sibling_surname_does_not_collide(
    agent: AutomationAgent,
) -> None:
    """A first name cannot drag in a namesake.

    ``Omkar`` matches only ``Omkar Shenwai``, not the Vermas.
    """
    meeting = agent.parse_instruction("invite Omkar")

    assert meeting["attendees"] == ["Omkar Shenwai"]


def test_surname_alone_matches_nobody(agent: AutomationAgent) -> None:
    """A bare shared surname is ambiguous and resolves to nobody.

    The previous behaviour invited both Vermas here. Ambiguity is not a
    licence to invite people who were not named.
    """
    meeting = agent.parse_instruction("invite Verma to the review")

    assert meeting["attendees"] == []


def test_no_people_named_matches_nobody(agent: AutomationAgent) -> None:
    """An instruction naming no one produces an empty attendee list."""
    meeting = agent.parse_instruction("invite the whole team to the standup")

    assert meeting["attendees"] == []


def test_full_name_takes_precedence_over_first_name_ambiguity(
    agent: AutomationAgent,
) -> None:
    """A full name is matched even when a first name would also fit.

    ``Navneet`` is unambiguous on its own, so this documents that the full-name
    pass runs first and the fallback only handles what it missed.
    """
    meeting = agent.parse_instruction("Schedule a standup at 9 AM with Navneet Verma and Omkar")

    assert meeting["attendees"] == ["Navneet Verma", "Omkar Shenwai"]


# --------------------------------------------------------------------------
# End-to-end parse of the documented example
# --------------------------------------------------------------------------


def test_full_instruction_parses_every_field(agent: AutomationAgent) -> None:
    """The reference instruction fills in every meeting field.

    Ties the two fixes together: the time no longer leaks into the date, and
    the named employee resolves to exactly one person.
    """
    meeting = agent.parse_instruction("Schedule a standup tomorrow at 9 AM with Omkar")

    assert meeting == {
        "title": "Daily Standup",
        "date": "Not Specified",
        "time": "9 AM",
        "venue": "Not Specified",
        "attendees": ["Omkar Shenwai"],
    }


def test_find_emails_resolves_parsed_attendees(agent: AutomationAgent) -> None:
    """Parsed attendee names resolve to employee records.

    Confirms the attendee fix flows through to recipient lookup, which matches
    on the exact ``name`` field and so requires an unambiguous result.
    """
    meeting = agent.parse_instruction("invite Navneet Verma")

    recipients = agent.find_emails(meeting["attendees"])

    assert [person["name"] for person in recipients] == ["Navneet Verma"]
    assert recipients[0]["email"] == "navneet.verma2023@ssipmt.com"


def test_recipients_are_not_duplicated(agent: AutomationAgent) -> None:
    """One recipient record per named employee, never two.

    Both Vermas appearing once each is correct; the same person appearing twice
    would mean a duplicate was queued for invitation.
    """
    meeting = agent.parse_instruction("invite Navneet Verma and Pulkita Verma")

    recipients = agent.find_emails(meeting["attendees"])

    assert len(recipients) == len({person["name"] for person in recipients}) == 2
