"""Tests for the Gmail collector's client injection and message mapping.

The collector is the only place the platform talks to the Gmail API during a
sync, so these tests pin two things: an injected client is used verbatim with
no local ``token.json`` and no interactive browser flow, and the list call is
made with the parameters ``users().messages().list`` actually accepts.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from employee_insights.email_collector import gmail_collector
from employee_insights.email_collector.gmail_collector import GmailCollector

LISTED = [{"id": "msg-1", "threadId": "thread-1"}]


def _b64url(text: str) -> str:
    """Encode text the way Gmail encodes a message part.

    Args:
        text: The raw part contents.

    Returns:
        The URL-safe base64 representation.
    """
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _message(
    message_id: str,
    subject: str,
    body_text: str,
    sender: str = "Sam Manager <sam@example.test>",
) -> dict[str, Any]:
    """Build one Gmail ``messages.get`` response.

    Args:
        message_id: The message identifier.
        subject: The Subject header value.
        body_text: The plain-text body contents.
        sender: The From header value.

    Returns:
        A payload shaped the way the Gmail API returns it.
    """
    return {
        "id": message_id,
        "threadId": "thread-1",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": "hr@example.test"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Tue, 18 Nov 2026 10:00:00 +0000"},
            ],
            "body": {"data": _b64url(body_text)},
        },
    }


class _Request:
    """A stand-in for a googleapiclient request object."""

    def __init__(self, payload: dict[str, Any]) -> None:
        """Store the response this request will return.

        Args:
            payload: The body ``execute()`` should yield.
        """
        self._payload = payload

    def execute(self) -> dict[str, Any]:
        """Return the canned response.

        Returns:
            A copy of the stored payload.
        """
        return dict(self._payload)


class FakeGmailService:
    """Answer ``list`` and ``get`` from fixtures and record the arguments used."""

    def __init__(
        self,
        listed: list[dict[str, str]],
        fetched: dict[str, dict[str, Any]],
    ) -> None:
        """Initialize the fake client.

        Args:
            listed: Messages ``list`` should report.
            fetched: Full messages keyed by id, served to ``get``.
        """
        self._listed = listed
        self._fetched = fetched
        self.list_kwargs: dict[str, Any] | None = None
        self.get_kwargs: dict[str, Any] | None = None

    def users(self) -> FakeGmailService:
        """Return the users collection.

        Returns:
            This fake, which also exposes the message methods.
        """
        return self

    def messages(self) -> FakeGmailService:
        """Return the messages collection.

        Returns:
            This fake, which exposes ``list`` and ``get``.
        """
        return self

    def list(self, **kwargs: Any) -> _Request:
        """Serve one page of message summaries.

        Args:
            kwargs: The parameters the collector passed.

        Returns:
            A request yielding the canned list response.
        """
        self.list_kwargs = kwargs
        return _Request({"messages": list(self._listed)})

    def get(self, **kwargs: Any) -> _Request:
        """Serve one full message.

        Args:
            kwargs: The parameters the collector passed, including ``id``.

        Returns:
            A request yielding the canned message.

        Raises:
            KeyError: If the message id was not provided as a fixture.
        """
        self.get_kwargs = kwargs
        return _Request(self._fetched[kwargs["id"]])


@pytest.fixture(autouse=True)
def _refuse_the_installed_app_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test opens the interactive local-server flow.

    That flow reads ``credentials.json`` and starts a browser on the server
    machine, which is exactly what the stored-credential path exists to avoid.
    """

    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the installed-app OAuth flow must not run in these tests")

    monkeypatch.setattr(gmail_collector, "InstalledAppFlow", _explode)


def test_an_injected_service_skips_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    """A supplied client is used as-is; ``_authenticate`` is never reached."""
    marker = object()

    def _explode(self: Any, credentials: Any = None) -> Any:
        raise AssertionError("_authenticate must not run when a service is supplied")

    monkeypatch.setattr(GmailCollector, "_authenticate", _explode)

    collector = GmailCollector(service=marker)

    assert collector.service is marker


