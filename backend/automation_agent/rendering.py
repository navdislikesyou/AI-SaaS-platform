"""Deterministic HTML rendering for Automation Agent drafts.

Turns a parsed meeting into a subject line and a complete HTML email body
using one of the templates shipped in ``templates/``. Rendering is a pure
function of its inputs: no model, no network, and no side effects beyond
reading the template files. That is what keeps ``draft_html`` cheap enough
to run on every request.

This module drafts. It returns HTML as a string and never transmits it.
Nothing here imports a mail transport, and
``tests/test_automation_adapter.py`` scans the Automation source files to
keep it that way.

Date, time, and venue are passed through unchanged.
:meth:`automation_agent.automation_agent.AutomationAgent.parse_instruction`
already returns human-readable values such as ``"5 March"`` and ``"10 AM"``,
or ``"Not Specified"`` when the instruction named neither. Reparsing them
here would mean second-guessing a string the parser deliberately left loose.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Directory holding the HTML templates that ship with the agent.
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

#: Template filename and subject pattern for each supported notification type.
TEMPLATES: dict[str, tuple[str, str]] = {
    "meeting_invitation": ("meeting_invitation.html", "Meeting Invitation: {title}"),
    "reminder_24h": ("reminder_24h.html", "Reminder: {title} - Tomorrow"),
    "reminder_30m": ("reminder_30m.html", "Upcoming Meeting: {title}"),
}

#: Notification types a client may request, in catalog order.
SUPPORTED_TEMPLATES: tuple[str, ...] = tuple(TEMPLATES)

#: Template used when a payload does not name one.
DEFAULT_TEMPLATE = "meeting_invitation"

#: Sign-off printed at the foot of every body. Matches the plain-text draft.
DEFAULT_SENDER_NAME = "Project Management Office"

#: Greeting used when no recipient resolved. A draft is still worth returning
#: without a named recipient; inventing a name would not be.
DEFAULT_GREETING = "Team"


class InvitationRenderer:
    """Render a parsed meeting as a subject line and an HTML body."""

    def __init__(self, template_dir: Path | None = None) -> None:
        """Load the packaged templates into a Jinja environment.

        Args:
            template_dir: Directory holding the templates. Defaults to the
                ``templates/`` directory shipped beside this module.
        """
        # Imported here rather than at module scope so that importing this
        # module for its template constants does not require the optional
        # agent dependency to be installed. A construction failure surfaces
        # through the adapter's connect guard and degrades the agent to
        # unavailable instead of breaking import.
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        directory = Path(template_dir) if template_dir is not None else TEMPLATE_DIR

        self._environment = Environment(
            loader=FileSystemLoader(str(directory)),
            # Values come out of an untrusted instruction and an uploaded
            # directory, so they are escaped on the way into the markup.
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render(
        self,
        meeting: dict[str, Any],
        recipients: list[dict[str, Any]],
        template: str = DEFAULT_TEMPLATE,
        reason: str = "",
        sender_name: str = DEFAULT_SENDER_NAME,
    ) -> dict[str, str]:
        """Render one meeting into a subject and an HTML body.

        Args:
            meeting: The parsed meeting. ``title``, ``date``, ``time``, and
                ``venue`` are already display-ready and are passed through.
            recipients: Resolved employee records. The first named recipient
                greets the body; with none, the greeting falls back to
                ``Team``.
            template: Which shipped template to render.
            reason: Optional purpose line. A blank value omits the row rather
                than printing an empty one.
            sender_name: Sign-off printed at the foot of the body.

        Returns:
            A mapping holding ``subject`` and ``html_body``.

        Raises:
            ValueError: If ``template`` is not one of the shipped templates.
        """
        if template not in TEMPLATES:
            raise ValueError(f"Unknown template: {template!r}")

        filename, subject_pattern = TEMPLATES[template]

        context = {
            "recipient_name": _greeting(recipients),
            "sender_name": sender_name,
            "title": str(meeting.get("title") or "Meeting"),
            "reason": (reason or "").strip(),
            "date": str(meeting.get("date") or "Not Specified"),
            "time": str(meeting.get("time") or "Not Specified"),
            "venue": str(meeting.get("venue") or "Not Specified"),
        }

        body = self._environment.get_template(filename).render(**context)

        subject = subject_pattern.format(title=context["title"])

        logger.debug("automation_render template=%s subject=%s", template, subject)

        return {"subject": subject, "html_body": body}


def _greeting(recipients: list[dict[str, Any]]) -> str:
    """Return the name that greets the body.

    Args:
        recipients: Resolved employee records, possibly empty.

    Returns:
        The first recipient's name, or ``Team`` when no record carries one.
    """
    if recipients and isinstance(recipients[0], dict):
        name = str(recipients[0].get("name") or "").strip()

        if name:
            return name

    return DEFAULT_GREETING
