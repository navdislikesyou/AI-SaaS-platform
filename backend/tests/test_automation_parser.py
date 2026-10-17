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

Relative dates and online venues are covered separately below. The short version:
``"for tomorrow"`` needs a literal ``" in "`` to reach the venue pattern, so an
online request lost both its date and its venue.

The module under test imports ``langchain_ollama`` at module scope, which is an
optional agent dependency. It is stubbed here so these regression tests run in a
plain CI environment.
"""

from __future__ import annotations

import sys
import types
from datetime import date, datetime, timedelta
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

from automation_agent import automation_agent as automation_agent_module  # noqa: E402
from automation_agent.automation_agent import (  # noqa: E402
    AutomationAgent,
    _tomorrow,
)


class _FrozenDatetime:
    """A ``datetime`` stand-in whose ``now()`` never moves.

    Month rollover cannot be reached from the real clock without waiting for the
    right day, so the date is pinned here instead.

    Args:
        frozen: The day to report.
    """

    def __init__(self, frozen: date) -> None:
        """Store the pinned day.

        Args:
            frozen: The day to report.
        """
        self._frozen = frozen

    def now(self) -> datetime:
        """Return midday on the pinned day.

        Returns:
            A datetime on the pinned day.
        """
        return datetime.combine(self._frozen, datetime.min.time())


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
    a word, so the date came back as the time. The instruction carries no other
    date word, so nothing else can fill the field.
    """
    meeting = agent.parse_instruction(f"Schedule a standup at 9 {meridiem} with Omkar")

    assert meeting["date"] == "Not Specified"
    assert meeting["time"] == f"9 {meridiem}"


def test_colon_time_is_not_parsed_as_a_date(agent: AutomationAgent) -> None:
    """A ``HH:MM`` time does not become the date either."""
    meeting = agent.parse_instruction("Standup at 2:30 PM with Omkar")

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


@pytest.mark.parametrize(
    "phrase",
    ["next Monday", "next week", "some day soon", "later this month"],
)
def test_other_relative_dates_are_still_left_unspecified(
    agent: AutomationAgent,
    phrase: str,
) -> None:
    """A relative day the parser does not understand is not guessed at.

    ``"tomorrow"`` is resolved because it has exactly one meaning. Anything
    vaguer has several, and inventing one would put a wrong date in a draft.
    """
    meeting = agent.parse_instruction(f"Schedule a standup {phrase} at 9 AM")

    assert meeting["date"] == "Not Specified"
    assert meeting["time"] == "9 AM"


# --------------------------------------------------------------------------
# Relative dates and online venues
# --------------------------------------------------------------------------


def test_tomorrow_is_resolved_to_the_next_calendar_day(
    agent: AutomationAgent,
) -> None:
    """``"tomorrow"`` becomes tomorrow's date, derived from the current day.

    The expected value is computed the same way rather than written down, so the
    test stays correct on any day it runs.
    """
    expected = date.today() + timedelta(days=1)
    expected_text = f"{expected.day} {expected.strftime('%B')}"

    meeting = agent.parse_instruction("Draft an invitation for tomorrow at 9 AM")

    assert meeting["date"] == expected_text


@pytest.mark.parametrize(
    "phrase",
    ["tomorrow", "Tomorrow", "TOMORROW", "tomorrow's standup"],
)
def test_tomorrow_is_matched_regardless_of_case(
    agent: AutomationAgent,
    phrase: str,
) -> None:
    """The word is matched case-insensitively, like every other term.

    Args:
        agent: The agent under test.
        phrase: The spelling to try.
    """
    expected = date.today() + timedelta(days=1)

    meeting = agent.parse_instruction(f"Draft an invitation for {phrase}")

    assert meeting["date"] == f"{expected.day} {expected.strftime('%B')}"


