"""Unit tests for the Automation Agent's HTML rendering.

These cover :class:`automation_agent.rendering.InvitationRenderer`, which turns
a parsed meeting into a subject line and a complete HTML body. Rendering is a
pure function of its inputs: no model, no network, and no mail transport, so
these run on CPU with no Ollama server and no external service.

Two properties matter beyond the shape of the output. The body is escaped on
the way in, because the meeting details come from an untrusted instruction and
the roster can come from an uploaded directory. And the renderer drafts only:
it returns a string and has no way to transmit one.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

# Jinja is imported when a renderer is constructed, not when its module is
# loaded, so the skip has to happen before the fixture builds one.
pytest.importorskip("jinja2")

from automation_agent.rendering import (  # noqa: E402
    DEFAULT_TEMPLATE,
    SUPPORTED_TEMPLATES,
    TEMPLATE_DIR,
    TEMPLATES,
    InvitationRenderer,
)

RENDERING_SOURCE = Path("automation_agent/rendering.py")

#: Modules that would indicate the renderer could transmit what it renders.
FORBIDDEN_IMPORTS = {
    "smtplib",
    "email",
    "poplib",
    "imaplib",
    "requests",
    "httpx",
    "urllib.request",
    "urllib3",
    "googleapiclient",
    "google.oauth2",
    "msal",
    "socket",
}

#: A parsed meeting, in the shape ``parse_instruction`` returns.
MEETING: dict[str, Any] = {
    "title": "Sprint Planning",
    "date": "5 March",
    "time": "10 AM",
    "venue": "Conference Room A",
}

RECIPIENTS = [{"name": "Navneet Verma", "email": "navneet@example.com"}]


@pytest.fixture
def renderer() -> InvitationRenderer:
    """Return a renderer over the templates that ship with the agent.

    Returns:
        A renderer backed by the packaged template directory.
    """
    return InvitationRenderer()


def test_every_shipped_template_file_exists() -> None:
    """Each advertised template has a file behind it.

    The catalogue and the directory could drift apart: renaming a file would
    otherwise leave a template that is advertised, accepted, and then fails to
    render at request time.
    """
    for filename, _ in TEMPLATES.values():
        assert (TEMPLATE_DIR / filename).is_file(), filename


def test_render_returns_a_complete_html_document(
    renderer: InvitationRenderer,
) -> None:
    """The body is a whole document, not a fragment a client has to repair."""
    rendered = renderer.render(MEETING, RECIPIENTS)

    body = rendered["html_body"]

    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert body.rstrip().endswith("</html>")
    assert isinstance(rendered["subject"], str)
    assert rendered["subject"]


def test_render_fills_in_the_parsed_meeting(
    renderer: InvitationRenderer,
) -> None:
    """Every parsed field reaches the body, verbatim and in full."""
    body = renderer.render(MEETING, RECIPIENTS)["html_body"]

    for value in MEETING.values():
        assert value in body


@pytest.mark.parametrize("template", list(SUPPORTED_TEMPLATES))
def test_every_shipped_template_renders(
    renderer: InvitationRenderer,
    template: str,
) -> None:
    """Each advertised template renders without raising."""
    rendered = renderer.render(MEETING, RECIPIENTS, template=template)

    assert rendered["html_body"].lstrip().startswith("<!DOCTYPE html>")
    assert MEETING["title"] in rendered["html_body"]


def test_each_template_produces_a_different_body(
    renderer: InvitationRenderer,
) -> None:
    """The three templates are three drafts, not one file under three names."""
    bodies = {
        template: renderer.render(MEETING, RECIPIENTS, template=template)["html_body"]
        for template in SUPPORTED_TEMPLATES
    }

    assert len(set(bodies.values())) == len(SUPPORTED_TEMPLATES)


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        pytest.param("meeting_invitation", "Meeting Invitation: Sprint Planning", id="invitation"),
        pytest.param("reminder_24h", "Reminder: Sprint Planning - Tomorrow", id="reminder_24h"),
        pytest.param("reminder_30m", "Upcoming Meeting: Sprint Planning", id="reminder_30m"),
    ],
)
def test_subject_follows_the_template(
    renderer: InvitationRenderer,
    template: str,
    expected: str,
) -> None:
    """The subject line is derived from the template and the meeting title."""
    assert renderer.render(MEETING, RECIPIENTS, template=template)["subject"] == expected


def test_the_default_template_is_an_invitation(
    renderer: InvitationRenderer,
) -> None:
    """A caller that names no template gets the invitation, by name."""
    rendered = renderer.render(MEETING, RECIPIENTS, template=DEFAULT_TEMPLATE)

    assert rendered["subject"] == "Meeting Invitation: Sprint Planning"


def test_an_unknown_template_is_rejected(
    renderer: InvitationRenderer,
) -> None:
    """A template that does not exist fails loudly rather than rendering nothing.

    A blank body returned as success would reach a client as a drafted email
    with nothing in it.

    Args:
        renderer: The renderer under test.
    """
    with pytest.raises(ValueError, match="Unknown template"):
        renderer.render(MEETING, RECIPIENTS, template="invoice")


def test_meeting_values_are_html_escaped(
    renderer: InvitationRenderer,
) -> None:
    """Markup in an instruction is escaped, never executed by the reader.

    The venue and title come straight from free text, so an instruction that
    names a venue containing a tag must not have that tag survive as markup.

    Args:
        renderer: The renderer under test.
    """
    meeting = {
        "title": "Sprint Planning",
        "date": "5 March",
        "time": "10 AM",
        "venue": '<script>alert("xss")</script>',
    }

    body = renderer.render(meeting, RECIPIENTS)["html_body"]

    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_a_reason_is_printed_when_given(
    renderer: InvitationRenderer,
) -> None:
    """An optional purpose line appears with the meeting details."""
    body = renderer.render(MEETING, RECIPIENTS, reason="Quarterly planning")["html_body"]

    assert "Quarterly planning" in body


def test_a_blank_reason_omits_the_row(
    renderer: InvitationRenderer,
) -> None:
    """A caller that supplies no purpose gets no empty purpose line."""
    body = renderer.render(MEETING, RECIPIENTS)["html_body"]

    assert "Purpose" not in body


def test_the_first_recipient_greets_the_body(
    renderer: InvitationRenderer,
) -> None:
    """The greeting names the first resolved recipient."""
    recipients = [
        {"name": "Navneet Verma", "email": "navneet@example.com"},
        {"name": "Omkar Shenwai", "email": "omkar.shenwai2023@ssipmt.com"},
    ]

    body = renderer.render(MEETING, recipients)["html_body"]

    assert "Dear Navneet Verma," in body
    assert "Omkar Shenwai" not in body


def test_no_recipients_falls_back_to_a_team_greeting(
    renderer: InvitationRenderer,
) -> None:
    """A draft with no resolved recipient still reads sensibly.

    Inventing a name would be worse than addressing the team, and dropping the
    greeting would leave the body opening mid-sentence.

    Args:
        renderer: The renderer under test.
    """
    body = renderer.render(MEETING, [])["html_body"]

    assert "Dear Team," in body


def test_the_renderer_defines_no_transport_method() -> None:
    """The renderer has no way to send what it rendered.

    Checked by AST so the assertion holds without importing the module, which
    is what keeps a send method from creeping into the new layer unnoticed.
    """
    tree = ast.parse(RENDERING_SOURCE.read_text(encoding="utf-8"))

    methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("__")
    }

    assert not methods & {
        "send",
        "send_email",
        "send_invitation",
        "send_message",
        "create_event",
        "schedule",
        "submit",
    }


def test_the_renderer_imports_no_mail_or_network_client() -> None:
    """No transport library is reachable from the rendering layer."""
    tree = ast.parse(RENDERING_SOURCE.read_text(encoding="utf-8"))
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)

    offenders = {
        module
        for module in modules
        if any(module == bad or module.startswith(f"{bad}.") for bad in FORBIDDEN_IMPORTS)
    }

    assert not offenders, f"rendering imports side-effect modules: {sorted(offenders)}"
