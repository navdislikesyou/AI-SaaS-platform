import requests
import json

# Test 1: "Navneet did an excellent job"
r1 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': 'Navneet did an excellent job'}
    }
)
d1 = r1.json()
print("Test 1 - 'Navneet did an excellent job':")
print(f"  Status: {r1.status_code}")
print(f"  Records: {d1['data']['data']['records']}")
print(f"  Count: {d1['data']['data']['count']}")
print(f"  Source: {d1['data']['data']['source']}")
print()

# Test 2: "Olga showed great leadership during the crisis"
r2 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': 'Olga showed great leadership during the crisis'}
    }
)
d2 = r2.json()
print("Test 2 - 'Olga showed great leadership during the crisis':")
print(f"  Status: {r2.status_code}")
print(f"  Records: {d2['data']['data']['records']}")
print(f"  Count: {d2['data']['data']['count']}")
print(f"  Source: {d2['data']['data']['source']}")
print()

# Test 3: "Mark helped me a lot with the migration"
r3 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': 'Mark helped me a lot with the migration'}
    }
)
d3 = r3.json()
print("Test 3 - 'Mark helped me a lot with the migration':")
print(f"  Status: {r3.status_code}")
print(f"  Records: {d3['data']['data']['records']}")
print(f"  Count: {d3['data']['data']['count']}")
print(f"  Source: {d3['data']['data']['source']}")
print()

# Test 4: "Sarah's feedback about the new policy was insightful"
r4 = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': "Sarah's feedback about the new policy was insightful"}
    }
)
d4 = r4.json()
print("Test 4 - \"Sarah's feedback about the new policy was insightful\":")
print(f"  Status: {r4.status_code}")
print(f"  Records: {d4['data']['data']['records']}")
print(f"  Count: {d4['data']['data']['count']}")
print(f"  Source: {d4['data']['data']['source']}")