from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape


class EmailGenerator:

    def __init__(self):

        template_dir = (
            Path(__file__).resolve().parent.parent / "templates"
        )

        self.environment = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html"])
        )

        self.templates = {
            "invitation": {
                "file": "meeting_invitation.html",
                "subject": "Meeting Invitation: {title}"
            },
            "reminder_24h": {
                "file": "reminder_24h.html",
                "subject": "Reminder: {title} - Tomorrow"
            },
            "reminder_30m": {
                "file": "reminder_30m.html",
                "subject": "Upcoming Meeting: {title}"
            }
        }

    def generate(self, notification_type, meeting, recipient, sender_name):

        if notification_type not in self.templates:
            raise ValueError("Invalid notification type.")

        config = self.templates[notification_type]

        template = self.environment.get_template(
            config["file"]
        )

        meeting_date = datetime.strptime(
            meeting["date"],
            "%Y-%m-%d"
        )

        meeting_time = datetime.strptime(
            meeting["time"],
            "%H:%M"
        )

        context = {
            "recipient_name": recipient["name"],
            "sender_name": sender_name,
            "title": meeting["title"],
            "reason": meeting["reason"],
            "date": meeting_date.strftime("%d %B %Y"),
            "time": meeting_time.strftime("%I:%M %p"),
            "venue": meeting["venue"]
        }

        return {
            "to": recipient["email"],
            "subject": config["subject"].format(
                title=meeting["title"]
            ),
            "html_body": template.render(**context)
        }

    def generate_all(self, meeting, sender_name):

        emails = {}

        for notification_type in self.templates:

            emails[notification_type] = []

            for recipient in meeting["participants"]:

                email = self.generate(
                    notification_type,
                    meeting,
                    recipient,
                    sender_name
                )

                emails[notification_type].append(email)

        return emails