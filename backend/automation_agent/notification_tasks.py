from backend.automation_agent.email.gmail_service import GmailService
from backend.automation_agent.email.email_generator import EmailGenerator


def send_notification(notification_type, meeting, recipient):
    gmail = GmailService()
    generator = EmailGenerator()

    email = generator.generate(
        notification_type=notification_type,
        meeting=meeting,
        recipient=recipient,
        sender_name="AI SaaS Platform"
    )

    message_id = gmail.send_email(
        recipient=email["to"],
        subject=email["subject"],
        html_body=email["html_body"]
    )

    print(
        f"[SENT] {notification_type} to "
        f"{recipient['name']} ({recipient['email']})"
    )

    return message_id