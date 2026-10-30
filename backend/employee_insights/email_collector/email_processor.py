import re
from email.utils import parsedate_to_datetime

from backend.employee_insights.email_collector.gmail_collector import GmailCollector
from backend.employee_insights.analysis.feedback_extractor import FeedbackExtractor
from backend.employee_insights.preprocessing.employee_identifier import EmployeeIdentifier
from backend.employee_insights.database.db_manager import DatabaseManager


class EmailProcessor:

    AUTOMATED_SUBJECTS = [
        r"^upcoming meeting",
        r"^meeting invitation",
        r"^automation agent\s*-\s*gmail test"
    ]

    def __init__(self):

        self.collector = GmailCollector()
        self.extractor = FeedbackExtractor()
        self.employee_identifier = EmployeeIdentifier()
        self.database = DatabaseManager()

    def normalize_date(self, date_string):

        if not date_string:
            return None

        try:
            return parsedate_to_datetime(date_string).isoformat()

        except (TypeError, ValueError):
            return None

    def is_automated_email(self, subject, body):

        subject = subject.strip().lower()

        for pattern in self.AUTOMATED_SUBJECTS:

            if re.search(pattern, subject, re.IGNORECASE):
                return True

        if "please view this email in an html-compatible email client" in body.lower():
            return True

        return False

    def process_emails(
        self,
        query="in:anywhere -in:spam -in:trash",
        max_results=100
    ):

        emails = self.collector.collect_emails(
            query=query,
            max_results=max_results
        )

        total_feedback = 0
        saved_feedback = 0
        matched_emails = 0
        skipped_emails = 0

        print(f"\nCollected {len(emails)} emails.")

        for email in emails:

            subject = email.get("subject", "")
            body = email.get("body", "")
            recipients = email.get("recipients", "")

            if self.is_automated_email(subject, body):
                skipped_emails += 1
                continue

            email_text = f"{subject}\n{body}".strip()

            if not email_text:
                continue

            target_employees = (
                self.employee_identifier.identify_employees(
                    recipients
                )
            )

            feedback_records = self.extractor.extract_feedback(
                email_text,
                target_employees=target_employees
            )

            if not feedback_records:
                continue

            matched_emails += 1
            total_feedback += len(feedback_records)

            email_date = self.normalize_date(
                email.get("date", "")
            )

            for record in feedback_records:

                record["email_id"] = email["email_id"]
                record["email_date"] = email_date

            saved_feedback += self.database.save_feedback(
                feedback_records
            )

        print("\nEMAIL PROCESSING SUMMARY")
        print("=" * 50)
        print(f"Emails collected: {len(emails)}")
        print(f"Automated emails skipped: {skipped_emails}")
        print(f"Emails containing feedback: {matched_emails}")
        print(f"Feedback records extracted: {total_feedback}")
        print(f"New records saved: {saved_feedback}")
        print(f"Duplicate records skipped: {total_feedback - saved_feedback}")

        return {
            "emails_collected": len(emails),
            "automated_emails_skipped": skipped_emails,
            "matched_emails": matched_emails,
            "feedback_extracted": total_feedback,
            "feedback_saved": saved_feedback
        }


if __name__ == "__main__":

    processor = EmailProcessor()

    processor.process_emails(
        query="in:anywhere -in:spam -in:trash",
        max_results=100
    )