from backend.employee_insights.database.db_manager import DatabaseManager


database = DatabaseManager()

confirmation = input(
    "This will delete ALL stored employee feedback. Type CLEAR to continue: "
)

if confirmation == "CLEAR":

    with database.get_connection() as connection:

        connection.execute("DELETE FROM feedback_records")

        connection.execute("""
            DELETE FROM sqlite_sequence
            WHERE name = 'feedback_records'
        """)

    print("\nDatabase cleared successfully.")
    print("All employee feedback counts are now zero.")

else:
    print("\nDatabase clearing cancelled.")