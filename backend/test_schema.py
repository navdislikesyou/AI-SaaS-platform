from app.main import app
schema = app.openapi()
import json
print(json.dumps(schema['components']['securitySchemes'], indent=2))