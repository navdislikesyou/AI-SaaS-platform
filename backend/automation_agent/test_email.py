from backend.automation_agent.meeting_setup import MeetingSetup
from backend.automation_agent.email.email_generator import EmailGenerator


setup = MeetingSetup()
meeting = setup.run()

if meeting:

    generator = EmailGenerator()

    emails = generator.generate_all(
        meeting,
        sender_name="Automation System"
    )

    for notification_type, messages in emails.items():

        print("\n" + "=" * 60)
        print(notification_type.upper())
        print("=" * 60)

        for message in messages:

            print("\nTo:", message["to"])
            print("Subject:", message["subject"])
            print("\n", message["html_body"])