def test_collect_emails_passes_a_query_and_a_page_size() -> None:
    """The list call carries ``q`` and ``maxResults``, the parameters it accepts."""
    service = FakeGmailService(
        listed=LISTED,
        fetched={"msg-1": _message("msg-1", "Weekly update", "All on track.")},
    )
    collector = GmailCollector(service=service)

    collector.collect_emails(query="newer_than:30d -in:spam -in:trash", max_results=7)

    assert service.list_kwargs == {
        "userId": "me",
        "q": "newer_than:30d -in:spam -in:trash",
        "maxResults": 7,
    }


def test_collect_emails_maps_headers_and_body() -> None:
    """Each message becomes a flat dictionary with the fields a sync needs."""
    service = FakeGmailService(
        listed=LISTED,
        fetched={
            "msg-1": _message(
                "msg-1",
                "Q4 review for Jon Clerk",
                "Jon Clerk did an excellent job.",
            )
        },
    )
    collector = GmailCollector(service=service)

    emails = collector.collect_emails(query="in:anywhere", max_results=10)

    assert len(emails) == 1
    assert emails[0]["email_id"] == "msg-1"
    assert emails[0]["thread_id"] == "thread-1"
    assert emails[0]["subject"] == "Q4 review for Jon Clerk"
    assert emails[0]["sender"] == "Sam Manager <sam@example.test>"
    assert emails[0]["recipients"] == "hr@example.test"
    assert emails[0]["date"] == "Tue, 18 Nov 2026 10:00:00 +0000"
    assert emails[0]["body"] == "Jon Clerk did an excellent job."


def test_extract_body_prefers_a_top_level_text_part() -> None:
    """A ``text/plain`` payload is decoded without descending into parts."""
    collector = GmailCollector(service=object())

    payload = {"mimeType": "text/plain", "body": {"data": _b64url("plain body")}}

    assert collector._extract_body(payload) == "plain body"


def test_extract_body_falls_back_to_a_nested_text_part() -> None:
    """A multipart message yields its first non-empty ``text/plain`` part."""
    collector = GmailCollector(service=object())

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64url("<b>html</b>")}},
            {"mimeType": "text/plain", "body": {"data": _b64url("nested body")}},
        ],
    }

    assert collector._extract_body(payload) == "nested body"


def test_extract_body_returns_empty_when_no_text_part_exists() -> None:
    """A message with no decodable text part yields an empty string, not None."""
    collector = GmailCollector(service=object())

    assert collector._extract_body({"mimeType": "text/html", "parts": []}) == ""
    assert collector._extract_body({}) == ""


def test_get_header_matches_case_insensitively_and_defaults_to_empty() -> None:
    """Header lookup is case-insensitive and reports a missing header as empty."""
    collector = GmailCollector(service=object())
    headers = [{"name": "Subject", "value": "Hello"}]

    assert collector._get_header(headers, "subject") == "Hello"
    assert collector._get_header(headers, "SUBJECT") == "Hello"
    assert collector._get_header(headers, "Date") == ""


def test_from_stored_credentials_builds_a_client_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored credential builds a client without ``token.json`` or a browser."""
    marker = object()
    built: dict[str, Any] = {}

    def fake_build(api: str, version: str, credentials: Any = None) -> Any:
        built["api"] = api
        built["version"] = version
        built["credentials"] = credentials
        return marker

    monkeypatch.setattr(gmail_collector, "build", fake_build)

    collector = GmailCollector.from_stored_credentials(
        json.dumps(
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
    )

    # The autouse fixture would have raised had the local flow been reached.
    assert collector.service is marker
    assert built["api"] == "gmail"
    assert built["version"] == "v1"
    assert built["credentials"].refresh_token == "refresh-token"
    assert built["credentials"].token == "access-token"
