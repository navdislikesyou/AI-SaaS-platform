from backend.employee_insights.preprocessing.employee_identifier import EmployeeIdentifier


identifier = EmployeeIdentifier()

email_text = """
Navneet Verma completed the project successfully.
Omkar Shenwai missed the submission deadline.
Pulkita Verma did an excellent job coordinating the team.
The quarterly meeting is scheduled for Monday.
"""

print("\nEMPLOYEE IDENTIFICATION")
print("=" * 60)

matches = identifier.identify_employees(email_text)

for employee in matches:
    print(employee["name"], "-", employee["email"])


print("\nEMPLOYEE-SPECIFIC SENTENCES")
print("=" * 60)

results = identifier.extract_employee_sentences(email_text)

for result in results:
    print(f"\nEmployee: {result['employee_name']}")
    print(f"Feedback: {result['sentence']}")