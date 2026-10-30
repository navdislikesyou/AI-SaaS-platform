from threading import Event

from backend.automation_agent.meeting_setup import MeetingSetup
from backend.automation_agent.email.email_generator import EmailGenerator
from backend.automation_agent.email.gmail_service import GmailService
from backend.automation_agent.scheduler import MeetingScheduler


def main():

    meeting = MeetingSetup().run()

    if not meeting:
        print("Meeting setup cancelled.")
        return

    print("\nPreparing meeting invitations...")

    generator = EmailGenerator()
    gmail = GmailService()

    for recipient in meeting["participants"]:

        email = generator.generate(
            notification_type="invitation",
            meeting=meeting,
            recipient=recipient,
            sender_name="AI SaaS Platform"
        )

        confirm = input(
            f"Send invitation to {recipient['name']} "
            f"({recipient['email']})? (yes/no): "
        )

        if confirm.lower() == "yes":

            gmail.send_email(
                recipient=email["to"],
                subject=email["subject"],
                html_body=email["html_body"]
            )

            print(f"[SENT] Invitation to {recipient['name']}")

        else:
            print(f"[SKIPPED] {recipient['name']}")

    scheduler = MeetingScheduler()

    scheduler.schedule_meeting(meeting)

    print("\nMeeting automation is active.")
    print("Scheduled reminders are stored in SQLite.")
    print("Keep this terminal running to execute scheduled reminders.")
    print("Press Ctrl+C to stop the scheduler.")

    try:
        Event().wait()

    except KeyboardInterrupt:
        print("\nStopping scheduler...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()