import sqlite3
from pathlib import Path
from datetime import datetime


class DatabaseManager:

    def __init__(self):
        self.database_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "employee_insights.db"
        )

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.initialize_database()

    def get_connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_database(self):

        with self.get_connection() as connection:

            connection.execute("""
                CREATE TABLE IF NOT EXISTS feedback_records (
                    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id TEXT NOT NULL,
                    employee_name TEXT NOT NULL,
                    employee_email TEXT,
                    feedback TEXT NOT NULL,
                    sentiment TEXT NOT NULL,
                    confidence REAL,
                    email_id TEXT NOT NULL,
                    email_date TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(email_id, employee_id, feedback)
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_id
                ON feedback_records(employee_id)
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_sentiment
                ON feedback_records(sentiment)
            """)

    def save_feedback(self, records):

        saved_count = 0

        with self.get_connection() as connection:

            for record in records:

                cursor = connection.execute("""
                    INSERT OR IGNORE INTO feedback_records (
                        employee_id,
                        employee_name,
                        employee_email,
                        feedback,
                        sentiment,
                        confidence,
                        email_id,
                        email_date,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record["employee_id"],
                    record["employee_name"],
                    record.get("employee_email"),
                    record["feedback"],
                    record["sentiment"],
                    record["confidence"],
                    record.get("email_id", ""),
                    record.get("email_date"),
                    datetime.now().isoformat()
                ))

                saved_count += cursor.rowcount

        return saved_count

    def get_employee_feedback(self, employee_id):

        with self.get_connection() as connection:

            cursor = connection.execute("""
                SELECT *
                FROM feedback_records
                WHERE employee_id = ?
                ORDER BY email_date DESC
            """, (employee_id,))

            return [dict(row) for row in cursor.fetchall()]

    def get_all_feedback(self):

        with self.get_connection() as connection:

            cursor = connection.execute("""
                SELECT *
                FROM feedback_records
                ORDER BY email_date DESC
            """)

            return [dict(row) for row in cursor.fetchall()]

    def get_employee_summary(self, employee_id):

        with self.get_connection() as connection:

            cursor = connection.execute("""
                SELECT
                    COUNT(*) AS total_feedback,
                    COALESCE(SUM(CASE WHEN sentiment = 'POSITIVE' THEN 1 ELSE 0 END), 0)
                        AS positive_count,
                    COALESCE(SUM(CASE WHEN sentiment = 'NEGATIVE' THEN 1 ELSE 0 END), 0)
                        AS negative_count,
                    COALESCE(SUM(CASE WHEN sentiment = 'NEUTRAL' THEN 1 ELSE 0 END), 0)
                        AS neutral_count
                FROM feedback_records
                WHERE employee_id = ?
            """, (employee_id,))

            return dict(cursor.fetchone())

    def close(self):
        pass