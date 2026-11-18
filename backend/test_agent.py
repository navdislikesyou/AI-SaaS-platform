import requests
import json

r = requests.post(
    'http://localhost:8000/api/v1/agents/execute',
    json={
        'agent': 'employee_insights',
        'operation': 'extract_feedback',
        'payload': {'email_text': 'Navneet did an excellent job'}
    }
)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2)}")