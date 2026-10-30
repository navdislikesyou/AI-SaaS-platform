from backend.automation_agent.email.gmail_service import GmailService


gmail = GmailService()

recipient = input("Enter your own email address: ")

confirm = input(f"Send a test email to {recipient}? (yes/no): ")

if confirm.lower() == "yes":
    message_id = gmail.send_email(
        recipient=recipient,
        subject="Automation Agent - Gmail Test",
        html_body="""
        <html>
            <body>
                <h2>Gmail Integration Successful!</h2>
                <p>Your Automation Agent can now send emails.</p>
            </body>
        </html>
        """
    )

    print("Email sent successfully.")
    print("Message ID:", message_id)
else:
    print("Test cancelled.")