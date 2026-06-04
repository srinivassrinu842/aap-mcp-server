"""
Workflow Template Management Tools for AAP MCP Server.

AAP API Mapping:
  list_workflow_templates   GET    /api/v2/workflow_job_templates/
  get_workflow_template     GET    /api/v2/workflow_job_templates/{id}/
  create_workflow_template  POST   /api/v2/workflow_job_templates/
  update_workflow_template  PATCH  /api/v2/workflow_job_templates/{id}/
  delete_workflow_template  DELETE /api/v2/workflow_job_templates/{id}/
  launch_workflow           POST   /api/v2/workflow_job_templates/{id}/launch/
  get_workflow_status       GET    /api/v2/workflow_jobs/{id}/
"""

import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from ..utils.api_client import (
    aap_get, aap_post, aap_patch, aap_delete,
    AAPAPIError, require_confirmation_token, validate_confirmation_token,
    format_job_status, paginate_params,
)


def register(mcp: FastMCP):

    class ListWFTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_list_workflow_templates",
        annotations={"title": "List Workflow Templates", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_workflow_templates(params: ListWFTInput, ctx: Context) -> str:
        """List AAP workflow job templates.

        Args:
            params (ListWFTInput): Pagination and filter.

        Returns:
            str: JSON with count and workflow template list.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search

            data = await aap_get(ctx, "/workflow_job_templates/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "results": [
                    {
                        "id": wf["id"],
                        "name": wf["name"],
                        "description": wf.get("description", ""),
                        "organization": wf.get("summary_fields", {}).get("organization", {}).get("name"),
                        "survey_enabled": wf.get("survey_enabled", False),
                        "ask_variables_on_launch": wf.get("ask_variables_on_launch", False),
                    }
                    for wf in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetWFTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        workflow_id: int = Field(..., ge=1, description="Workflow template ID")

    @mcp.tool(
        name="aap_get_workflow_template",
        annotations={"title": "Get Workflow Template", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_workflow_template(params: GetWFTInput, ctx: Context) -> str:
        """Get full details of an AAP workflow template including node structure.

        Args:
            params (GetWFTInput):
                - workflow_id (int): Workflow template ID

        Returns:
            str: JSON with workflow details and node count.
        """
        try:
            data = await aap_get(ctx, f"/workflow_job_templates/{params.workflow_id}/")
            nodes = await aap_get(ctx, f"/workflow_job_templates/{params.workflow_id}/workflow_nodes/")
            return json.dumps({
                "id": data["id"],
                "name": data["name"],
                "description": data.get("description", ""),
                "organization": data.get("summary_fields", {}).get("organization", {}),
                "survey_enabled": data.get("survey_enabled", False),
                "ask_variables_on_launch": data.get("ask_variables_on_launch", False),
                "extra_vars": data.get("extra_vars", ""),
                "node_count": nodes.get("count", 0),
                "nodes": [
                    {
                        "id": n["id"],
                        "job_template": n.get("summary_fields", {}).get("unified_job_template", {}).get("name"),
                        "success_nodes": n.get("success_nodes", []),
                        "failure_nodes": n.get("failure_nodes", []),
                        "always_nodes": n.get("always_nodes", []),
                    }
                    for n in nodes.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateWFTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512, description="Workflow template name")
        organization_id: Optional[int] = Field(default=None, ge=1)
        description: str = Field(default="")
        extra_vars: str = Field(default="")
        ask_variables_on_launch: bool = Field(default=False)
        survey_enabled: bool = Field(default=False)

    @mcp.tool(
        name="aap_create_workflow_template",
        annotations={"title": "Create Workflow Template", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_workflow_template(params: CreateWFTInput, ctx: Context) -> str:
        """Create a new AAP workflow template.

        Example: "Create a workflow that provisions EC2 and configures Apache"
        Note: After creation, use the AAP UI or API to add workflow nodes.

        Args:
            params (CreateWFTInput): Workflow template configuration.

        Returns:
            str: JSON with created workflow id and name.
        """
        try:
            payload: Dict[str, Any] = {
                "name": params.name,
                "description": params.description,
                "extra_vars": params.extra_vars,
                "ask_variables_on_launch": params.ask_variables_on_launch,
                "survey_enabled": params.survey_enabled,
            }
            if params.organization_id:
                payload["organization"] = params.organization_id

            data = await aap_post(ctx, "/workflow_job_templates/", payload)
            return json.dumps({
                "success": True,
                "id": data["id"],
                "name": data["name"],
                "tip": "Add workflow nodes via the AAP UI or aap_* node management tools.",
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class LaunchWorkflowInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        workflow_id: int = Field(..., ge=1, description="Workflow template ID to launch")
        extra_vars: Optional[str] = Field(default=None, description="Extra variables as JSON/YAML")
        limit: Optional[str] = Field(default=None, description="Host limit pattern")

    @mcp.tool(
        name="aap_launch_workflow",
        annotations={"title": "Launch Workflow", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_launch_workflow(params: LaunchWorkflowInput, ctx: Context) -> str:
        """Launch an AAP workflow template.

        Example: "Launch the Redis production workflow"

        Args:
            params (LaunchWorkflowInput):
                - workflow_id (int): Workflow template ID
                - extra_vars (Optional[str]): Variables to pass
                - limit (Optional[str]): Host limit

        Returns:
            str: JSON with workflow job id, status, and monitoring tip.
        """
        try:
            payload: Dict[str, Any] = {}
            if params.extra_vars:
                payload["extra_vars"] = params.extra_vars
            if params.limit:
                payload["limit"] = params.limit

            data = await aap_post(ctx, f"/workflow_job_templates/{params.workflow_id}/launch/", payload)
            wf_job_id = data.get("id")
            return json.dumps({
                "success": True,
                "workflow_job_id": wf_job_id,
                "status": data.get("status", "pending"),
                "monitor_tip": f"Use aap_get_workflow_status(workflow_job_id={wf_job_id}) to check progress.",
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetWorkflowStatusInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        workflow_job_id: int = Field(..., ge=1, description="Workflow job ID (from launch response)")

    @mcp.tool(
        name="aap_get_workflow_status",
        annotations={"title": "Get Workflow Status", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_workflow_status(params: GetWorkflowStatusInput, ctx: Context) -> str:
        """Get status of a running or completed workflow job including node results.

        Args:
            params (GetWorkflowStatusInput):
                - workflow_job_id (int): Workflow job ID

        Returns:
            str: JSON with workflow status, elapsed time, and per-node results.
        """
        try:
            data = await aap_get(ctx, f"/workflow_jobs/{params.workflow_job_id}/")
            nodes_data = await aap_get(ctx, f"/workflow_jobs/{params.workflow_job_id}/workflow_nodes/")

            nodes = []
            for n in nodes_data.get("results", []):
                sf = n.get("summary_fields", {})
                nodes.append({
                    "id": n["id"],
                    "job_template": sf.get("unified_job_template", {}).get("name"),
                    "job_id": sf.get("job", {}).get("id"),
                    "job_status": sf.get("job", {}).get("status"),
                    "do_not_run": n.get("do_not_run", False),
                })

            return json.dumps({
                "workflow_job_id": data["id"],
                "status": format_job_status(data),
                "started": data.get("started"),
                "finished": data.get("finished"),
                "elapsed": data.get("elapsed"),
                "workflow_template": data.get("summary_fields", {}).get("workflow_job_template", {}).get("name"),
                "nodes": nodes,
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteWFTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        workflow_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_workflow_template",
        annotations={"title": "Delete Workflow Template", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_workflow_template(params: DeleteWFTInput, ctx: Context) -> str:
        """Delete an AAP workflow template. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteWFTInput):
                - workflow_id (int): Workflow template ID
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation prompt or success JSON.
        """
        op_id = f"delete_wft_{params.workflow_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            try:
                wf = await aap_get(ctx, f"/workflow_job_templates/{params.workflow_id}/")
                name = wf.get("name", f"ID {params.workflow_id}")
            except AAPAPIError:
                name = f"ID {params.workflow_id}"
            return require_confirmation_token(op_id, f"Delete workflow template '{name}'")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."

        try:
            await aap_delete(ctx, f"/workflow_job_templates/{params.workflow_id}/")
            return json.dumps({"success": True, "deleted_workflow_id": params.workflow_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── UPDATE WORKFLOW TEMPLATE ─────────────────────────────────────────────

    class UpdateWFTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        workflow_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1, max_length=512)
        description: Optional[str] = Field(default=None)
        extra_vars: Optional[str] = Field(default=None)
        ask_variables_on_launch: Optional[bool] = Field(default=None)

    @mcp.tool(
        name="aap_update_workflow_template",
        annotations={"title": "Update Workflow Template", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_workflow_template(params: UpdateWFTInput, ctx: Context) -> str:
        """Update an existing AAP workflow template (PATCH).

        Args:
            params (UpdateWFTInput): Fields to update.

        Returns:
            str: JSON with updated workflow id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "extra_vars": params.extra_vars,
                "ask_variables_on_launch": params.ask_variables_on_launch,
            }.items() if v is not None}
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/workflow_job_templates/{params.workflow_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
