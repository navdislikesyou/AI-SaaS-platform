from backend.employee_insights.database.db_manager import DatabaseManager


database = DatabaseManager()

records = database.get_all_feedback()

print("\nSTORED EMPLOYEE FEEDBACK")
print("=" * 90)

if not records:
    print("No feedback records found.")

for record in records:

    print(f"\nEmployee: {record['employee_name']}")
    print(f"Employee ID: {record['employee_id']}")
    print(f"Sentiment: {record['sentiment']}")
    print(f"Confidence: {record['confidence']}")
    print(f"Feedback: {record['feedback']}")
    print(f"Email Date: {record['email_date']}")
    print("-" * 90)