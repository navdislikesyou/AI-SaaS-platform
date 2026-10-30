import sys
from pathlib import Path

import streamlit as st

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from backend.automation_agent.employees.employee_directory import EmployeeDirectory


st.set_page_config(
    page_title="Employee Directory",
    page_icon="",
    layout="wide"
)


@st.cache_resource
def get_directory():
    return EmployeeDirectory()


directory = get_directory()

employees = directory.get_all_employees()

st.title("Employee Directory")
st.write("Manage employees and select participants for meetings.")

st.divider()

st.subheader("Employee Overview")

col1, col2, col3 = st.columns(3)

col1.metric("Total Employees", len(employees))

col2.metric(
    "Departments",
    len({
        employee["department"]
        for employee in employees
        if employee["department"] != "Unassigned"
    })
)

col3.metric(
    "Roles",
    len({
        employee["role"]
        for employee in employees
        if employee["role"] != "Unassigned"
    })
)

st.divider()

st.subheader("Select Participants")

search_col, department_col, role_col = st.columns(3)

with search_col:
    search_query = st.text_input(
        "Search employees",
        placeholder="Name, email or employee ID"
    )

with department_col:
    departments = sorted({
        employee["department"]
        for employee in employees
    })

    selected_department = st.selectbox(
        "Department",
        ["All Departments"] + departments
    )

with role_col:
    roles = sorted({
        employee["role"]
        for employee in employees
    })

    selected_role = st.selectbox(
        "Role",
        ["All Roles"] + roles
    )

filtered_employees = employees

if search_query:
    query = search_query.lower().strip()

    filtered_employees = [
        employee
        for employee in filtered_employees
        if query in employee["name"].lower()
        or query in employee["email"].lower()
        or query in employee["employee_id"].lower()
    ]

if selected_department != "All Departments":
    filtered_employees = [
        employee
        for employee in filtered_employees
        if employee["department"] == selected_department
    ]

if selected_role != "All Roles":
    filtered_employees = [
        employee
        for employee in filtered_employees
        if employee["role"] == selected_role
    ]

st.caption(
    f"Showing {len(filtered_employees)} of {len(employees)} employees"
)

if "selected_employees" not in st.session_state:
    st.session_state.selected_employees = set()

button_col1, button_col2, button_col3 = st.columns([1, 1, 4])

with button_col1:
    if st.button("Select All Visible", use_container_width=True):
        for employee in filtered_employees:
            st.session_state.selected_employees.add(
                employee["employee_id"]
            )
        st.rerun()

with button_col2:
    if st.button("Clear Selection", use_container_width=True):
        st.session_state.selected_employees.clear()
        st.rerun()

st.write("")

if not filtered_employees:
    st.info("No employees found.")

for employee in filtered_employees:

    employee_id = employee["employee_id"]

    col1, col2 = st.columns([3, 5])

    with col1:
        selected = st.checkbox(
            employee["name"],
            value=employee_id in st.session_state.selected_employees,
            key=f"employee_{employee_id}"
        )

        if selected:
            st.session_state.selected_employees.add(employee_id)
        else:
            st.session_state.selected_employees.discard(employee_id)

    with col2:
        st.write(
            f"**{employee['role']}** · {employee['department']}"
        )
        st.caption(employee["email"])

st.divider()

selected_ids = list(st.session_state.selected_employees)

selected_participants = directory.get_selected_employees(
    selected_ids
)

st.subheader("Selected Participants")

st.metric(
    "Selected Employees",
    len(selected_participants)
)

if selected_participants:

    for employee in selected_participants:
        st.write(
            f"**{employee['name']}** — {employee['email']}"
        )

    participant_data = [
        {
            "employee_id": employee["employee_id"],
            "name": employee["name"],
            "email": employee["email"],
            "role": employee["role"],
            "department": employee["department"]
        }
        for employee in selected_participants
    ]

    st.download_button(
        "Download Participant List",
        data=__import__("json").dumps(
            participant_data,
            indent=4
        ),
        file_name="selected_participants.json",
        mime="application/json"
    )

    st.success("Participants selected successfully.")

else:
    st.info("Select employees to add them to the meeting.")

st.divider()

st.caption("Temporary Employee Directory · Automation Agent")