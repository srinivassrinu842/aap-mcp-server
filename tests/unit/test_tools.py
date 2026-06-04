"""
Unit tests for AAP MCP Server tools.
Uses respx to mock HTTP responses without a real AAP instance.
"""

import json
import pytest
import httpx
import respx
from unittest.mock import MagicMock, patch


# ─── Fixtures ─────────────────────────────────────────────────────────────────

AAP_BASE = "https://controller.example.com/api/v2"

def make_mock_ctx(read_only=False, require_confirmation=True):
    """Create a mock FastMCP Context with lifespan state."""
    settings = MagicMock()
    settings.read_only_mode = read_only
    settings.require_confirmation = require_confirmation

    http_client = httpx.AsyncClient(base_url="https://controller.example.com")

    ctx = MagicMock()
    ctx.request_context = MagicMock()
    ctx.request_context.lifespan_context = {
        "http_client": http_client,
        "settings": settings,
        "audit_logger": MagicMock(),
        "auth_client": MagicMock(),
    }
    return ctx


def get_tool(mcp, name):
    """Retrieve a registered tool by name."""
    return mcp._tool_manager._tools[name]


async def call_tool(tool, args: dict, ctx) -> str:
    """Call a tool using the MCP run() API.
    The MCP SDK wraps all tool arguments under a 'params' key internally.
    Returns the raw string result from the tool function.
    """
    return await tool.run({"params": args}, context=ctx)


# ─── Sample data ──────────────────────────────────────────────────────────────

SAMPLE_ORG = {"id": 1, "name": "Default", "description": "Default org", "max_hosts": 0}
SAMPLE_ORG_LIST = {"count": 1, "next": None, "previous": None, "results": [SAMPLE_ORG]}

SAMPLE_JT = {
    "id": 10, "name": "Install Apache", "description": "",
    "playbook": "site.yml", "job_type": "run", "verbosity": 0,
    "become_enabled": False, "ask_variables_on_launch": False,
    "ask_inventory_on_launch": False, "ask_credential_on_launch": False,
    "survey_enabled": False, "extra_vars": "", "diff_mode": False,
    "created": "2024-01-01T00:00:00Z", "modified": "2024-01-01T00:00:00Z",
    "summary_fields": {
        "project": {"id": 5, "name": "myproject"},
        "inventory": {"id": 3, "name": "Production"},
        "credentials": [],
        "organization": {"id": 1, "name": "Default"},
    },
}

SAMPLE_JOB = {
    "id": 42, "status": "successful", "elapsed": 30.5,
    "started": "2024-01-01T10:00:00Z", "finished": "2024-01-01T10:00:30Z",
    "failed": 0, "summary_fields": {},
}

PING_RESPONSE = {
    "ha": True, "version": "4.5.0", "active_node": "controller-1",
    "install_uuid": "abc-123", "instances": {}, "instance_groups": {},
}


# ─── Organization Tests ────────────────────────────────────────────────────────

