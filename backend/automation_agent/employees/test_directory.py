from backend.automation_agent.employees.employee_directory import EmployeeDirectory


directory = EmployeeDirectory()

print("\nALL EMPLOYEES")

for employee in directory.get_all_employees():
    print(employee)

print("\nSEARCH EMPLOYEE")

results = directory.search_employees("Navneet")

for employee in results:
    print(employee)

print("\nAVAILABLE ROLES")
print(directory.get_roles())

print("\nAVAILABLE DEPARTMENTS")
print(directory.get_departments())

print("\nSELECTED PARTICIPANTS")

selected = directory.get_selected_employees(
    ["EMP001", "EMP002", "EMP004"]
)

for employee in selected:
    print(employee["name"], employee["email"])