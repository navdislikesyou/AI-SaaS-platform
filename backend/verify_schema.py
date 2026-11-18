from app.main import app
schema = app.openapi()
schemes = schema['components']['securitySchemes']
import json
print(json.dumps(schemes, indent=2))