class TestOrganizations:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import organizations
        self.mcp = FastMCP("test_orgs")
        organizations.register(self.mcp)

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_organizations(self):
        respx.get(f"{AAP_BASE}/organizations/").mock(
            return_value=httpx.Response(200, json=SAMPLE_ORG_LIST)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_organizations")
        raw = await call_tool(tool, {"page": 1, "page_size": 20}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1
        assert result["results"][0]["name"] == "Default"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_organization(self):
        respx.get(f"{AAP_BASE}/organizations/1/").mock(
            return_value=httpx.Response(200, json=SAMPLE_ORG)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_organization")
        raw = await call_tool(tool, {"org_id": 1}, ctx)
        result = json.loads(raw)
        assert result["id"] == 1
        assert result["name"] == "Default"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_organization(self):
        respx.post(f"{AAP_BASE}/organizations/").mock(
            return_value=httpx.Response(201, json=SAMPLE_ORG)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_create_organization")
        raw = await call_tool(tool, {"name": "Default", "description": "", "max_hosts": 0}, ctx)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_organization_requires_confirmation(self):
        respx.get(f"{AAP_BASE}/organizations/1/").mock(
            return_value=httpx.Response(200, json=SAMPLE_ORG)
        )
        ctx = make_mock_ctx(require_confirmation=True)
        tool = get_tool(self.mcp, "aap_delete_organization")
        raw = await call_tool(tool, {"org_id": 1}, ctx)
        result = raw
        assert "DESTRUCTIVE OPERATION" in result
        assert "confirmation_token" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_read_only_mode_blocks_create(self):
        ctx = make_mock_ctx(read_only=True)
        tool = get_tool(self.mcp, "aap_create_organization")
        raw = await call_tool(tool, {"name": "Test", "description": "", "max_hosts": 0}, ctx)
        assert "READ-ONLY" in raw

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_organization(self):
        updated = {**SAMPLE_ORG, "description": "Updated"}
        respx.patch(f"{AAP_BASE}/organizations/1/").mock(
            return_value=httpx.Response(200, json=updated)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_update_organization")
        raw = await call_tool(tool, {"org_id": 1, "description": "Updated"}, ctx)
        result = json.loads(raw)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_update_organization_no_fields(self):
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_update_organization")
        raw = await call_tool(tool, {"org_id": 1}, ctx)
        assert "No fields" in raw

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_organizations_search_filter(self):
        respx.get(f"{AAP_BASE}/organizations/").mock(
            return_value=httpx.Response(200, json=SAMPLE_ORG_LIST)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_organizations")
        raw = await call_tool(tool, {"page": 1, "page_size": 20, "search": "Default"}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1


# ─── Project Tests ─────────────────────────────────────────────────────────────

class TestProjects:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import projects
        self.mcp = FastMCP("test_projects")
        projects.register(self.mcp)

    SAMPLE_PROJECT = {
        "id": 5, "name": "redis-automation", "description": "",
        "scm_type": "git", "scm_url": "https://github.com/org/redis-automation",
        "scm_branch": "main", "scm_clean": False, "scm_delete_on_update": False,
        "update_on_launch": True, "status": "successful",
        "last_updated": "2024-01-01T00:00:00Z", "last_update_failed": False,
        "summary_fields": {"organization": {"id": 1, "name": "Default"}, "credential": {}},
    }

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_projects(self):
        respx.get(f"{AAP_BASE}/projects/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [self.SAMPLE_PROJECT]})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_projects")
        raw = await call_tool(tool, {"page": 1, "page_size": 20}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1
        assert result["results"][0]["scm_url"] == "https://github.com/org/redis-automation"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_project(self):
        respx.post(f"{AAP_BASE}/projects/").mock(
            return_value=httpx.Response(201, json=self.SAMPLE_PROJECT)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_create_project")
        raw = await call_tool(tool, {
            "name": "redis-automation",
            "scm_type": "git",
            "scm_url": "https://github.com/org/redis-automation",
        }, ctx)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["id"] == 5

    @respx.mock
    @pytest.mark.asyncio
    async def test_sync_project(self):
        respx.post(f"{AAP_BASE}/projects/5/update/").mock(
            return_value=httpx.Response(202, json={"id": 100})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_sync_project")
        raw = await call_tool(tool, {"project_id": 5}, ctx)
        result = json.loads(raw)
        assert result["success"] is True


# ─── Job Template Tests ────────────────────────────────────────────────────────

class TestJobTemplates:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import job_templates
        self.mcp = FastMCP("test_jt")
        job_templates.register(self.mcp)

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_job_templates(self):
        respx.get(f"{AAP_BASE}/job_templates/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [SAMPLE_JT]})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_job_templates")
        raw = await call_tool(tool, {"page": 1, "page_size": 20}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1
        assert result["results"][0]["name"] == "Install Apache"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_job_template(self):
        respx.get(f"{AAP_BASE}/job_templates/10/").mock(
            return_value=httpx.Response(200, json=SAMPLE_JT)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_job_template")
        raw = await call_tool(tool, {"template_id": 10}, ctx)
        result = json.loads(raw)
        assert result["playbook"] == "site.yml"

    @respx.mock
    @pytest.mark.asyncio
    async def test_launch_job_template(self):
        launch_resp = {"id": 42, "status": "pending"}
        respx.post(f"{AAP_BASE}/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json=launch_resp)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_launch_job_template")
        raw = await call_tool(tool, {"template_id": 10}, ctx)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["job_id"] == 42

    @respx.mock
    @pytest.mark.asyncio
    async def test_launch_with_extra_vars(self):
        respx.post(f"{AAP_BASE}/job_templates/10/launch/").mock(
            return_value=httpx.Response(201, json={"id": 43, "status": "pending"})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_launch_job_template")
        raw = await call_tool(tool, {
            "template_id": 10,
            "extra_vars": '{"env": "production"}',
            "limit": "web01.example.com",
        }, ctx)
        result = json.loads(raw)
        assert result["job_id"] == 43

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_job_template_404(self):
        respx.get(f"{AAP_BASE}/job_templates/999/").mock(
            return_value=httpx.Response(404, json={"detail": "Not found."})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_job_template")
        raw = await call_tool(tool, {"template_id": 999}, ctx)
        assert "Error" in raw
        assert "not found" in raw.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_cancel_job_requires_confirmation(self):
        ctx = make_mock_ctx(require_confirmation=True)
        tool = get_tool(self.mcp, "aap_cancel_job")
        raw = await call_tool(tool, {"job_id": 42}, ctx)
        assert "DESTRUCTIVE OPERATION" in raw

    @respx.mock
    @pytest.mark.asyncio
    async def test_copy_job_template(self):
        copy_resp = {"id": 11, "name": "Install Apache (copy)"}
        respx.post(f"{AAP_BASE}/job_templates/10/copy/").mock(
            return_value=httpx.Response(201, json=copy_resp)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_copy_job_template")
        raw = await call_tool(tool, {"template_id": 10, "name": "Install Apache (copy)"}, ctx)
        result = json.loads(raw)
        assert result["id"] == 11


# ─── Inventory Tests ───────────────────────────────────────────────────────────

class TestInventories:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import inventories
        self.mcp = FastMCP("test_inv")
        inventories.register(self.mcp)

    SAMPLE_INV = {
        "id": 3, "name": "AWS-Production", "description": "",
        "kind": "", "total_hosts": 5, "hosts_with_active_failures": 0,
        "summary_fields": {"organization": {"id": 1, "name": "Default"}},
    }

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_inventory(self):
        respx.post(f"{AAP_BASE}/inventories/").mock(
            return_value=httpx.Response(201, json=self.SAMPLE_INV)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_create_inventory")
        raw = await call_tool(tool, {
            "name": "AWS-Production",
            "organization_id": 1,
        }, ctx)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["name"] == "AWS-Production"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_host(self):
        host_resp = {"id": 20, "name": "web01.example.com", "enabled": True,
                     "description": "", "variables": "", "summary_fields": {}}
        respx.post(f"{AAP_BASE}/hosts/").mock(
            return_value=httpx.Response(201, json=host_resp)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_create_host")
        raw = await call_tool(tool, {
            "name": "web01.example.com",
            "inventory_id": 3,
        }, ctx)
        result = json.loads(raw)
        assert result["name"] == "web01.example.com"

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_host_to_group(self):
        respx.post(f"{AAP_BASE}/groups/5/hosts/").mock(
            return_value=httpx.Response(204)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_add_host_to_group")
        raw = await call_tool(tool, {"group_id": 5, "host_id": 20}, ctx)
        result = json.loads(raw)
        assert result["success"] is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_inventory(self):
        updated = {**self.SAMPLE_INV, "description": "Updated"}
        respx.patch(f"{AAP_BASE}/inventories/3/").mock(
            return_value=httpx.Response(200, json=updated)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_update_inventory")
        raw = await call_tool(tool, {"inventory_id": 3, "description": "Updated"}, ctx)
        result = json.loads(raw)
        assert result["success"] is True


# ─── Workflow Tests ────────────────────────────────────────────────────────────

class TestWorkflows:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import workflows
        self.mcp = FastMCP("test_wf")
        workflows.register(self.mcp)

    SAMPLE_WF = {
        "id": 7, "name": "Redis Production Workflow", "description": "",
        "ask_variables_on_launch": False, "survey_enabled": False, "extra_vars": "",
        "summary_fields": {"organization": {"id": 1, "name": "Default"}},
    }

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_workflow_templates(self):
        respx.get(f"{AAP_BASE}/workflow_job_templates/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [self.SAMPLE_WF]})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_workflow_templates")
        raw = await call_tool(tool, {"page": 1, "page_size": 20}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1
        assert result["results"][0]["name"] == "Redis Production Workflow"

    @respx.mock
    @pytest.mark.asyncio
    async def test_launch_workflow(self):
        respx.post(f"{AAP_BASE}/workflow_job_templates/7/launch/").mock(
            return_value=httpx.Response(201, json={"id": 99, "status": "pending"})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_launch_workflow")
        raw = await call_tool(tool, {"workflow_id": 7}, ctx)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["workflow_job_id"] == 99

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_workflow_template(self):
        updated = {**self.SAMPLE_WF, "description": "Updated"}
        respx.patch(f"{AAP_BASE}/workflow_job_templates/7/").mock(
            return_value=httpx.Response(200, json=updated)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_update_workflow_template")
        raw = await call_tool(tool, {"workflow_id": 7, "description": "Updated"}, ctx)
        result = json.loads(raw)
        assert result["success"] is True


# ─── Monitoring Tests ──────────────────────────────────────────────────────────

class TestMonitoring:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import monitoring
        self.mcp = FastMCP("test_mon")
        monitoring.register(self.mcp)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_failed_jobs(self):
        failed_job = {
            **SAMPLE_JOB, "status": "failed",
            "summary_fields": {
                "job_template": {"name": "Deploy App"},
                "created_by": {"username": "admin"},
            },
        }
        respx.get(f"{AAP_BASE}/jobs/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [failed_job]})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_failed_jobs")
        raw = await call_tool(tool, {"hours": 24, "limit": 20}, ctx)
        result = json.loads(raw)
        assert result["total_failed"] == 1
        assert result["window_hours"] == 24

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_running_jobs(self):
        running_job = {**SAMPLE_JOB, "status": "running", "summary_fields": {
            "job_template": {"name": "Deploy App"},
            "created_by": {"username": "admin"},
        }}
        respx.get(f"{AAP_BASE}/jobs/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [running_job]})
        )
        respx.get(f"{AAP_BASE}/workflow_jobs/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_running_jobs")
        raw = await call_tool(tool, {}, ctx)
        result = json.loads(raw)
        assert result["running_count"] == 1


# ─── Platform Admin Tests ──────────────────────────────────────────────────────

class TestPlatformAdmin:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import platform_admin
        self.mcp = FastMCP("test_admin")
        platform_admin.register(self.mcp)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_controller_health(self):
        respx.get(f"{AAP_BASE}/ping/").mock(
            return_value=httpx.Response(200, json=PING_RESPONSE)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_controller_health")
        raw = await call_tool(tool, {}, ctx)
        result = json.loads(raw)
        assert result["ha_enabled"] is True
        assert result["version"] == "4.5.0"
        assert result["status"] == "healthy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_license_info(self):
        config_resp = {"license_info": {
            "license_type": "enterprise", "valid_key": True, "compliant": True,
            "total_instances": 100, "current_instances": 42,
        }}
        respx.get(f"{AAP_BASE}/config/").mock(
            return_value=httpx.Response(200, json=config_resp)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_license_info")
        raw = await call_tool(tool, {}, ctx)
        result = json.loads(raw)
        assert result["license_type"] == "enterprise"
        assert result["valid_key"] is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_cluster_status(self):
        instances_resp = {"count": 2, "results": [
            {"id": 1, "hostname": "ctrl-1", "node_type": "control",
             "node_state": "ready", "capacity": 100, "consumed_capacity": 20,
             "percent_capacity_remaining": 80, "enabled": True, "version": "4.5.0"},
            {"id": 2, "hostname": "exec-1", "node_type": "execution",
             "node_state": "ready", "capacity": 200, "consumed_capacity": 50,
             "percent_capacity_remaining": 75, "enabled": True, "version": "4.5.0"},
        ]}
        respx.get(f"{AAP_BASE}/instances/").mock(
            return_value=httpx.Response(200, json=instances_resp)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_cluster_status")
        raw = await call_tool(tool, {}, ctx)
        result = json.loads(raw)
        assert result["total_nodes"] == 2
        assert result["healthy_nodes"] == 2


# ─── Credential Tests ──────────────────────────────────────────────────────────

class TestCredentials:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import credentials
        self.mcp = FastMCP("test_creds")
        credentials.register(self.mcp)

    SAMPLE_CRED = {
        "id": 8, "name": "SSH Key Prod", "description": "",
        "kind": "ssh", "managed": False,
        "inputs": {"username": "ansible", "ssh_key_data": "$encrypted$"},
        "summary_fields": {
            "credential_type": {"id": 1, "name": "Machine"},
            "organization": {"id": 1, "name": "Default"},
        },
    }

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_credentials(self):
        respx.get(f"{AAP_BASE}/credentials/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [self.SAMPLE_CRED]})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_credentials")
        raw = await call_tool(tool, {"page": 1, "page_size": 20}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1
        assert result["results"][0]["name"] == "SSH Key Prod"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_credential(self):
        respx.post(f"{AAP_BASE}/credentials/").mock(
            return_value=httpx.Response(201, json=self.SAMPLE_CRED)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_create_credential")
        raw = await call_tool(tool, {
            "name": "SSH Key Prod",
            "credential_type_id": 1,
            "inputs": {"username": "ansible", "ssh_key_data": "-----BEGIN..."},
        }, ctx)
        result = json.loads(raw)
        assert result["success"] is True
        assert result["id"] == 8


# ─── Config-as-Code Tests ──────────────────────────────────────────────────────

class TestConfigAsCode:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import config_as_code
        self.mcp = FastMCP("test_cac")
        config_as_code.register(self.mcp)

    @respx.mock
    @pytest.mark.asyncio
    async def test_export_project_yaml(self):
        proj = {
            "id": 5, "name": "redis-automation", "description": "",
            "scm_type": "git", "scm_url": "https://github.com/org/redis",
            "scm_branch": "main", "scm_clean": False,
            "scm_delete_on_update": False, "update_on_launch": True,
            "summary_fields": {"organization": {"name": "Default"}, "credential": {}},
        }
        respx.get(f"{AAP_BASE}/projects/5/").mock(
            return_value=httpx.Response(200, json=proj)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_export_project")
        raw = await call_tool(tool, {"project_id": 5, "format": "yaml"}, ctx)
        result = raw
        assert "controller_projects" in result
        assert "redis-automation" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_export_job_template_json(self):
        respx.get(f"{AAP_BASE}/job_templates/10/").mock(
            return_value=httpx.Response(200, json=SAMPLE_JT)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_export_job_template")
        raw = await call_tool(tool, {"template_id": 10, "format": "json"}, ctx)
        result = json.loads(raw)
        assert "controller_templates" in result
        assert result["controller_templates"][0]["playbook"] == "site.yml"


# ─── Users Tests ──────────────────────────────────────────────────────────────

class TestUsers:

    def setup_method(self):
        from mcp.server.fastmcp import FastMCP
        from src.tools import users
        self.mcp = FastMCP("test_users")
        users.register(self.mcp)

    SAMPLE_USER = {
        "id": 5, "username": "jdoe", "email": "jdoe@example.com",
        "first_name": "John", "last_name": "Doe",
        "is_superuser": False, "is_system_auditor": False,
        "last_login": None, "created": "2024-01-01T00:00:00Z",
    }

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_users(self):
        respx.get(f"{AAP_BASE}/users/").mock(
            return_value=httpx.Response(200, json={"count": 1, "results": [self.SAMPLE_USER]})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_users")
        raw = await call_tool(tool, {"page": 1, "page_size": 20}, ctx)
        result = json.loads(raw)
        assert result["count"] == 1
        assert result["results"][0]["username"] == "jdoe"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_superusers_filter(self):
        respx.get(f"{AAP_BASE}/users/").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_list_users")
        raw = await call_tool(tool, {"page": 1, "page_size": 20, "is_superuser": True}, ctx)
        result = json.loads(raw)
        assert result["count"] == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_user(self):
        respx.get(f"{AAP_BASE}/users/5/").mock(
            return_value=httpx.Response(200, json=self.SAMPLE_USER)
        )
        ctx = make_mock_ctx()
        tool = get_tool(self.mcp, "aap_get_user")
        raw = await call_tool(tool, {"user_id": 5}, ctx)
        result = json.loads(raw)
        assert result["username"] == "jdoe"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_user_requires_confirmation(self):
        respx.get(f"{AAP_BASE}/users/5/").mock(
            return_value=httpx.Response(200, json=self.SAMPLE_USER)
        )
        ctx = make_mock_ctx(require_confirmation=True)
        tool = get_tool(self.mcp, "aap_delete_user")
        raw = await call_tool(tool, {"user_id": 5}, ctx)
        assert "DESTRUCTIVE OPERATION" in raw
