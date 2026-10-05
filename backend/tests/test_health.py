"""Tests for health and readiness endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_reports_ok(client: AsyncClient) -> None:
    """The liveness endpoint returns an ok payload with app metadata."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0-test"
    assert body["environment"] == "test"
    assert "timestamp" in body


async def test_health_requires_no_authentication(client: AsyncClient) -> None:
    """Liveness stays reachable because authentication is not implemented."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 200


async def test_health_sets_request_id_header(client: AsyncClient) -> None:
    """Every response carries a correlation id header."""
    response = await client.get("/api/v1/health")

    assert response.headers.get("X-Request-ID")


async def test_health_reuses_inbound_request_id(client: AsyncClient) -> None:
    """A client-supplied request id is echoed back for end-to-end tracing."""
    inbound = "trace-abc-123"

    response = await client.get("/api/v1/health", headers={"X-Request-ID": inbound})

    assert response.headers["X-Request-ID"] == inbound


async def test_ready_reports_registry_initialized(client: AsyncClient) -> None:
    """Readiness returns 200 and confirms the registry is populated."""
    response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    checks = {check["name"]: check for check in body["checks"]}
    assert checks["registry"]["ready"] is True
    assert checks["agents"]["ready"] is True


async def test_ready_lists_unconnected_agents_as_ready(
    client: AsyncClient,
) -> None:
    """Unconnected agents must not fail readiness.

    The backend itself is healthy even though no agent implementation exists,
    so the container must not be restarted for that reason.
    """
    response = await client.get("/api/v1/ready")

    body = response.json()
    agents_check = next(check for check in body["checks"] if check["name"] == "agents")
    assert agents_check["ready"] is True
    assert "agents connected" in agents_check["detail"]


async def test_root_points_to_docs(client: AsyncClient) -> None:
    """The root path advertises the docs and health locations."""
    response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health"
