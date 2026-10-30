import os
import base64
from pathlib import Path
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GmailService:
    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.credentials_path = self.base_dir / "credentials.json"
        self.token_path = self.base_dir / "token.json"

        self.service = self._authenticate()

    def _authenticate(self):
        credentials = None

        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(
                str(self.token_path), self.SCOPES
            )

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), self.SCOPES
            )
            credentials = flow.run_local_server(port=0)

        with open(self.token_path, "w") as token_file:
            token_file.write(credentials.to_json())

        return build("gmail", "v1", credentials=credentials)

    def send_email(self, recipient, subject, html_body):
        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = subject

        message.set_content("Please view this email in an HTML-compatible email client.")
        message.add_alternative(html_body, subtype="html")

        encoded_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode()

        result = self.service.users().messages().send(
            userId="me",
            body={"raw": encoded_message}
        ).execute()

        return result.get("id")