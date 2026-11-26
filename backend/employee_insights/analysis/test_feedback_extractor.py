import re

from backend.employee_insights.preprocessing.employee_identifier import EmployeeIdentifier
from backend.employee_insights.analysis.sentiment_analyzer import SentimentAnalyzer


class FeedbackExtractor:

    PRONOUNS = {
        "he", "she", "his", "her", "they", "their",
        "him", "them", "himself", "herself", "themselves"
    }

    def __init__(self):
        self.employee_identifier = EmployeeIdentifier()
        self.sentiment_analyzer = SentimentAnalyzer()

    def split_sentences(self, text):

        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text)
            if sentence.strip()
        ]

    def has_employee_reference(self, sentence):

        words = set(re.findall(r"\b\w+\b", sentence.lower()))

        return bool(words.intersection(self.PRONOUNS))

    def extract_feedback(self, email_text, target_employees=None):

        sentences = self.split_sentences(email_text)

        extracted_feedback = []
        previous_employees = []

        target_employees = target_employees or []

        for sentence in sentences:

            employees = self.employee_identifier.identify_employees(
                sentence
            )

            if employees:

                previous_employees = employees

            elif (
                previous_employees
                and self.has_employee_reference(sentence)
            ):

                employees = previous_employees

            elif len(target_employees) == 1:

                employees = target_employees

            else:
                continue

            for employee in employees:

                extracted_feedback.append({
                    "employee_id": employee["employee_id"],
                    "employee_name": employee["name"],
                    "employee_email": employee["email"],
                    "feedback": sentence
                })

        if not extracted_feedback:
            return []

        sentiments = self.sentiment_analyzer.analyze_batch([
            item["feedback"]
            for item in extracted_feedback
        ])

        results = []

        for item, sentiment in zip(extracted_feedback, sentiments):

            results.append({
                **item,
                "sentiment": sentiment["sentiment"],
                "confidence": sentiment["confidence"],
                "feedback_type": (
                    "performance_feedback"
                    if sentiment["sentiment"] in ("POSITIVE", "NEGATIVE")
                    else "neutral_mention"
                )
            })

        return results