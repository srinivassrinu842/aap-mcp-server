"""
Integration tests for AAP MCP Server.
Requires real AAP_CONTROLLER_URL and AAP_OAUTH_TOKEN env vars.
Run with: pytest tests/integration/ -m "not destructive"

These tests run in READ-ONLY mode by default.
Mark destructive tests with @pytest.mark.destructive to exclude from CI.
"""

import json
import os
import pytest
import httpx

# Skip all integration tests if no AAP URL configured
pytestmark = pytest.mark.skipif(
    not os.getenv("AAP_CONTROLLER_URL"),
    reason="AAP_CONTROLLER_URL not set - skipping integration tests",
)


@pytest.fixture(scope="session")
def aap_url():
    return os.environ["AAP_CONTROLLER_URL"].rstrip("/")


@pytest.fixture(scope="session")
def aap_token():
    return os.environ.get("AAP_OAUTH_TOKEN", "")


@pytest.fixture(scope="session")
async def http_client(aap_url, aap_token):
    """Shared httpx client for integration tests."""
    async with httpx.AsyncClient(
        base_url=aap_url,
        headers={
            "Authorization": f"Bearer {aap_token}",
            "Content-Type": "application/json",
        },
        verify=os.getenv("AAP_VERIFY_SSL", "true").lower() == "true",
        timeout=30.0,
    ) as client:
        yield client


class TestControllerConnectivity:

    @pytest.mark.asyncio
    async def test_ping_endpoint(self, http_client):
        """Verify we can reach the AAP Controller API."""
        response = await http_client.get("/api/v2/ping/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "ha" in data

    @pytest.mark.asyncio
    async def test_authentication(self, http_client):
        """Verify the OAuth token is valid."""
        response = await http_client.get("/api/v2/me/")
        assert response.status_code == 200
        data = response.json()
        # /api/v2/me/ returns a paginated list
        results = data.get("results", [data])
        assert len(results) > 0
        assert "username" in results[0]


class TestReadOperations:

    @pytest.mark.asyncio
    async def test_list_organizations(self, http_client):
        response = await http_client.get("/api/v2/organizations/", params={"page_size": 5})
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "results" in data

    @pytest.mark.asyncio
    async def test_list_job_templates(self, http_client):
        response = await http_client.get("/api/v2/job_templates/", params={"page_size": 5})
        assert response.status_code == 200
        data = response.json()
        assert "count" in data

    @pytest.mark.asyncio
    async def test_list_inventories(self, http_client):
        response = await http_client.get("/api/v2/inventories/", params={"page_size": 5})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_credentials(self, http_client):
        response = await http_client.get("/api/v2/credentials/", params={"page_size": 5})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_cluster_health(self, http_client):
        response = await http_client.get("/api/v2/instances/")
        assert response.status_code == 200
        data = response.json()
        instances = data.get("results", [])
        # At least one instance should be in ready state
        ready = [i for i in instances if i.get("node_state") == "ready"]
        assert len(ready) >= 1, "No ready instances found - cluster may be unhealthy"


class TestMCPServerIntegration:
    """Test the full MCP server stack against a live AAP."""

    @pytest.mark.asyncio
    async def test_mcp_list_orgs_tool(self):
        """Test aap_list_organizations tool end-to-end via server startup."""
        # This test validates the server can start and tools are callable
        # Full E2E would require MCP client; here we validate the tool imports
        from src.tools.organizations import register
        from mcp.server.fastmcp import FastMCP
        mcp = FastMCP("test_integration")
        register(mcp)
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "aap_list_organizations" in tool_names
        assert "aap_create_organization" in tool_names
        assert "aap_delete_organization" in tool_names


# Destructive tests - excluded from standard CI
@pytest.mark.destructive
class TestDestructiveOperations:
    """Tests that create/modify/delete resources. Run manually with -m destructive."""

    @pytest.mark.asyncio
    async def test_create_and_delete_organization(self, http_client):
        """Create a test org and immediately delete it."""
        # Create
        create_resp = await http_client.post("/api/v2/organizations/", json={
            "name": "aap-mcp-integration-test",
            "description": "Temporary org for MCP server integration tests",
        })
        assert create_resp.status_code == 201
        org_id = create_resp.json()["id"]

        # Delete
        delete_resp = await http_client.delete(f"/api/v2/organizations/{org_id}/")
        assert delete_resp.status_code == 204
