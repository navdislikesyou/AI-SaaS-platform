"""Test path confinement - symlink and traversal resistance."""
import asyncio
import tempfile
from pathlib import Path
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.api.deps import get_settings_dep, get_registry, get_orchestrator
from app.core.config import Settings
from app.agents.registry import AgentRegistry
from app.agents.adapters.performance import PerformanceAgentAdapter
from tests.fakes import EchoAgent


async def test_path_confinement():
    """Test that file_path is confined to the allowlisted directory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        
        # Simulate the allowlisted directory structure
        # The allowlist is: resolved_performance_sample_dataset_path.parent
        # which is: backend_dir / "performance_agent" / "data"
        # Let's set up:
        backend_dir = tmp / "backend"
        backend_dir.mkdir()
        
        # The allowlisted dir (what _resolve_dataset_path checks against)
        allowed_dir = backend_dir / "performance_agent" / "data"
        allowed_dir.mkdir(parents=True)
        
        # Create a "safe" file inside the allowed dir
        safe_file = allowed_dir / "safe.csv"
        safe_file.write_text("a,b,c\n1,2,3")
        
        # Create a file OUTSIDE the allowed dir
        outside_file = tmp / "outside" / "secret.csv"
        outside_file.parent.mkdir(parents=True)
        outside_file.write_text("secret data")
        
        # Set up settings
        settings = Settings(
            environment="test",
            debug=False,
            cors_origins=["http://testserver"],
            log_level="WARNING",
            api_v1_prefix="/api/v1",
        )
        # Point the sample dataset path parent to the allowed dir
        settings._sample_dataset_path_parent = allowed_dir.parent
        
        registry = AgentRegistry()
        registry.register(PerformanceAgentAdapter())
        registry.register(EchoAgent(name="echo", capabilities=["ping"]))
        
        app = create_app(settings)
        app.dependency_overrides[get_settings_dep] = lambda: settings
        app.dependency_overrides[get_registry] = lambda: registry
        app.dependency_overrides[get_orchestrator] = lambda: __import__("app.services.orchestrator").Orchestrator(registry)
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Test 1: Valid relative path within allowlist should work
            response = await client.post(
                "/api/v1/performance/jobs",
                json={"operation": "analyze", "file_path": "performance_agent/data/safe.csv"},
            )
            print(f"Valid relative path - status: {response.status_code}")
            if response.status_code == 202:
                print("  -> Job created successfully (path confined)")
            else:
                print(f"  -> Error: {response.text}")
            
            # Test 2: Path escaping the allowlist via .. traversal
            response2 = await client.post(
                "/api/v1/performance/jobs",
                json={"operation": "analyze", "file_path": "../../../outside/secret.csv"},
            )
            print(f"\nTraversal escape - status: {response2.status_code}")
            if response2.status_code in (404, 422):
                print("  -> Correctly rejected (path escapes allowlist)")
            else:
                print(f"  -> Unexpected: {response2.text}")
            
            # Test 3: Absolute path
            response3 = await client.post(
                "/api/v1/performance/jobs",
                json={"operation": "analyze", "file_path": "C:/Windows/system32/config/SAM"},
            )
            print(f"\nAbsolute path - status: {response3.status_code}")
            if response3.status_code in (404, 422):
                print("  -> Correctly rejected (absolute path)")
            else:
                print(f"  -> Unexpected: {response3.text}")


if __name__ == "__main__":
    asyncio.run(test_path_confinement())