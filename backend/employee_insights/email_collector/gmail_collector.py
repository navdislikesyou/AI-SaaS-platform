import base64
import json
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GmailCollector:
    """Read-only Gmail client that maps messages into plain dictionaries.

    Two ways of obtaining a client exist. The default runs the installed-app
    flow against a local ``credentials.json``/``token.json``, which only works
    on the machine hosting the backend. The stored-credential path used by the
    platform takes an already-authorized service (or credential) instead, so
    no local file and no interactive browser flow is ever involved.
    """

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self, credentials: Credentials | None = None, service: Any | None = None):
        """Collect Gmail messages, either from a supplied client or by authenticating.

        Args:
            credentials: An already-authorized Google credential. When given,
                the installed-app flow is skipped entirely.
            service: An already-built Gmail API client. When given it is used
                as-is, so a caller that owns its own credential (for example
                one decrypted from the platform's encrypted store) never
                touches ``token.json`` or opens a browser.
        """
        self.email_directory = Path(__file__).resolve().parents[2] / "automation_agent" / "email"

        self.credentials_path = self.email_directory / "credentials.json"

        self.token_path = Path(__file__).resolve().parent / "token.json"

        self.service = service if service is not None else self._authenticate(credentials)

    @classmethod
    def from_stored_credentials(cls, credentials_json: str) -> "GmailCollector":
        """Build a collector from an existing OAuth credential JSON document.

        Args:
            credentials_json: The serialized ``google.oauth2.credentials.Credentials``,
                typically produced by ``Credentials.to_json()``.

        Returns:
            A :class:`GmailCollector` ready to call the Gmail API.
        """
        credentials = Credentials.from_authorized_user_info(
            json.loads(credentials_json), cls.SCOPES
        )
        return cls(credentials=credentials)

    def _authenticate(self, credentials: Credentials | None):
        # When a caller supplies an existing (stored and refreshed) credential,
        # use it directly instead of running the local-server installed-app flow.
        # That flow only works on the machine hosting the backend and cannot be
        # driven by a browser-based frontend.
        if credentials is not None:
            return build("gmail", "v1", credentials=credentials)

        credentials_stored = None

        if self.token_path.exists():
            credentials_stored = Credentials.from_authorized_user_file(
                str(self.token_path), self.SCOPES
            )

        if credentials_stored and credentials_stored.expired and credentials_stored.refresh_token:
            credentials_stored.refresh(Request())

        if not credentials_stored or not credentials_stored.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), self.SCOPES
            )

            credentials_stored = flow.run_local_server(port=0)

            self.token_path.write_text(credentials_stored.to_json(), encoding="utf-8")

        return build("gmail", "v1", credentials=credentials_stored)

    def _decode_body(self, data):
        if not data:
            return ""

        decoded = base64.urlsafe_b64decode(data)
        return decoded.decode("utf-8", errors="replace")

    def _extract_body(self, payload):
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            return self._decode_body(payload.get("body", {}).get("data"))

        parts = payload.get("parts", [])

        for part in parts:
            if part.get("mimeType") == "text/plain":
                body = self._decode_body(part.get("body", {}).get("data"))

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
        response = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = response.get("messages", [])

        collected_emails = []

        for message in messages:
            email_data = (
                self.service.users()
                .messages()
                .get(userId="me", id=message["id"], format="full")
                .execute()
            )

            payload = email_data.get("payload", {})
            headers = payload.get("headers", [])

            collected_emails.append(
                {
                    "email_id": email_data["id"],
                    "thread_id": email_data.get("threadId"),
                    "sender": self._get_header(headers, "From"),
                    "recipients": self._get_header(headers, "To"),
                    "subject": self._get_header(headers, "Subject"),
                    "date": self._get_header(headers, "Date"),
                    "body": self._extract_body(payload),
                }
            )

        return collected_emails


if __name__ == "__main__":
    collector = GmailCollector()

    emails = collector.collect_emails(query="in:anywhere", max_results=10)

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
