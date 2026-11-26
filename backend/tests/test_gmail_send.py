"""Tests for the Gmail sending service.

All Gmail API calls are mocked. No real email is ever sent.
"""

from __future__ import annotations

import base64
from email import message_from_bytes

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    GoogleOAuthNotConfiguredError,
    ValidationFailedError,
)
from app.services import gmail_send


def _settings() -> Settings:
    return Settings(
        environment="test",
        debug=False,
        cors_origins=["http://testserver"],
        log_level="WARNING",
        google_oauth_enabled=True,
        google_client_id="client-id.apps.googleusercontent.com",
        google_client_secret="client-secret",
        google_token_encryption_key="test-encryption-passphrase",
    )


def test_build_raw_message_is_multipart_alternative() -> None:
    raw = gmail_send.build_raw_message(
        sender="hr@example.test",
        recipients=["a@example.test", "b@example.test"],
        subject="Hello world",
        html_body="<p>Hi</p>",
    )
    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    msg = message_from_bytes(decoded)
    assert msg.is_multipart()
    assert msg.get_content_type() == "multipart/alternative"
    assert msg["To"] == "a@example.test, b@example.test"
    from email.header import decode_header

    decoded_subject = "".join(
        (part.decode(enc or "utf-8") if isinstance(part, bytes) else part)
        for part, enc in decode_header(msg["Subject"])
    )
    assert decoded_subject == "Hello world"
    parts = msg.get_payload()
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert parts[1].get_content_type() == "text/html"


def test_build_raw_message_handles_non_ascii_subject() -> None:
    raw = gmail_send.build_raw_message(
        sender="hr@example.test",
        recipients=["a@example.test"],
        subject="Café résumé",
        html_body="<p>x</p>",
    )
    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    msg = message_from_bytes(decoded)
    from email.header import decode_header

    decoded_subject = "".join(
        (part.decode(enc or "utf-8") if isinstance(part, bytes) else part)
        for part, enc in decode_header(msg["Subject"])
    )
    assert decoded_subject == "Café résumé"


def test_validate_recipients_rejects_empty() -> None:
    with pytest.raises(ValidationFailedError):
        gmail_send._validate_recipients([], 5)


def test_validate_recipients_rejects_malformed() -> None:
    with pytest.raises(ValidationFailedError):
        gmail_send._validate_recipients([{"name": "x", "email": "not-an-email"}], 5)


def test_validate_recipients_dedups() -> None:
    out = gmail_send._validate_recipients(
        [
            {"name": "a", "email": "a@example.test"},
            {"name": "b", "email": "A@EXAMPLE.TEST"},
        ],
        5,
    )
    assert len(out) == 1


def test_text_to_html_preserves_paragraphs() -> None:
    html = gmail_send._text_to_html("Para one.\n\nPara two.")
    assert "<p>Para one.</p>" in html
    assert "<p>Para two.</p>" in html


def test_text_to_html_escapes_special_chars() -> None:
    html = gmail_send._text_to_html("a < b & c > d")
    stripped = html.replace("<p>", "").replace("<br>", "").replace("</p>", "")
    assert "<" not in stripped or "&lt;" in html
    assert "&lt;" in html
    assert "&amp;" in html
    assert "&gt;" in html


def test_text_to_html_converts_single_newlines() -> None:
    html = gmail_send._text_to_html("line1\nline2")
    assert "<br>" in html


def test_looks_like_html_detects_tags() -> None:
    assert gmail_send._looks_like_html("<p>hi</p>") is True
    assert gmail_send._looks_like_html("plain text") is False


def test_strip_html_preserves_paragraph_breaks() -> None:
    out = gmail_send._strip_html("<p>First</p><p>Second</p>")
    assert "First" in out
    assert "Second" in out
    assert "\n" in out


def test_build_raw_message_plain_text_preserves_newlines_in_plain_part() -> None:
    body = "Para one.\n\nPara two."
    raw = gmail_send.build_raw_message(
        sender="hr@example.test",
        recipients=["a@example.test"],
        subject="Hi",
        html_body=body,
    )
    import base64
    from email import message_from_bytes

    msg = message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))
    parts = msg.get_payload()
    plain = parts[0].get_payload(decode=True).decode("utf-8")
    assert "Para one." in plain
    assert "Para two." in plain
    assert "\n" in plain


def test_build_raw_message_html_input_not_escaped() -> None:
    body = "<p><b>Bold</b> text</p><ul><li>item</li></ul>"
    raw = gmail_send.build_raw_message(
        sender="hr@example.test",
        recipients=["a@example.test"],
        subject="Hi",
        html_body=body,
    )
    import base64
    from email import message_from_bytes

    msg = message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))
    parts = msg.get_payload()
    html_part = parts[1].get_payload(decode=True).decode("utf-8")
    assert "<b>Bold</b>" in html_part
    assert "<li>item</li>" in html_part


def test_build_raw_message_utf8() -> None:
    body = "Café résumé — naïve"
    raw = gmail_send.build_raw_message(
        sender="hr@example.test",
        recipients=["a@example.test"],
        subject="Ünïcödé",
        html_body=body,
    )
    import base64
    from email import message_from_bytes

    msg = message_from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))
    parts = msg.get_payload()
    html_part = parts[1].get_payload(decode=True).decode("utf-8")
    assert "Café" in html_part


def test_validate_recipients_enforces_max() -> None:
    with pytest.raises(ValidationFailedError):
        gmail_send._validate_recipients(
            [{"name": f"u{i}", "email": f"u{i}@example.test"} for i in range(3)],
            2,
        )


@pytest.mark.asyncio
async def test_send_html_email_requires_oauth_enabled() -> None:
    settings = _settings()
    settings.google_oauth_enabled = False
    with pytest.raises(GoogleOAuthNotConfiguredError):
        await gmail_send.send_html_email(
            organization_id="org-1",
            sender_user_id="user-1",
            recipients=[{"name": "a", "email": "a@example.test"}],
            subject="Hi",
            html_body="<p>hi</p>",
            idempotency_key="key-1",
            settings=settings,
        )


@pytest.mark.asyncio
async def test_send_html_email_rejects_oversized_html() -> None:
    settings = _settings()
    with pytest.raises(ValidationFailedError):
        await gmail_send.send_html_email(
            organization_id="org-1",
            sender_user_id="user-1",
            recipients=[{"name": "a", "email": "a@example.test"}],
            subject="Hi",
            html_body="x" * (settings.gmail_send_max_html_bytes + 10),
            idempotency_key="key-2",
            settings=settings,
        )
