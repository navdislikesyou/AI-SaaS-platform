import json
import re
from pathlib import Path

from automation_agent.llm.local_llm import LocalLLM


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

    def parse_instruction(self, instruction):

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

        # A day number followed by a word, e.g. "5 March" or "12 April 2026".
        # The negative lookahead rejects "9 AM" / "9 pm", which otherwise match
        # because AM and PM are words: without it a time gets read as the date.
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

        for employee in self.employees:

            name = employee["name"].lower()

            if name in text:

                attendees.append(employee["name"])

                matched.add(name)

        for employee in self.employees:

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

    def find_emails(self, attendees):

        recipients = []

        for attendee in attendees:

            for employee in self.employees:

                if employee["name"] == attendee:

                    recipients.append(employee)

                    break

        return recipients

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

    def execute(self, instruction):

        meeting = self.parse_instruction(instruction)

        recipients = self.find_emails(
            meeting["attendees"]
        )

        email = self.generate_email(
            meeting,
            recipients,
        )

        return meeting, recipients, email