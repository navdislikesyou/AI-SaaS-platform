"""Test the full API scenario with and without directory_id."""

from app.services.employee_directory import EmployeeDirectoryService, EmployeeDirectoryManifest, build_row, DirectoryStatus
from app.core.config import get_settings
import uuid
import json
import os

# Set up the manifest and service
from tests.fakes import FakePrincipal
from app.main import create_app
from app.api.deps import (
    get_current_user_from_token_optional_principal,
    get_employee_directory_manifest,
    get_employee_directory_service,
    get_settings_dep,
    get_orchestrator,
    get_registry,
)
from app.agents.registry import AgentRegistry
from app.agents.adapters.automation import AutomationAgentAdapter
from httpx import ASGITransport, AsyncClient

# Write a directory
settings = get_settings()
upload_dir = settings.resolved_automation_upload_dir
manifest_path = settings.resolved_automation_upload_manifest_path

upload_dir.mkdir(parents=True, exist_ok=True)

# Create a test directory with "omkar"
records = [{"name": "Omkar", "email": "omkar@example.com"}]
directory_id = uuid.uuid4().hex
stored_name = f"{directory_id}_roster.json"

# Write to upload dir
(upload_dir / stored_name).write_text(json.dumps(records), encoding="utf-8")

# Record in manifest
from app.services.employee_directory import record_directory, get_manifest
manifest = get_manifest()
row = build_row(
    directory_id=directory_id,
    display_filename="roster.json",
    stored_name=stored_name,
    extension=".json",
    size_bytes=len(json.dumps(records)),
    status=DirectoryStatus.READY,
    employee_count=len(records),
    organization_id="test-org-1",
    owner_id="test-user-1",
)
manifest.append(row)

print(f"Directory ID: {directory_id}")
print(f"Records: {records}")

# Now test the API flow
from app.core.exceptions import DirectoryNotFoundError

async def test():
    from starlette.testclient import TestClient
    
    app = create_app(settings)
    
    # Override dependencies
    from app.api.deps import reset_state
    reset_state()
    
    registry = AgentRegistry()
    
    # Create adapter with recording service
    from tests.fakes import RecordingService
    recording = RecordingService()
    adapter = AutomationAgentAdapter(
        service=recording,
        directory_service=EmployeeDirectoryService(upload_dir=upload_dir),
    )
    registry.register(adapter)
    
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_orchestrator] = lambda: type('O', (), {'registry': registry})()
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: FakePrincipal(
        user_id="test-user-1", 
        organization_id="test-org-1", 
        role="manager"
    )
    app.dependency_overrides[get_employee_directory_manifest] = lambda: manifest
    app.dependency_overrides[get_employee_directory_service] = lambda: EmployeeDirectoryService(upload_dir=upload_dir)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Test 1: WITH directory_id
        print("\n--- Test 1: With directory_id ---")
        response = await client.post(
            "/api/v1/agents/execute",
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {
                    "instruction": "write a mail to omkar and invite him for tomorrow's diwali celebration",
                    "directory_id": directory_id,
                },
            },
        )
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Directory: {data['data'].get('directory', {})}")
        print(f"Recipients: {data['data'].get('recipients', [])}")
        print(f"Employee count: {data['data'].get('employee_count', 'N/A')}")
        
        # Test 2: WITHOUT directory_id
        print("\n--- Test 2: Without directory_id ---")
        response2 = await client.post(
            "/api/v1/agents/execute",
            json={
                "agent": "automation",
                "operation": "draft_action",
                "payload": {
                    "instruction": "write a mail to omkar and invite him for tomorrow's diwali celebration",
                },
            },
        )
        print(f"Status: {response2.status_code}")
        data2 = response2.json()
        print(f"Directory: {data2['data'].get('directory', {})}")
        print(f"Recipients: {data2['data'].get('recipients', [])}")
        print(f"Employee count: {data2['data'].get('employee_count', 'N/A')}")

import asyncio
asyncio.run(test())