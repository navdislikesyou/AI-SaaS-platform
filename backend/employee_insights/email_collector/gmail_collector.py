import base64
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GmailCollector:

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self):

        self.email_directory = (
            Path(__file__).resolve().parents[2]
            / "automation_agent"
            / "email"
        )

        self.credentials_path = (
            self.email_directory / "credentials.json"
        )

        self.token_path = (
            Path(__file__).resolve().parent / "token.json"
        )

        self.service = self._authenticate()

    def _authenticate(self):

        credentials = None

        if self.token_path.exists():

            credentials = Credentials.from_authorized_user_file(
                str(self.token_path),
                self.SCOPES
            )

        if credentials and credentials.expired and credentials.refresh_token:

            credentials.refresh(Request())

        if not credentials or not credentials.valid:

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path),
                self.SCOPES
            )

            credentials = flow.run_local_server(port=0)

            self.token_path.write_text(
                credentials.to_json(),
                encoding="utf-8"
            )

        return build("gmail", "v1", credentials=credentials)

    def _decode_body(self, data):

        if not data:
            return ""

        decoded = base64.urlsafe_b64decode(data)
        return decoded.decode("utf-8", errors="replace")

    def _extract_body(self, payload):

        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":

            return self._decode_body(
                payload.get("body", {}).get("data")
            )

        parts = payload.get("parts", [])

        for part in parts:

            if part.get("mimeType") == "text/plain":

                body = self._decode_body(
                    part.get("body", {}).get("data")
                )

                if body:
                    return body

        for part in parts:

            body = self._extract_body(part)

            if body:
                return body

        return ""

    def _get_header(self, headers, name):

        for header in headers:

            if header["name"].lower() == name.lower():
                return header["value"]

        return ""

    def collect_emails(self, query="in:anywhere", max_results=100):

        response = self.service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()

        messages = response.get("messages", [])

        collected_emails = []

        for message in messages:

            email_data = self.service.users().messages().get(
                userId="me",
                id=message["id"],
                format="full"
            ).execute()

            payload = email_data.get("payload", {})
            headers = payload.get("headers", [])

            collected_emails.append({
                "email_id": email_data["id"],
                "thread_id": email_data.get("threadId"),
                "sender": self._get_header(headers, "From"),
                "recipients": self._get_header(headers, "To"),
                "subject": self._get_header(headers, "Subject"),
                "date": self._get_header(headers, "Date"),
                "body": self._extract_body(payload)
            })

        return collected_emails


if __name__ == "__main__":

    collector = GmailCollector()

    emails = collector.collect_emails(
        query="in:anywhere",
        max_results=10
    )

    print(f"\nCollected {len(emails)} emails\n")

    for email in emails:

        print("=" * 70)
        print("Subject:", email["subject"])
        print("From:", email["sender"])
        print("To:", email["recipients"])
        print("Date:", email["date"])
        print("Email ID:", email["email_id"])
        print("\nBody:")
        print(email["body"][:500])