"""Test the actual flow with and without directory_id."""

from automation_agent.service import AutomationService


class StubLLM:
    def generate(self, prompt):
        return "Dear Team,\n\nDraft body."


def test_with_uploaded_employees():
    """Test with explicitly passed employees (simulates uploaded directory)."""
    print("=" * 60)
    print("TEST 1: With uploaded employees (directory_id provided)")
    print("=" * 60)
    
    service = AutomationService(settings=None)
    
    # Simulate uploaded directory records
    uploaded_employees = [
        {"name": "Omkar", "email": "omkar@example.com"},
        {"name": "Navneet", "email": "navneet@example.com"},
    ]
    
    # Simulate user context with organization_id
    user_context = {"organization_id": "test-org-1", "user_id": "test-user-1", "role": "manager"}
    
    # Simulate session (None for now)
    session = None
    
    # Step 1: _resolve_roster with uploaded employees
    roster = service._resolve_roster(uploaded_employees, user_context, session)
    print(f"_resolve_roster with uploaded employees: {len(roster)} employees")
    print(f"  Roster: {roster}")
    
    # Step 2: execute with the roster
    result = service.execute(
        "write a mail to omkar and invite him for tomorrow's diwali celebration",
        uploaded_employees,
        user_context=user_context,
        session=session,
    )
    print(f"\nExecute result:")
    print(f"  meeting: {result['meeting']}")
    print(f"  recipients: {result['recipients']}")
    print(f"  employee_count: {result['employee_count']}")
    
    # Step 3: Also test with the agent directly
    from automation_agent.automation_agent import AutomationAgent
    agent = AutomationAgent(llm=StubLLM())
    
    # Test parse_instruction
    meeting = agent.parse_instruction(
        "write a mail to omkar and invite him for tomorrow's diwali celebration",
        uploaded_employees,
    )
    print(f"\nParse instruction attendees: {meeting['attendees']}")
    
    # Test find_emails
    recipients = agent.find_emails(meeting['attendees'], uploaded_employees)
    print(f"Find emails recipients: {recipients}")


def test_without_employees():
    """Test with no employees passed (uses packaged directory)."""
    print("\n" + "=" * 60)
    print("TEST 2: Without employees (uses packaged directory)")
    print("=" * 60)
    
    service = AutomationService(settings=None)
    
    # No employees passed = uses packaged directory
    user_context = {"organization_id": "test-org-1", "user_id": "test-user-1", "role": "manager"}
    session = None
    
    # Step 1: _resolve_roster with NO employees
    roster = service._resolve_roster(None, user_context, session)
    print(f"_resolve_roster with NO employees: {len(roster)} employees")
    print(f"  Roster: {roster}")
    
    # Step 2: execute with no employees
    result = service.execute(
        "write a mail to omkar and invite him for tomorrow's diwali celebration",
        None,  # no employees = use packaged directory
        user_context=user_context,
        session=session,
    )
    print(f"\nExecute result (no employees):")
    print(f"  meeting: {result['meeting']}")
    print(f"  recipients: {result['recipients']}")
    print(f"  employee_count: {result['employee_count']}")


if __name__ == "__main__":
    test_with_uploaded_employees()
    test_without_employees()