import asyncio, pathlib
from httpx import ASGITransport, AsyncClient
from app.core.config import Settings
from app.main import create_app
from app.api import deps
from app.api.deps import (get_current_user_from_token_optional_principal, get_job_manager,
                          get_settings_dep, get_registry, get_orchestrator)
from app.agents.registry import AgentRegistry
from app.services.job_manager import JobManager
from app.services.orchestrator import Orchestrator

class Org:
    def __init__(self, org): self.id="u1"; self.organization_id=org; self.role="employee"; self.is_active=True

async def main():
    s = Settings(environment="test", debug=False, cors_origins=["http://testserver"], log_level="WARNING")
    registry = AgentRegistry(); manager = JobManager()
    deps.reset_state()
    app = create_app(s)
    app.dependency_overrides[get_settings_dep] = lambda: s
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_orchestrator] = lambda: Orchestrator(registry)
    app.dependency_overrides[get_job_manager] = lambda: manager
    app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: Org("org-A")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        created = await c.post("/api/v1/performance/jobs",
            json={"operation": "visualize", "file_path": "performance_agent/data/Financials_standardized.csv"})
        job_id = created.json()["data"]["job_id"]
        for _ in range(600):
            await asyncio.sleep(0.05)
            d = (await c.get(f"/api/v1/performance/jobs/{job_id}")).json()["data"]
            if d["status"] in ("completed","failed"): break
        print("JOB", d["status"], "generated=", d.get("result",{}).get("generated"))
        fn = d["result"]["visualizations"][0]["filename"]
        url = f"/api/v1/performance/jobs/{job_id}/artifacts/{fn}"

        # 1. WITH the bearer-equivalent principal (same org) -> what an authenticated fetch gets
        r = await c.get(url)
        print("AUTHENTICATED  ->", r.status_code, r.headers.get("content-type"), len(r.content), "bytes")

        # 2. WITHOUT any principal -> exactly what a browser <img> request does (no Authorization header)
        app.dependency_overrides[get_current_user_from_token_optional_principal] = lambda: None
        r2 = await c.get(url)
        print("ANONYMOUS <img> ->", r2.status_code, r2.headers.get("content-type"), r2.text[:160])

        # 3. The PNG on disk
        from performance_agent.reporting import resolve_results_dir
        p = resolve_results_dir("results/visualizations")/"jobs"/job_id/"visualizations"/fn
        print("ON DISK        ->", p.is_file(), p.stat().st_size if p.is_file() else None, "bytes")

asyncio.run(main())
