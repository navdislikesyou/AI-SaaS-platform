import requests
import json

# Test with a name that might be in the database or demo employees
# Let's also test what the backend sees

# Test 1: Simple text without a specific employee name
r1 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': 'Great project completion by the team'}
    }
)
d1 = r1.json()
print("Test 1 - 'Great project completion by the team':")
print(f"  Records: {d1['data']['data']['records']}")
print(f"  Count: {d1['data']['data']['count']}")
print()

# Test 2: Check if there are any employees in the database
# Let's test the employee_summary operation instead
r2 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'employee_summary',
        'payload': {'employee_id': 'all'}
    }
)
d2 = r2.json()
print("Test 2 - employee_summary (all):")
if d2.get('success'):
    data = d2.get('data', {})
    print(f"  Employees: {data.get('employees', [])}")
    print(f"  Organization: {data.get('organization_id', '')}")
else:
    print(f"  Error: {d2.get('error', 'unknown')}")
print()

# Test 3: Try with just "thanks" - very simple
r3 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': 'thanks'}
    }
)
d3 = r3.json()
print("Test 3 - 'thanks':")
print(f"  Records: {d3['data']['data']['records']}")
print(f"  Count: {d3['data']['data']['count']}")