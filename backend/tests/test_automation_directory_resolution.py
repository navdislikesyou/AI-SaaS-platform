"""Tests for resolving an uploaded employee directory into a draft.

The Automation Agent itself is not loaded here. ``automation_agent`` needs the
Ollama client and the langchain stack, so these tests drive the real parser and
lookup logic with a stub LLM, exactly as ``test_automation_parser.py`` does, and
drive the adapter with a recording fake service.

The point of this file is that a selected directory genuinely changes who a
draft is addressed to, and that two directories in flight at once cannot leak
into each other.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.adapters.automation import AutomationAgentAdapter
from app.agents.registry import AgentRegistry
from app.api import deps
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_employee_directory_manifest,
    get_employee_directory_service,
    get_orchestrator,
    get_registry,
    get_settings_dep,
)
from app.core.config import Settings
from app.core.exceptions import DirectoryNotFoundError
from app.main import create_app
from app.services.employee_directory import (
    DirectoryStatus,
    EmployeeDirectoryManifest,
    EmployeeDirectoryService,
    build_row,
    record_directory,
    set_directory_service,
    set_manifest,
)
from app.services.orchestrator import Orchestrator
from tests.fakes import FakePrincipal

#: Principal handed to the adapter under test. The adapters authorize the
#: caller before they reach the agent, so a principal is required.
PRINCIPAL = {
    "user_id": "test-user-1",
    "organization_id": "test-org-1",
    "role": "employee",
}

EXECUTE_URL = "/api/v1/agents/execute"

CUSTOM = [{"name": "Aarti Rao", "email": "aarti@example.com"}]

OTHER = [{"name": "Zoya Kapadia", "email": "zoya@example.com"}]

#: Present only in the packaged agents.json, so it proves a custom directory
#: replaces the default roster rather than merging with it.
PACKAGED_ONLY = "Navneet Verma"


class RecordingService:
    """Stands in for ``AutomationService`` and records what it was given.

    Attributes:
        calls: Instructions passed to :meth:`execute`, in order.
        rosters: Employee lists passed to :meth:`execute`, in order. None means
            the caller relied on the packaged directory.
    """

    def __init__(self) -> None:
        """Initialize with no recorded calls."""
        self.calls: list[str] = []
        self.rosters: list[list[dict[str, str]] | None] = []

    def execute(
        self,
        instruction: str,
        employees: list[dict[str, str]] | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record the call and return a draft shaped from the given roster.

        Args:
            instruction: The instruction forwarded by the adapter.
            employees: The resolved roster, or None for the packaged directory.

        Returns:
            A draft whose recipients come from whichever roster was used.
        """
        self.calls.append(instruction)
        self.rosters.append(employees)

        roster = employees if employees is not None else [{"name": PACKAGED_ONLY}]

        return {
            "meeting": {
                "title": "Sprint Planning",
                "date": "5 March",
                "time": "10 AM",
                "venue": "Conference Room A",
                "attendees": [person["name"] for person in roster],
            },
            "recipients": list(roster),
            "email": "Dear Team,\n\nSprint planning is scheduled for 5 March.",
            "employee_count": len(roster),
        }


def write_directory(
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
    records: list[dict[str, str]],
    filename: str = "roster.json",
) -> str:
    """Write a directory file directly and register it in the manifest.

    Registering by hand keeps these tests focused on resolution rather than on
    the upload route, which ``test_automation_directories_api.py`` already covers.

    Args:
        service: The directory service.
        manifest: The manifest to record into.
        records: Employee records to store.
        filename: Display filename to record.

    Returns:
        The new directory id.
    """
    service.upload_dir.mkdir(parents=True, exist_ok=True)

    directory_id = uuid.uuid4().hex
    stored_name = f"{directory_id}_{filename}"

    (service.upload_dir / stored_name).write_text(json.dumps(records), encoding="utf-8")

    record_directory(
        build_row(
            directory_id=directory_id,
            display_filename=filename,
            stored_name=stored_name,
            extension=".json",
            size_bytes=len(json.dumps(records)),
            status=DirectoryStatus.READY,
            employee_count=len(records),
            organization_id=PRINCIPAL["organization_id"],
            owner_id=PRINCIPAL["user_id"],
        ),
        manifest,
    )

    return directory_id