def test_tomorrow_rolls_over_into_the_next_month(
    agent: AutomationAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The last day of a month resolves to the first of the next one.

    Naive arithmetic on the day number would produce an impossible date here.
    """
    monkeypatch.setattr(automation_agent_module, "datetime", _FrozenDatetime(date(2026, 12, 31)))

    assert _tomorrow() == "1 January"


def test_tomorrow_does_not_disturb_the_time(agent: AutomationAgent) -> None:
    """A relative date and a clock time are captured independently."""
    expected = date.today() + timedelta(days=1)

    meeting = agent.parse_instruction("Schedule a standup tomorrow at 2:30 PM with Omkar")

    assert meeting["date"] == f"{expected.day} {expected.strftime('%B')}"
    assert meeting["time"] == "2:30 PM"


def test_online_meeting_without_a_platform(agent: AutomationAgent) -> None:
    """An online meeting with no platform named reports a generic venue.

    No joining link is invented, because one has to come from whoever owns the
    call.
    """
    meeting = agent.parse_instruction(
        "draft an invitation mail for tomorrow to attend the online meeting with omkar"
    )

    assert meeting["venue"] == "Online meeting"
    assert "http" not in meeting["venue"]


def test_virtual_meeting_is_also_recognized(agent: AutomationAgent) -> None:
    """ "Virtual" means the same thing and produces the same venue."""
    meeting = agent.parse_instruction("Draft an invitation for a virtual meeting")

    assert meeting["venue"] == "Online meeting"


@pytest.mark.parametrize(
    "phrase,expected_venue",
    [
        pytest.param("Google Meet", "Google Meet", id="google_meet"),
        pytest.param("google meet", "Google Meet", id="google_meet_lowercase"),
        pytest.param("Zoom", "Zoom", id="zoom"),
        pytest.param("zoom", "Zoom", id="zoom_lowercase"),
        pytest.param("Microsoft Teams", "Microsoft Teams", id="microsoft_teams"),
    ],
)
def test_a_named_platform_is_reported_as_the_venue(
    agent: AutomationAgent,
    phrase: str,
    expected_venue: str,
) -> None:
    """A platform named in the request is the venue.

    Args:
        agent: The agent under test.
        phrase: The platform wording to try.
        expected_venue: The venue text it should produce.
    """
    meeting = agent.parse_instruction(f"Draft an invitation for a meeting on {phrase} tomorrow")

    assert meeting["venue"] == expected_venue


def test_the_bare_word_teams_is_not_treated_as_a_platform(
    agent: AutomationAgent,
) -> None:
    """ "Teams" is also an ordinary plural noun in a workplace request.

    Matching it would turn "invite the engineering teams" into a Microsoft Teams
    meeting, so only the full product name counts.
    """
    meeting = agent.parse_instruction("Invite the engineering teams tomorrow")

    assert meeting["venue"] == "Not Specified"


def test_a_named_platform_wins_over_a_generic_online_phrase(
    agent: AutomationAgent,
) -> None:
    """ "on Zoom" identifies the venue more precisely than "online meeting"."""
    meeting = agent.parse_instruction("Draft an invitation for an online meeting on Zoom")

    assert meeting["venue"] == "Zoom"


def test_online_meeting_with_no_time_leaves_the_time_unspecified(
    agent: AutomationAgent,
) -> None:
    """A request with no clock time must not invent one.

    A guessed time is worse than an absent one: it is the field a reader acts on
    first, and a wrong time sends people to a meeting that is not happening.
    """
    meeting = agent.parse_instruction(
        "draft an invitation mail for tomorrow to attend the online meeting with omkar and pulkita"
    )

    assert meeting["time"] == "Not Specified"
    assert meeting["date"] != "Not Specified"
    assert meeting["venue"] == "Online meeting"


def test_the_reported_instruction_resolves_every_field(
    agent: AutomationAgent,
) -> None:
    """The exact instruction from the bug report parses as intended."""
    expected = date.today() + timedelta(days=1)

    meeting = agent.parse_instruction(
        "draft an invitation mail for tomorrow to attend the online meeting with omkar and pulkita"
    )

    assert meeting["date"] == f"{expected.day} {expected.strftime('%B')}"
    assert meeting["time"] == "Not Specified"
    assert meeting["venue"] == "Online meeting"
    assert sorted(meeting["attendees"]) == ["Omkar Shenwai", "Pulkita Verma"]


def test_a_physical_venue_still_wins_when_no_platform_is_named(
    agent: AutomationAgent,
) -> None:
    """Online detection must not swallow a room name."""
    meeting = agent.parse_instruction(
        "Schedule a client meeting in Conference Room A with Navneet Verma"
    )

    assert meeting["venue"] == "Conference Room A"


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

    Ties the fixes together: the time no longer leaks into the date, and the
    named employee resolves to exactly one person.
    """
    meeting = agent.parse_instruction("Schedule a standup at 9 AM with Omkar")

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
