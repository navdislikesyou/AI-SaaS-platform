from datetime import datetime

from backend.automation_agent.employees.employee_directory import (
    EmployeeDirectory
)


class MeetingSetup:

    def __init__(self):
        self.directory = EmployeeDirectory()

    def select_participants(self):

        employees = self.directory.get_all_employees()

        if not employees:
            raise ValueError("No active employees available.")

        print("\nAVAILABLE EMPLOYEES")
        print("=" * 50)

        for index, employee in enumerate(employees, 1):
            print(f"\n[{index}] {employee['name']}")
            print(f"    {employee['email']}")
            print(f"    {employee['role']} | {employee['department']}")

        while True:
            choice = input(
                "\nSelect employees (e.g. 1,2,4): "
            ).strip()

            try:
                indices = [
                    int(value.strip())
                    for value in choice.split(",")
                ]

                if not indices:
                    raise ValueError

                if len(indices) != len(set(indices)):
                    print("Duplicate selections are not allowed.")
                    continue

                if any(index < 1 or index > len(employees)
                       for index in indices):
                    print("Invalid employee selection.")
                    continue

                selected = [
                    employees[index - 1]
                    for index in indices
                ]

                return selected

            except ValueError:
                print("Enter valid employee numbers separated by commas.")

    def get_meeting_details(self):

        print("\nMEETING DETAILS")
        print("=" * 50)

        title = input("Meeting Title: ").strip()
        reason = input("Reason: ").strip()
        venue = input("Venue: ").strip()

        while True:
            date_input = input(
                "Date (YYYY-MM-DD): "
            ).strip()

            try:
                meeting_date = datetime.strptime(
                    date_input,
                    "%Y-%m-%d"
                ).date()

                break

            except ValueError:
                print("Invalid date. Use YYYY-MM-DD.")

        while True:
            time_input = input(
                "Time (HH:MM, 24-hour): "
            ).strip()

            try:
                meeting_time = datetime.strptime(
                    time_input,
                    "%H:%M"
                ).time()

                meeting_datetime = datetime.combine(
                    meeting_date,
                    meeting_time
                )

                if meeting_datetime <= datetime.now():
                    print("Meeting must be scheduled in the future.")
                    continue

                break

            except ValueError:
                print("Invalid time. Use HH:MM.")

        if not title or not reason or not venue:
            raise ValueError("All meeting details are required.")

        return {
            "title": title,
            "reason": reason,
            "date": meeting_date.isoformat(),
            "time": meeting_time.strftime("%H:%M"),
            "venue": venue,
            "datetime": meeting_datetime.isoformat()
        }

    def display_summary(self, meeting, participants):

        meeting_date = datetime.strptime(
            meeting["date"],
            "%Y-%m-%d"
        )

        meeting_time = datetime.strptime(
            meeting["time"],
            "%H:%M"
        )

        print("\n" + "=" * 50)
        print("MEETING SUMMARY")
        print("=" * 50)

        print(f"Title: {meeting['title']}")
        print(f"Reason: {meeting['reason']}")
        print(f"Date: {meeting_date.strftime('%d %B %Y')}")
        print(f"Time: {meeting_time.strftime('%I:%M %p')}")
        print(f"Venue: {meeting['venue']}")

        print("\nParticipants:")

        for employee in participants:
            print(f"- {employee['name']} ({employee['email']})")

        print("\n" + "=" * 50)

    def run(self):

        print("\n" + "=" * 50)
        print("MEETING SCHEDULER")
        print("=" * 50)

        participants = self.select_participants()

        meeting = self.get_meeting_details()

        self.display_summary(
            meeting,
            participants
        )

        while True:

            print("\n[1] Confirm")
            print("[2] Cancel")

            choice = input("\nChoice: ").strip()

            if choice == "1":

                meeting_data = {
                    **meeting,
                    "participants": [
                        {
                            "employee_id": employee["employee_id"],
                            "name": employee["name"],
                            "email": employee["email"]
                        }
                        for employee in participants
                    ],
                    "notifications": {
                        "invitation": True,
                        "reminder_24h": True,
                        "reminder_30m": True
                    }
                }

                print("\nMeeting setup completed successfully.")

                return meeting_data

            elif choice == "2":

                print("\nMeeting setup cancelled.")
                return None

            else:
                print("Invalid choice.")


def main():

    setup = MeetingSetup()

    try:
        meeting = setup.run()

        if meeting:
            print("\nMEETING DATA")
            print("=" * 50)
            print(meeting)

    except (ValueError, OSError) as error:
        print(f"\nError: {error}")


if __name__ == "__main__":
    main()