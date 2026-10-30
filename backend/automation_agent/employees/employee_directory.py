import json
from pathlib import Path


class EmployeeDirectory:

    def __init__(self):
        self.file_path = Path(__file__).parent / "employees.json"
        self.employees = []
        self.load_employees()

    def load_employees(self):
        if not self.file_path.exists():
            self.employees = []
            return

        with open(self.file_path, "r", encoding="utf-8") as file:
            self.employees = json.load(file)

    def save_employees(self):
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(self.employees, file, indent=4)

    def get_all_employees(self):
        return [
            employee for employee in self.employees
            if employee.get("active", True)
        ]

    def get_by_id(self, employee_id):
        for employee in self.get_all_employees():
            if employee["employee_id"] == employee_id:
                return employee
        return None

    def search_employees(self, query):
        query = query.strip().lower()

        if not query:
            return self.get_all_employees()

        return [
            employee for employee in self.get_all_employees()
            if query in employee["name"].lower()
            or query in employee["email"].lower()
            or query in employee["employee_id"].lower()
        ]

    def get_by_role(self, role):
        return [
            employee for employee in self.get_all_employees()
            if employee["role"].lower() == role.strip().lower()
        ]

    def get_by_department(self, department):
        return [
            employee for employee in self.get_all_employees()
            if employee["department"].lower() == department.strip().lower()
        ]

    def get_selected_employees(self, employee_ids):
        selected = []
        missing = []

        for employee_id in employee_ids:
            employee = self.get_by_id(employee_id)

            if employee:
                selected.append(employee)
            else:
                missing.append(employee_id)

        if missing:
            raise ValueError(
                f"Invalid or inactive employee IDs: {', '.join(missing)}"
            )

        return selected

    def get_roles(self):
        return sorted({
            employee["role"]
            for employee in self.get_all_employees()
            if employee["role"] != "Unassigned"
        })

    def get_departments(self):
        return sorted({
            employee["department"]
            for employee in self.get_all_employees()
            if employee["department"] != "Unassigned"
        })

    def add_employee(self, employee_id, name, email, role, department):
        if any(
            employee["employee_id"] == employee_id
            for employee in self.employees
        ):
            raise ValueError("Employee ID already exists.")

        if any(
            employee["email"].lower() == email.lower()
            for employee in self.employees
        ):
            raise ValueError("Email address already exists.")

        employee = {
            "employee_id": employee_id,
            "name": name.strip(),
            "email": email.strip(),
            "role": role.strip(),
            "department": department.strip(),
            "active": True
        }

        self.employees.append(employee)
        self.save_employees()

        return employee

    def update_employee(self, employee_id, **updates):
        allowed_fields = {
            "name",
            "email",
            "role",
            "department",
            "active"
        }

        employee = next(
            (
                item for item in self.employees
                if item["employee_id"] == employee_id
            ),
            None
        )

        if not employee:
            raise ValueError("Employee not found.")

        for field, value in updates.items():
            if field not in allowed_fields:
                raise ValueError(f"Invalid field: {field}")

            if field == "email":
                duplicate = any(
                    item["email"].lower() == value.lower()
                    and item["employee_id"] != employee_id
                    for item in self.employees
                )

                if duplicate:
                    raise ValueError("Email address already exists.")

            employee[field] = value.strip() if isinstance(value, str) else value

        self.save_employees()

        return employee

    def deactivate_employee(self, employee_id):
        return self.update_employee(employee_id, active=False)

    def activate_employee(self, employee_id):
        return self.update_employee(employee_id, active=True)

    def get_all_roles(self):
        return self.get_roles()

    def get_all_departments(self):
        return self.get_departments()