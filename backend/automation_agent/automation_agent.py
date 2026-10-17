import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from automation_agent.llm.local_llm import LocalLLM

#: Phrases that mark a meeting as held online, in priority order. A named
#: platform is checked first, because "on Zoom" identifies the venue more
#: precisely than "online meeting" does.
ONLINE_VENUE_MARKERS = (
    ("google meet", "Google Meet"),
    ("microsoft teams", "Microsoft Teams"),
    ("zoom", "Zoom"),
    ("online meeting", "Online meeting"),
    ("virtual meeting", "Online meeting"),
)

#: Venue reported when a meeting is online but names no platform. No joining
#: link is invented: one has to come from whoever owns the call.
ONLINE_VENUE = "Online meeting"


class AutomationAgent:

    def __init__(self, employees_file=None, llm=None):

        self.llm = llm or LocalLLM()

        if employees_file is None:
            employees_file = (
                Path(__file__).parent
                / "data"
                / "employees.json"
            )

        with open(employees_file, "r", encoding="utf-8") as file:
            self.employees = json.load(file)

    def parse_instruction(self, instruction, employees=None):

        employees = self._roster(employees)

        text = instruction.lower()

        # ------------------------
        # Meeting Title
        # ------------------------

        title = "Meeting"

        if "sprint planning" in text:
            title = "Sprint Planning"

        elif "project review" in text:
            title = "Project Review"

        elif "client meeting" in text:
            title = "Client Meeting"

        elif "review meeting" in text:
            title = "Review Meeting"

        elif "standup" in text:
            title = "Daily Standup"

        # ------------------------
        # Date
        # ------------------------

        date = "Not Specified"

        # A relative day is resolved before the numeric pattern, because the two
        # cannot both be present in one sensible instruction and "tomorrow" is
        # the more specific of the two.
        if "tomorrow" in text:
            date = _tomorrow()

        else:
            # A day number followed by a word, e.g. "5 March" or "12 April 2026".
            # The negative lookahead rejects "9 AM" / "9 pm", which otherwise
            # match because AM and PM are words: without it a time gets read as
            # the date.
            date_match = re.search(
                r"\d{1,2}\s+(?!(?:AM|PM)\b)[A-Za-z]+(?:\s+\d{4})?",
                instruction,
                re.IGNORECASE,
            )

            if date_match:
                date = date_match.group()

        # ------------------------
        # Time
        # ------------------------

        time = "Not Specified"

        time_match = re.search(
            r"\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)",
            instruction,
        )

        if time_match:
            time = time_match.group()

        # ------------------------
        # Venue
        # ------------------------

        venue = "Not Specified"

        # An online venue is looked for before the physical-venue pattern. The
        # pattern only matches after a literal " in ", which an online request
        # rarely contains, so without this "the online meeting" would be lost.
        online_venue = _online_venue(text)

        if online_venue:
            venue = online_venue

        else:
            venue_match = re.search(
                r"in\s+(.+?)(?:\s+and\s+invite|\s+with|$)",
                instruction,
                re.IGNORECASE,
            )

            if venue_match:
                venue = venue_match.group(1).strip()

        # ------------------------
        # Attendees
        # ------------------------

        # Full name first, then first name as a fallback. Matching any name
        # part made a shared surname collide: "Navneet Verma" also matched
        # "Pulkita Verma" because both contain "verma". Requiring the full name
        # keeps that unambiguous while still allowing "Omkar" to resolve to
        # "Omkar Shenwai".
        attendees = []

        matched = set()

        for employee in employees:

            name = employee["name"].lower()

            if name in text:

                attendees.append(employee["name"])

                matched.add(name)

        for employee in employees:

            name = employee["name"].lower()

            if name in matched:

                continue

            if name.split()[0] in text:

                attendees.append(employee["name"])

                matched.add(name)

        return {
            "title": title,
            "date": date,
            "time": time,
            "venue": venue,
            "attendees": attendees,
        }

    def find_emails(self, attendees, employees=None):

        employees = self._roster(employees)

        recipients = []

        for attendee in attendees:

            for employee in employees:

                if employee["name"] == attendee:

                    recipients.append(employee)

                    break

        return recipients

    def _roster(self, employees):
        """Return the employee list to work against.

        A caller may pass a different directory for one request. That roster is
        threaded as an argument through parsing, recipient lookup, and drafting
        rather than assigned to ``self.employees``, because the service is shared
        across concurrent requests and swapping instance state would let one
        request resolve recipients from another request's directory.

        Args:
            employees: An employee list to use, or None for the packaged
                directory loaded at construction.

        Returns:
            The employee list to iterate.
        """

        return self.employees if employees is None else employees

    def generate_email(self, meeting, recipients):

        attendee_names = ", ".join(
            person["name"] for person in recipients
        )

        prompt = f"""
You are an enterprise HR assistant.

Write a professional meeting invitation email.

Meeting Title:
{meeting["title"]}

Date:
{meeting["date"]}

Time:
{meeting["time"]}

Venue:
{meeting["venue"]}

Attendees:
{attendee_names}

Instructions:

- Write ONLY the email body.
- Do NOT generate a subject.
- Do NOT use markdown.
- Do NOT say "Here is your email."
- Start directly with "Dear Team,".
- End with:

Regards,

Project Management Office
"""

        return self.llm.generate(prompt)

    def execute(self, instruction, employees=None):

        # Both stages receive the same list object. Splitting them across two
        # lists would let parsing match a name the lookup cannot then resolve.
        roster = self._roster(employees)

        meeting = self.parse_instruction(instruction, roster)

        recipients = self.find_emails(
            meeting["attendees"],
            roster,
        )

        email = self.generate_email(
            meeting,
            recipients,
        )

        return meeting, recipients, email


def _tomorrow():
    """Return the next calendar date in the format a spoken date parses to.

    The current local date is used, so nothing here is hardcoded and the result
    is correct whenever the request is made. The month rollover is handled by the
    date arithmetic, so 31 December correctly yields 1 January.

    Returns:
        Tomorrow as ``"<day> <Month>"``, matching what the numeric date pattern
        produces for "5 March".
    """

    upcoming = datetime.now().date() + timedelta(days=1)

    return f"{upcoming.day} {upcoming.strftime('%B')}"


def _online_venue(text):
    """Return the online venue a lowercased instruction names, if any.

    Args:
        text: The lowercased instruction.

    Returns:
        The named platform, or ``Online meeting`` when the request is online but
        names no platform. None when the request does not look online, so the
        caller can fall back to the physical-venue pattern.
    """

    for marker, venue in ONLINE_VENUE_MARKERS:

        if marker in text:

            return venue

    return None