@pytest.fixture
def manifest(tmp_path: Path) -> Iterator[EmployeeDirectoryManifest]:
    """Install a manifest backed by a temporary file as the shared one.

    The router and the adapter both resolve through the module accessor, so the
    test has to install it there rather than override a dependency separately.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Yields:
        The temporary manifest store.
    """
    store = EmployeeDirectoryManifest(tmp_path / "uploads" / "directories.json")

    set_manifest(store)

    try:
        yield store

    finally:
        set_manifest(None)


@pytest.fixture
def service(tmp_path: Path) -> Iterator[EmployeeDirectoryService]:
    """Install a directory service using temporary storage as the shared one.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Yields:
        The configured service.
    """
    store = EmployeeDirectoryService(upload_dir=tmp_path / "uploads", max_bytes=65536)

    set_directory_service(store)

    try:
        yield store

    finally:
        set_directory_service(None)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return test settings.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        Settings for the test application.
    """
    return Settings(
        environment="test",
        log_level="WARNING",
        automation_upload_dir=tmp_path / "uploads",
        automation_upload_manifest_path=tmp_path / "uploads" / "directories.json",
        _env_file=None,
    )


@pytest.fixture
def adapter(service: EmployeeDirectoryService) -> AutomationAgentAdapter:
    """Return a connected adapter with a recording service.

    Args:
        service: The directory service the adapter resolves ids through.

    Returns:
        A connected automation adapter.
    """
    return AutomationAgentAdapter(
        service=RecordingService(),
        directory_service=service,
    )


@pytest.fixture(autouse=True)
def _reset_deps() -> Iterator[None]:
    """Clear shared singletons around each test.

    Yields:
        Nothing. The reset runs after the test.
    """
    deps.reset_state()

    yield

    deps.reset_state()


# --------------------------------------------------------------------------
# Default directory behaviour
# --------------------------------------------------------------------------


async def test_omitting_directory_id_uses_the_packaged_directory(
    adapter: AutomationAgentAdapter,
) -> None:
    """No directory_id means the service is called with no roster at all."""
    await adapter.execute("draft_action", {"instruction": "Draft a standup invite"},
        user_context=PRINCIPAL,
)

    service = adapter._service

    assert service.rosters == [None]


@pytest.mark.parametrize("directory_id", ["", "   ", None])
async def test_a_blank_directory_id_uses_the_packaged_directory(
    adapter: AutomationAgentAdapter,
    directory_id: str | None,
) -> None:
    """A blank or null id is treated as no selection, not as a lookup.

    Args:
        adapter: The adapter under test.
        directory_id: The blank value to send.
    """
    await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup invite", "directory_id": directory_id},
            user_context=PRINCIPAL,
    )

    assert adapter._service.rosters == [None]


async def test_the_default_result_names_the_default_directory(
    adapter: AutomationAgentAdapter,
) -> None:
    """A caller can tell the packaged directory was used."""
    result = await adapter.execute("draft_action", {"instruction": "Draft a standup invite"},
        user_context=PRINCIPAL,
)

    assert result["directory"] == {
        "directory_id": None,
        "source": "default",
        "employee_count": 1,
    }


# --------------------------------------------------------------------------
# Selected directory behaviour
# --------------------------------------------------------------------------


async def test_a_selected_directory_replaces_the_roster(
    adapter: AutomationAgentAdapter,
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A selected id is resolved and handed to the service."""
    directory_id = write_directory(service, manifest, CUSTOM)

    await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup invite", "directory_id": directory_id},
            user_context=PRINCIPAL,
    )

    assert adapter._service.rosters == [CUSTOM]


