"""
Configuration-as-Code Tools for AAP MCP Server.

Export AAP resources as YAML suitable for awx-manage, ansible-playbooks,
or the AAP Configuration-as-Code collection (infra.aap_configuration).

AAP API Mapping:
  export_project         GET /api/v2/projects/{id}/
  export_inventory       GET /api/v2/inventories/{id}/ + hosts + groups
  export_job_template    GET /api/v2/job_templates/{id}/
  export_workflow        GET /api/v2/workflow_job_templates/{id}/
  export_credentials     GET /api/v2/credentials/
  export_all_resources   Multiple GET calls
  import_resources       POST to relevant endpoints (not yet a native bulk API)
"""

import json
from typing import Any

import yaml
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from ..utils.api_client import AAPAPIError, aap_get, aap_list_all


def register(mcp: FastMCP):

    class ExportProjectInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        project_id: int = Field(..., ge=1, description="Project ID to export")
        format: str = Field(default="yaml", description="Output format: 'yaml' or 'json'")

    @mcp.tool(
        name="aap_export_project",
        annotations={"title": "Export Project as Code", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_export_project(params: ExportProjectInput, ctx: Context) -> str:
        """Export an AAP project as Configuration-as-Code (infra.aap_configuration format).

        Args:
            params (ExportProjectInput):
                - project_id (int): Project ID
                - format (str): 'yaml' or 'json'

        Returns:
            str: YAML/JSON suitable for aap_configuration collection playbooks.
        """
        try:
            data = await aap_get(ctx, f"/projects/{params.project_id}/")
            sf = data.get("summary_fields", {})
            resource = {
                "controller_projects": [
                    {
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "organization": sf.get("organization", {}).get("name", ""),
                        "scm_type": data.get("scm_type", ""),
                        "scm_url": data.get("scm_url", ""),
                        "scm_branch": data.get("scm_branch", ""),
                        "scm_clean": data.get("scm_clean", False),
                        "scm_delete_on_update": data.get("scm_delete_on_update", False),
                        "update_on_launch": data.get("update_on_launch", True),
                        "credential": sf.get("credential", {}).get("name", "") or None,
                    }
                ]
            }
            if params.format == "json":
                return json.dumps(resource, indent=2)
            return yaml.dump(resource, default_flow_style=False, allow_unicode=True)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ExportJobTemplateInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        template_id: int = Field(..., ge=1, description="Job template ID to export")
        format: str = Field(default="yaml", description="'yaml' or 'json'")

    @mcp.tool(
        name="aap_export_job_template",
        annotations={"title": "Export Job Template as Code", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_export_job_template(params: ExportJobTemplateInput, ctx: Context) -> str:
        """Export a job template as Configuration-as-Code YAML.

        Args:
            params (ExportJobTemplateInput):
                - template_id (int): Template ID
                - format (str): 'yaml' or 'json'

        Returns:
            str: YAML compatible with infra.aap_configuration.controller_job_templates.
        """
        try:
            data = await aap_get(ctx, f"/job_templates/{params.template_id}/")
            sf = data.get("summary_fields", {})

            creds = [c["name"] for c in sf.get("credentials", [])]
            resource = {
                "controller_templates": [
                    {
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "organization": sf.get("organization", {}).get("name", "") or None,
                        "project": sf.get("project", {}).get("name", ""),
                        "inventory": sf.get("inventory", {}).get("name", "") or None,
                        "playbook": data.get("playbook", ""),
                        "job_type": data.get("job_type", "run"),
                        "verbosity": data.get("verbosity", 0),
                        "become_enabled": data.get("become_enabled", False),
                        "diff_mode": data.get("diff_mode", False),
                        "ask_variables_on_launch": data.get("ask_variables_on_launch", False),
                        "ask_inventory_on_launch": data.get("ask_inventory_on_launch", False),
                        "ask_credential_on_launch": data.get("ask_credential_on_launch", False),
                        "extra_vars": data.get("extra_vars", "") or None,
                        "credentials": creds,
                        "survey_enabled": data.get("survey_enabled", False),
                    }
                ]
            }
            if params.format == "json":
                return json.dumps(resource, indent=2)
            return yaml.dump(resource, default_flow_style=False, allow_unicode=True)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ExportWorkflowInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        workflow_id: int = Field(..., ge=1)
        format: str = Field(default="yaml")

    @mcp.tool(
        name="aap_export_workflow",
        annotations={"title": "Export Workflow as Code", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_export_workflow(params: ExportWorkflowInput, ctx: Context) -> str:
        """Export a workflow template as Configuration-as-Code YAML.

        Args:
            params (ExportWorkflowInput):
                - workflow_id (int): Workflow template ID
                - format (str): 'yaml' or 'json'

        Returns:
            str: YAML compatible with infra.aap_configuration.controller_workflows.
        """
        try:
            data = await aap_get(ctx, f"/workflow_job_templates/{params.workflow_id}/")
            nodes_data = await aap_get(ctx, f"/workflow_job_templates/{params.workflow_id}/workflow_nodes/")

            nodes = []
            for n in nodes_data.get("results", []):
                sf = n.get("summary_fields", {})
                node = {
                    "identifier": str(n["id"]),
                    "unified_job_template": sf.get("unified_job_template", {}).get("name"),
                    "success_nodes": n.get("success_nodes", []),
                    "failure_nodes": n.get("failure_nodes", []),
                    "always_nodes": n.get("always_nodes", []),
                }
                nodes.append(node)

            resource = {
                "controller_workflows": [
                    {
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "organization": data.get("summary_fields", {}).get("organization", {}).get("name", "") or None,
                        "ask_variables_on_launch": data.get("ask_variables_on_launch", False),
                        "extra_vars": data.get("extra_vars", "") or None,
                        "survey_enabled": data.get("survey_enabled", False),
                        "workflow_nodes": nodes,
                    }
                ]
            }
            if params.format == "json":
                return json.dumps(resource, indent=2)
            return yaml.dump(resource, default_flow_style=False, allow_unicode=True)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ExportInventoryInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        inventory_id: int = Field(..., ge=1)
        include_hosts: bool = Field(default=True, description="Include host list in export")
        format: str = Field(default="yaml")

    @mcp.tool(
        name="aap_export_inventory",
        annotations={"title": "Export Inventory as Code", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_export_inventory(params: ExportInventoryInput, ctx: Context) -> str:
        """Export an AAP inventory as Configuration-as-Code YAML.

        Args:
            params (ExportInventoryInput):
                - inventory_id (int): Inventory ID
                - include_hosts (bool): Include host entries
                - format (str): 'yaml' or 'json'

        Returns:
            str: YAML for infra.aap_configuration.controller_inventories.
        """
        try:
            data = await aap_get(ctx, f"/inventories/{params.inventory_id}/")
            sf = data.get("summary_fields", {})

            inv = {
                "name": data["name"],
                "description": data.get("description", ""),
                "organization": sf.get("organization", {}).get("name", ""),
                "variables": data.get("variables", "") or None,
                "kind": data.get("kind", "") or None,
            }

            if params.include_hosts:
                hosts, _ = await aap_list_all(ctx, "/hosts/", params={"inventory": params.inventory_id})
                inv["hosts"] = [
                    {
                        "name": h["name"],
                        "description": h.get("description", "") or None,
                        "variables": h.get("variables", "") or None,
                        "enabled": h.get("enabled", True),
                    }
                    for h in hosts
                ]

            resource = {"controller_inventories": [inv]}
            if params.format == "json":
                return json.dumps(resource, indent=2)
            return yaml.dump(resource, default_flow_style=False, allow_unicode=True)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ExportAllInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        organization_id: int | None = Field(default=None, description="Filter exports by organization ID")
        format: str = Field(default="yaml")

    @mcp.tool(
        name="aap_export_all_resources",
        annotations={"title": "Export All Resources as Code", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_export_all_resources(params: ExportAllInput, ctx: Context) -> str:
        """Export all AAP resources (projects, inventories, job templates, workflows) as Configuration-as-Code.

        Example: "Export all job templates as code"

        This produces a single YAML document compatible with the
        infra.aap_configuration Ansible collection.

        Args:
            params (ExportAllInput):
                - organization_id (Optional[int]): Scope exports to one org
                - format (str): 'yaml' or 'json'

        Returns:
            str: Combined YAML/JSON export of all resources.
        """
        try:
            result: dict[str, Any] = {}
            org_filter = {"organization": params.organization_id} if params.organization_id else {}

            # Projects
            projects, _ = await aap_list_all(ctx, "/projects/", params=org_filter)
            result["controller_projects"] = [
                {
                    "name": p["name"],
                    "description": p.get("description", ""),
                    "scm_type": p.get("scm_type", ""),
                    "scm_url": p.get("scm_url", ""),
                    "scm_branch": p.get("scm_branch", ""),
                    "organization": p.get("summary_fields", {}).get("organization", {}).get("name", ""),
                }
                for p in projects
            ]

            # Inventories
            inventories, _ = await aap_list_all(ctx, "/inventories/", params=org_filter)
            result["controller_inventories"] = [
                {
                    "name": inv["name"],
                    "organization": inv.get("summary_fields", {}).get("organization", {}).get("name", ""),
                    "description": inv.get("description", ""),
                    "kind": inv.get("kind", "") or None,
                }
                for inv in inventories
            ]

            # Job Templates
            jts, _ = await aap_list_all(ctx, "/job_templates/", params=org_filter)
            result["controller_templates"] = [
                {
                    "name": jt["name"],
                    "playbook": jt.get("playbook", ""),
                    "project": jt.get("summary_fields", {}).get("project", {}).get("name", ""),
                    "inventory": jt.get("summary_fields", {}).get("inventory", {}).get("name") or None,
                    "job_type": jt.get("job_type", "run"),
                    "verbosity": jt.get("verbosity", 0),
                    "become_enabled": jt.get("become_enabled", False),
                }
                for jt in jts
            ]

            # Workflows
            wfs, _ = await aap_list_all(ctx, "/workflow_job_templates/", params=org_filter)
            result["controller_workflows"] = [
                {
                    "name": wf["name"],
                    "organization": wf.get("summary_fields", {}).get("organization", {}).get("name", "") or None,
                    "description": wf.get("description", ""),
                }
                for wf in wfs
            ]

            # Schedules
            scheds, _ = await aap_list_all(ctx, "/schedules/")
            result["controller_schedules"] = [
                {
                    "name": s["name"],
                    "rrule": s.get("rrule", ""),
                    "unified_job_template": s.get("summary_fields", {}).get("unified_job_template", {}).get("name"),
                    "enabled": s.get("enabled", True),
                }
                for s in scheds
            ]

            if params.format == "json":
                return json.dumps(result, indent=2)
            return yaml.dump(result, default_flow_style=False, allow_unicode=True)
        except AAPAPIError as e:
            return f"Error: {e}"
