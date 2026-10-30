from collections import defaultdict

from backend.employee_insights.database.db_manager import DatabaseManager
from backend.employee_insights.preprocessing.employee_identifier import EmployeeIdentifier


class FrequencyAnalyzer:

    def __init__(self):
        self.database = DatabaseManager()
        self.employee_identifier = EmployeeIdentifier()

    def analyze(self):

        records = self.database.get_all_feedback()

        employees = {
            employee["employee_id"]: {
                "employee_id": employee["employee_id"],
                "employee_name": employee["name"],
                "total_feedback": 0,
                "positive": 0,
                "negative": 0,
                "neutral": 0
            }
            for employee in self.employee_identifier.employees
        }

        for record in records:

            employee_id = record["employee_id"]

            if employee_id not in employees:
                continue

            employee = employees[employee_id]

            employee["total_feedback"] += 1

            sentiment = record["sentiment"].lower()

            if sentiment in ("positive", "negative", "neutral"):
                employee[sentiment] += 1

        results = []

        for employee in employees.values():

            classified_feedback = (
                employee["positive"] + employee["negative"]
            )

            if classified_feedback:
                positive_percentage = round(
                    employee["positive"] / classified_feedback * 100, 2
                )
            else:
                positive_percentage = 0

            results.append({
                **employee,
                "positive_percentage": positive_percentage
            })

        return results

    def monthly_analysis(self):

        records = self.database.get_all_feedback()

        monthly_data = defaultdict(
            lambda: {
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "total": 0
            }
        )

        for record in records:

            email_date = record.get("email_date")

            if not email_date:
                continue

            month = email_date[:7]
            sentiment = record["sentiment"].lower()

            if sentiment not in ("positive", "negative", "neutral"):
                continue

            monthly_data[month][sentiment] += 1
            monthly_data[month]["total"] += 1

        return dict(sorted(monthly_data.items()))