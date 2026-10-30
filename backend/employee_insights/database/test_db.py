from backend.employee_insights.database.db_manager import DatabaseManager
from backend.employee_insights.analysis.feedback_extractor import FeedbackExtractor


extractor = FeedbackExtractor()
database = DatabaseManager()

email_text = """
Navneet Verma completed the project successfully.
His presentation was excellent.

Omkar Shenwai missed the submission deadline.
He needs to improve his time management.

Pulkita Verma did an outstanding job coordinating the team.
"""

results = extractor.extract_feedback(email_text)

for record in results:
    record["email_id"] = "TEST_EMAIL_001"
    record["email_date"] = "2026-10-30T10:00:00"

saved = database.save_feedback(results)

print("\nDATABASE TEST")
print("=" * 60)

print(f"New records saved: {saved}")

print("\nALL FEEDBACK")

for record in database.get_all_feedback():

    print(f"\nEmployee: {record['employee_name']}")
    print(f"Feedback: {record['feedback']}")
    print(f"Sentiment: {record['sentiment']}")

print("\nEMPLOYEE SUMMARY")

for employee_id in ["EMP001", "EMP002", "EMP003", "EMP004"]:

    summary = database.get_employee_summary(employee_id)

    print(f"\n{employee_id}: {summary}")

print("\nDatabase test completed.")