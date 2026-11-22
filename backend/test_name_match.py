"""Test name matching logic for automation agent."""

from automation_agent.automation_agent import AutomationAgent


class StubLLM:
    def generate(self, prompt):
        return 'Dear Team,\n\nDraft body.'


agent = AutomationAgent(llm=StubLLM())

# Test 1: roster with just 'Omkar' as name
roster1 = [{'name': 'Omkar', 'email': 'omkar@example.com'}]
meeting1 = agent.parse_instruction(
    'write a mail to omkar and invite him for tomorrow diwali celebration',
    roster1
)
print(f'Case 1 - roster with name=Omkar:')
print(f'  attendees: {meeting1["attendees"]}')

# Test 2: roster with 'Omkar Shenwai' as name
roster2 = [{'name': 'Omkar Shenwai', 'email': 'omkar.shenwai@example.com'}]
meeting2 = agent.parse_instruction(
    'write a mail to omkar and invite him for tomorrow diwali celebration',
    roster2
)
print(f'\nCase 2 - roster with name=Omkar Shenwai:')
print(f'  attendees: {meeting2["attendees"]}')

# Test 3: find_emails with just 'Omkar'
recipients1 = agent.find_emails(meeting1['attendees'], roster1)
print(f'\nCase 3 - find_emails with name=Omkar:')
print(f'  recipients: {recipients1}')

# Test 4: find_emails with 'Omkar Shenwai'
recipients2 = agent.find_emails(meeting2['attendees'], roster2)
print(f'\nCase 4 - find_emails with name=Omkar Shenwai:')
print(f'  recipients: {recipients2}')

# Test 5: The full execute flow with just 'Omkar'
result1 = agent.execute(
    'write a mail to omkar and invite him for tomorrow diwali celebration',
    roster1
)
print(f'\nCase 5 - execute with name=Omkar:')
print(f'  meeting: {result1[0]}')
print(f'  recipients: {result1[1]}')
print(f'  email: {result1[2]}')
print(f'  employee_count: {result1[3] if len(result1) > 3 else "N/A"}')

# Test 6: The full execute flow with 'Omkar Shenwai'
result2 = agent.execute(
    'write a mail to omkar and invite him for tomorrow diwali celebration',
    roster2
)
print(f'\nCase 6 - execute with name=Omkar Shenwai:')
print(f'  meeting: {result2[0]}')
print(f'  recipients: {result2[1]}')
print(f'  email: {result2[2]}')
print(f'  employee_count: {result2[3] if len(result2) > 3 else "N/A"}')