from backend.employee_insights.analysis.frequency_analyzer import FrequencyAnalyzer


analyzer = FrequencyAnalyzer()

results = analyzer.analyze()

print("\nEMPLOYEE FEEDBACK FREQUENCY")
print("=" * 85)

for employee in results:

    print(f"\nEmployee: {employee['employee_name']}")
    print(f"Employee ID: {employee['employee_id']}")
    print(f"Total Feedback: {employee['total_feedback']}")
    print(f"Positive: {employee['positive']}")
    print(f"Negative: {employee['negative']}")
    print(f"Neutral: {employee['neutral']}")
    print(f"Positive Percentage: {employee['positive_percentage']}%")

    print("-" * 85)


print("\nMONTHLY FEEDBACK ANALYSIS")
print("=" * 85)

monthly_results = analyzer.monthly_analysis()

for month, data in monthly_results.items():

    print(f"\nMonth: {month}")
    print(f"Total: {data['total']}")
    print(f"Positive: {data['positive']}")
    print(f"Negative: {data['negative']}")
    print(f"Neutral: {data['neutral']}")