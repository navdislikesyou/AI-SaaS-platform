"""Tests for the agent catalog and execution endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_list_agents_returns_all_registered_agents(
    client: AsyncClient,
) -> None:
    """Every registered agent appears in the catalog."""
    response = await client.get("/api/v1/agents")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    names = [agent["name"] for agent in body["data"]["agents"]]
    assert names == ["automation", "knowledge", "performance"]
    assert body["data"]["total"] == 3


async def test_list_agents_reports_availability(client: AsyncClient) -> None:
    """Availability and status are reported per agent."""
    response = await client.get("/api/v1/agents")

    agents = {agent["name"]: agent for agent in response.json()["data"]["agents"]}
    assert agents["knowledge"]["available"] is True
    assert agents["knowledge"]["status"] == "ready"
    assert agents["automation"]["available"] is False
    assert agents["automation"]["status"] == "not_connected"

    # Two of the three fakes report available: the echo agent and the failing
    # agent, both of which are "connected" but behave differently on execute.
    assert response.json()["data"]["available_count"] == 2


async def test_list_agents_includes_capabilities(client: AsyncClient) -> None:
    """Advertised capabilities are exposed to clients."""
    response = await client.get("/api/v1/agents")

    agents = {agent["name"]: agent for agent in response.json()["data"]["agents"]}
    assert agents["knowledge"]["capabilities"] == ["query", "ingest_document"]


async def test_get_single_agent(client: AsyncClient) -> None:
    """A single agent can be fetched by name."""
    response = await client.get("/api/v1/agents/knowledge")

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "knowledge"


async def test_get_unknown_agent_returns_404(client: AsyncClient) -> None:
    """An unregistered agent name returns a structured 404."""
    response = await client.get("/api/v1/agents/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AGENT_NOT_FOUND"
    assert "does-not-exist" in body["error"]["message"]


async def test_execute_returns_agent_result(client: AsyncClient) -> None:
    """A connected agent returns its result in the standard envelope."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={
            "agent": "knowledge",
            "operation": "query",
            "payload": {"question": "What is this document about?"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["agent"] == "knowledge"
    assert data["operation"] == "query"
    assert data["data"]["payload"]["question"] == "What is this document about?"
    assert data["duration_ms"] >= 0
    assert body["request_id"]


async def test_execute_defaults_payload_to_empty_object(client: AsyncClient) -> None:
    """Omitting the payload is valid and treated as an empty object."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "knowledge", "operation": "query"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["data"]["payload"] == {}


async def test_execute_unavailable_agent_returns_503(client: AsyncClient) -> None:
    """An unconnected agent returns 503 without crashing the process."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "automation", "operation": "draft_action", "payload": {}},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AGENT_UNAVAILABLE"
    assert body["error"]["details"]["status"] == "not_implemented"


async def test_execute_unknown_agent_returns_404(client: AsyncClient) -> None:
    """An unknown agent returns 404 rather than 503."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "nope", "operation": "query", "payload": {}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_execute_unsupported_operation_returns_404(
    client: AsyncClient,
) -> None:
    """An operation outside a connected agent's advertised set returns 404."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "knowledge", "operation": "delete_document", "payload": {}},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OPERATION_NOT_FOUND"


async def test_unconnected_agent_reports_503_regardless_of_operation(
    client: AsyncClient,
) -> None:
    """An unconnected agent returns 503 even for an unknown operation.

    Availability is checked first, since an agent with no implementation
    cannot report which operations it supports.
    """
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "automation", "operation": "not_a_real_operation", "payload": {}},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"


async def test_execute_failing_agent_returns_502(client: AsyncClient) -> None:
    """An agent that raises becomes a sanitized 502 response."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "performance", "operation": "ping", "payload": {}},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "AGENT_EXECUTION_FAILED"
    assert "sensitive internal detail" not in response.text


async def test_execute_missing_required_field_returns_422(
    client: AsyncClient,
) -> None:
    """A request missing required fields is rejected by validation."""
    response = await client.post("/api/v1/agents/execute", json={"agent": "knowledge"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_execute_empty_agent_name_returns_422(client: AsyncClient) -> None:
    """An empty agent name fails validation."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "", "operation": "query", "payload": {}},
    )

    assert response.status_code == 422


async def test_execute_rejects_non_object_payload(client: AsyncClient) -> None:
    """The payload must be a JSON object, not a list or scalar."""
    response = await client.post(
        "/api/v1/agents/execute",
        json={"agent": "knowledge", "operation": "query", "payload": ["not", "an", "object"]},
    )

    assert response.status_code == 422


async def test_execute_malformed_json_returns_422(client: AsyncClient) -> None:
    """Malformed request bodies return a structured validation error."""
    response = await client.post(
        "/api/v1/agents/execute",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


async def test_platform_agents_are_registered_under_their_stable_names() -> None:
    """The real platform agents register under the names clients use.

    The Knowledge and Automation agents are implemented, so whether they
    report as available depends on whether their optional dependencies are
    installed. The Performance Analyzer is served as background jobs, so it
    advertises no operation here and cannot be executed through this endpoint
    whatever its availability flag says.
    """
    from app.agents.factory import build_registry
    from app.core.config import Settings

    registry = build_registry(Settings(environment="development"))

    assert len(registry) == 3
    for name in ("knowledge", "automation", "performance"):
        assert registry.has(name)

    assert registry.get("performance").capabilities() == []