async def test_the_result_names_the_selected_directory(
    adapter: AutomationAgentAdapter,
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A caller can tell which uploaded directory produced the draft."""
    directory_id = write_directory(service, manifest, CUSTOM)

    result = await adapter.execute(
        "draft_action",
        {"instruction": "Draft a standup invite", "directory_id": directory_id},
            user_context=PRINCIPAL,
    )

    assert result["directory"] == {
        "directory_id": directory_id,
        "source": "uploaded",
        "employee_count": 1,
    }


async def test_an_unknown_directory_id_is_an_error_not_a_fallback(
    adapter: AutomationAgentAdapter,
) -> None:
    """An unusable id never silently reverts to the packaged directory.

    Silently drafting against the wrong roster would be the worst failure here:
    the draft would look correct and be addressed to the wrong people.
    """
    with pytest.raises(DirectoryNotFoundError):
        await adapter.execute(
            "draft_action",
            {"instruction": "Draft a standup invite", "directory_id": "nope"},
                user_context=PRINCIPAL,
        )

    assert adapter._service.calls == []


async def test_a_directory_whose_file_vanished_is_an_error_not_a_fallback(
    adapter: AutomationAgentAdapter,
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """A registered id with no file on disk is reported, never substituted."""
    directory_id = write_directory(service, manifest, CUSTOM)

    for path in service.upload_dir.iterdir():
        path.unlink()

    with pytest.raises(DirectoryNotFoundError):
        await adapter.execute(
            "draft_action",
            {"instruction": "Draft a standup invite", "directory_id": directory_id},
                user_context=PRINCIPAL,
        )

    assert adapter._service.calls == []


async def test_recipients_with_extra_fields_are_whitelisted(
    adapter: AutomationAgentAdapter,
) -> None:
    """A roster record carrying extra fields is reduced at the adapter boundary.

    Args:
        adapter: The adapter under test.
    """

    class LeakyService(RecordingService):
        """A service that returns recipient records with extra fields."""

        def execute(
            self,
            instruction: str,
            employees: list[dict[str, str]] | None = None,
        user_context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Return recipients that still hold non-public fields.

            Args:
                instruction: Unused instruction.
                employees: Unused roster.

            Returns:
                A draft whose recipients leak extra fields.
            """
            self.calls.append(instruction)

            return {
                "meeting": {"title": "T"},
                "recipients": [
                    {
                        "name": "Aarti Rao",
                        "email": "aarti@example.com",
                        "phone": "555",
                        "salary": "420000",
                    }
                ],
                "email": "Dear Team,",
                "employee_count": 1,
            }

    leaky = AutomationAgentAdapter(service=LeakyService())

    result = await leaky.execute("draft_action", {"instruction": "Draft a standup"})

    assert result["recipients"] == [{"name": "Aarti Rao", "email": "aarti@example.com"}]


async def test_malformed_recipient_records_are_skipped_not_passed_through(
    adapter: AutomationAgentAdapter,
) -> None:
    """A recipient that is not a record cannot become an error for the client."""

    class BrokenService(RecordingService):
        """A service returning recipient entries of the wrong shape."""

        def execute(
            self,
            instruction: str,
            employees: list[dict[str, str]] | None = None,
        user_context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Return a recipients list containing junk.

            Args:
                instruction: Unused instruction.
                employees: Unused roster.

            Returns:
                A draft with unusable recipient entries.
            """
            self.calls.append(instruction)

            return {
                "meeting": {"title": "T"},
                "recipients": ["not-a-record", {"nothing": "usable"}, {"name": "A"}],
                "email": "Dear Team,",
                "employee_count": 3,
            }

    broken = AutomationAgentAdapter(service=BrokenService())

    result = await broken.execute("draft_action", {"instruction": "Draft a standup"})

    assert result["recipients"] == [{"name": "A"}]


# --------------------------------------------------------------------------
# Two directories in flight at once
# --------------------------------------------------------------------------


@pytest.fixture
async def http(
    settings: Settings,
    manifest: EmployeeDirectoryManifest,
    service: EmployeeDirectoryService,
) -> AsyncIterator[AsyncClient]:
    """Return a client whose adapter resolves against temporary storage.

    Args:
        settings: Test settings.
        manifest: Temporary manifest store.
        service: The temporary directory service.

    Yields:
        The configured AsyncClient.
    """
    recording = RecordingService()

    adapter = AutomationAgentAdapter(service=recording, directory_service=service)
    registry = AgentRegistry()
    registry.register(adapter)

    application = create_app(settings)
    application.dependency_overrides[get_settings_dep] = lambda: settings
    application.dependency_overrides[get_registry] = lambda: registry
    application.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    application.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal()  # noqa: E501
    application.dependency_overrides[get_employee_directory_manifest] = lambda: manifest
    application.dependency_overrides[get_employee_directory_service] = lambda: service

    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_concurrent_drafts_do_not_leak_recipients(
    http: AsyncClient,
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """Two directories dispatched together resolve independently.

    This is the regression test for swapping shared agent state. With a shared
    mutable roster, one request would resolve the other's recipients.
    """
    first = write_directory(service, manifest, CUSTOM, "first.json")
    second = write_directory(service, manifest, OTHER, "second.json")

    responses = await asyncio.gather(
        http.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "Draft a standup", "directory_id": first},
            },
        ),
        http.post(
            EXECUTE_URL,
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {"instruction": "Draft a standup", "directory_id": second},
            },
        ),
    )

    bodies = [response.json()["data"]["data"] for response in responses]

    assert bodies[0]["recipients"] == CUSTOM
    assert bodies[1]["recipients"] == OTHER
    assert bodies[0]["directory"]["directory_id"] == first
    assert bodies[1]["directory"]["directory_id"] == second


async def test_an_unknown_directory_id_returns_404_over_http(
    http: AsyncClient,
) -> None:
    """The route maps an unusable directory id to 404, never to 200."""
    response = await http.post(
        EXECUTE_URL,
        json={
            "agent": "automation",
            "operation": "draft_action",
            "payload": {"instruction": "Draft a standup", "directory_id": "nope"},
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DIRECTORY_NOT_FOUND"


async def test_a_blank_instruction_is_still_rejected_before_any_lookup(
    adapter: AutomationAgentAdapter,
    service: EmployeeDirectoryService,
    manifest: EmployeeDirectoryManifest,
) -> None:
    """Payload validation still runs in front of the directory lookup."""
    directory_id = write_directory(service, manifest, CUSTOM)

    from app.core.exceptions import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        await adapter.execute(
            "draft_action",
            {"instruction": "  ", "directory_id": directory_id}, user_context=PRINCIPAL)


# --------------------------------------------------------------------------
# The real parser and lookup, with a supplied roster
# --------------------------------------------------------------------------


@pytest.fixture
def build_agent() -> Callable[[], Any]:
    """Return a factory that builds a real AutomationAgent with a stub LLM.

    Returns:
        A factory producing an agent that resolves names without contacting
        Ollama.
    """
    return _build_agent


def _build_agent() -> Any:
    """Build a real AutomationAgent with a stub LLM.

    Returns:
        An agent that resolves names without contacting Ollama.
    """
    from automation_agent.automation_agent import AutomationAgent

    class StubLLM:
        """Stand-in for the Ollama client."""

        def generate(self, prompt: str) -> str:
            """Return a fixed body.

            Args:
                prompt: The drafting prompt, unused.

            Returns:
                A fixed email body.
            """
            return "Dear Team,\n\nDraft body."

    return AutomationAgent(llm=StubLLM())


def test_the_real_parser_uses_the_supplied_roster(build_agent: Callable[[], Any]) -> None:
    """A name absent from the packaged directory still resolves.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    meeting = agent.parse_instruction("Schedule a standup with Aarti", CUSTOM)

    assert meeting["attendees"] == ["Aarti Rao"]


def test_the_real_lookup_uses_the_supplied_roster(build_agent: Callable[[], Any]) -> None:
    """Recipient resolution follows the roster the parser matched against.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    recipients = agent.find_emails(["Aarti Rao"], CUSTOM)

    assert recipients == CUSTOM


def test_the_real_parser_does_not_fall_back_to_the_packaged_directory(
    build_agent: Callable[[], Any],
) -> None:
    """A supplied roster replaces the default rather than adding to it.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    meeting = agent.parse_instruction(f"Schedule a standup with {PACKAGED_ONLY}", CUSTOM)

    assert meeting["attendees"] == []


def test_both_stages_see_the_same_roster(build_agent: Callable[[], Any]) -> None:
    """A parsed attendee is always resolvable in the recipients list.

    Passing different lists to the two stages would produce attendees that no
    recipient can satisfy, which is the signature of that mistake.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    meeting, recipients, _ = agent.execute("Schedule a standup with Aarti", CUSTOM)

    assert set(meeting["attendees"]) == {person["name"] for person in recipients}


def test_a_supplied_roster_does_not_replace_the_agent_state(
    build_agent: Callable[[], Any],
) -> None:
    """Executing with a roster leaves the packaged directory untouched.

    Swapping ``self.employees`` per request would let two concurrent drafts
    resolve recipients from each other's directory.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    packaged = list(agent.employees)

    agent.execute("Schedule a standup with Aarti", CUSTOM)

    assert agent.employees == packaged
    assert agent.employees is not CUSTOM


def test_a_supplied_roster_does_not_replace_the_default_directory(
    build_agent: Callable[[], Any],
) -> None:
    """A later default-path call still uses the packaged directory.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    agent.execute("Schedule a standup with Aarti", CUSTOM)
    meeting = agent.parse_instruction(f"Schedule a standup with {PACKAGED_ONLY}")

    assert meeting["attendees"] == [PACKAGED_ONLY]


def test_concurrent_executes_with_different_rosters_do_not_cross(
    build_agent: Callable[[], Any],
) -> None:
    """Two threads drafting against different rosters stay independent.

    This is the property the whole threading design exists to guarantee. If the
    roster were swapped on the instance instead of threaded through, one thread
    would resolve recipients from the other's directory.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    def draft(instruction: str, roster: list[dict[str, str]]) -> list[dict[str, str]]:
        _, recipients, _ = agent.execute(instruction, roster)

        return recipients

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(draft, "Schedule a standup with Aarti", CUSTOM)
        second = pool.submit(draft, "Schedule a standup with Zoya", OTHER)

        assert first.result() == CUSTOM
        assert second.result() == OTHER


def test_the_default_roster_is_unchanged_when_none_is_supplied(
    build_agent: Callable[[], Any],
) -> None:
    """The packaged directory still resolves when no roster is passed.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    meeting = agent.parse_instruction(f"Schedule a standup with {PACKAGED_ONLY}")

    assert meeting["attendees"] == [PACKAGED_ONLY]


def test_first_name_fallback_still_works_with_a_supplied_roster(
    build_agent: Callable[[], Any],
) -> None:
    """A bare first name resolves against the roster that was supplied.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    meeting = agent.parse_instruction("Schedule a standup with Aarti", CUSTOM)

    assert meeting["attendees"] == ["Aarti Rao"]


def test_a_shared_surname_still_resolves_to_nobody(
    build_agent: Callable[[], Any],
) -> None:
    """The surname-only fix holds for an uploaded roster too.

    Args:
        build_agent: Factory returning a real agent with a stub LLM.
    """
    agent = build_agent()

    meeting = agent.parse_instruction("Schedule a standup with Rao", CUSTOM)

    assert meeting["attendees"] == []
