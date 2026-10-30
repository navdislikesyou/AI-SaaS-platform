import json
import re
from pathlib import Path


class EmployeeIdentifier:

    def __init__(self):

        self.directory_path = (
            Path(__file__).resolve().parents[2]
            / "automation_agent"
            / "employees"
            / "employees.json"
        )

        self.employees = self._load_employees()

    def _load_employees(self):

        with open(self.directory_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            data = data.get("employees", [])

        return [
            employee for employee in data
            if employee.get("active", True)
        ]

    def _get_aliases(self, employee):

        name = employee.get("name", "").strip()
        email = employee.get("email", "").strip()
        employee_id = employee.get("employee_id", "")

        aliases = {
            name,
            email,
            employee_id
        }

        name_parts = name.split()

        # Include individual name parts.
        aliases.update(name_parts)

        # Include email username.
        if email:
            aliases.add(email.split("@")[0].replace(".", " "))

        return {
            alias.lower().strip()
            for alias in aliases
            if alias and len(alias.strip()) > 1
        }

    def identify_employees(self, text):

        normalized_text = re.sub(r"\s+", " ", text.lower()).strip()

        matches = []

        for employee in self.employees:

            aliases = self._get_aliases(employee)

            for alias in aliases:

                pattern = (
                    r"(?<![\w@.+-])"
                    + re.escape(alias)
                    + r"(?![\w@.+-])"
                )

                if re.search(pattern, normalized_text):

                    matches.append({
                        "employee_id": employee["employee_id"],
                        "name": employee["name"],
                        "email": employee["email"],
                        "matched_by": alias
                    })

                    break

        return matches

    def split_sentences(self, text):

        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text)
            if sentence.strip()
        ]

    def extract_employee_sentences(self, text):

        results = []

        for sentence in self.split_sentences(text):

            employees = self.identify_employees(sentence)

            for employee in employees:

                results.append({
                    "employee_id": employee["employee_id"],
                    "employee_name": employee["name"],
                    "employee_email": employee["email"],
                    "sentence": sentence
                })

        return results