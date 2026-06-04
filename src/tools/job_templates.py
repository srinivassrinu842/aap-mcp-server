"""
Job Template Management Tools for AAP MCP Server.

AAP API Mapping:
  list_job_templates      GET    /api/v2/job_templates/
  get_job_template        GET    /api/v2/job_templates/{id}/
  create_job_template     POST   /api/v2/job_templates/
  update_job_template     PATCH  /api/v2/job_templates/{id}/
  delete_job_template     DELETE /api/v2/job_templates/{id}/
  copy_job_template       POST   /api/v2/job_templates/{id}/copy/
  launch_job_template     POST   /api/v2/job_templates/{id}/launch/
  relaunch_job            POST   /api/v2/jobs/{id}/relaunch/
  cancel_job              POST   /api/v2/jobs/{id}/cancel/
  get_job_status          GET    /api/v2/jobs/{id}/
"""

import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from ..utils.api_client import (
    aap_get, aap_post, aap_patch, aap_delete, aap_list_all,
    AAPAPIError, require_confirmation_token, validate_confirmation_token,
    format_job_status, paginate_params,
)


def register(mcp: FastMCP):

    class ListJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: Optional[str] = Field(default=None, description="Filter by name substring")
        organization: Optional[int] = Field(default=None, description="Filter by organization ID")
        project: Optional[int] = Field(default=None, description="Filter by project ID")

    @mcp.tool(
        name="aap_list_job_templates",
        annotations={"title": "List Job Templates", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_job_templates(params: ListJTInput, ctx: Context) -> str:
        """List AAP job templates with optional filtering.

        Args:
            params (ListJTInput):
                - page (int): Page number
                - page_size (int): Results per page
                - search (Optional[str]): Name substring filter
                - organization (Optional[int]): Filter by org ID
                - project (Optional[int]): Filter by project ID

        Returns:
            str: JSON with count and results list. Each result has:
                id, name, description, project, inventory, playbook,
                ask_variables_on_launch, last_job_status, last_job_run
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            if params.organization:
                q["organization"] = params.organization
            if params.project:
                q["project"] = params.project

            data = await aap_get(ctx, "/job_templates/", params=q)
            results = []
            for jt in data.get("results", []):
                sf = jt.get("summary_fields", {})
                results.append({
                    "id": jt["id"],
                    "name": jt["name"],
                    "description": jt.get("description", ""),
                    "playbook": jt.get("playbook", ""),
                    "project": sf.get("project", {}).get("name"),
                    "inventory": sf.get("inventory", {}).get("name"),
                    "ask_variables_on_launch": jt.get("ask_variables_on_launch", False),
                    "last_job_status": sf.get("recent_jobs", [{}])[0].get("status") if sf.get("recent_jobs") else None,
                })
            return json.dumps({"count": data.get("count", 0), "results": results}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        template_id: int = Field(..., ge=1, description="Job template ID")

    @mcp.tool(
        name="aap_get_job_template",
        annotations={"title": "Get Job Template", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_job_template(params: GetJTInput, ctx: Context) -> str:
        """Get full details of an AAP job template.

        Args:
            params (GetJTInput):
                - template_id (int): Job template ID

        Returns:
            str: JSON with full template details including credentials, labels,
                 survey spec, extra_vars, verbosity, become_enabled, etc.
        """
        try:
            data = await aap_get(ctx, f"/job_templates/{params.template_id}/")
            sf = data.get("summary_fields", {})
            return json.dumps({
                "id": data["id"],
                "name": data["name"],
                "description": data.get("description", ""),
                "job_type": data.get("job_type", "run"),
                "playbook": data.get("playbook", ""),
                "project": sf.get("project", {}),
                "inventory": sf.get("inventory", {}),
                "credentials": sf.get("credentials", []),
                "extra_vars": data.get("extra_vars", ""),
                "verbosity": data.get("verbosity", 0),
                "ask_variables_on_launch": data.get("ask_variables_on_launch", False),
                "ask_inventory_on_launch": data.get("ask_inventory_on_launch", False),
                "ask_credential_on_launch": data.get("ask_credential_on_launch", False),
                "become_enabled": data.get("become_enabled", False),
                "diff_mode": data.get("diff_mode", False),
                "survey_enabled": data.get("survey_enabled", False),
                "created": data.get("created"),
                "modified": data.get("modified"),
                "related": {
                    "launch": f"/api/v2/job_templates/{data['id']}/launch/",
                    "jobs": f"/api/v2/job_templates/{data['id']}/jobs/",
                    "schedules": f"/api/v2/job_templates/{data['id']}/schedules/",
                },
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512, description="Template name (e.g., 'Install Apache')")
        project_id: int = Field(..., ge=1, description="Project ID containing the playbook")
        playbook: str = Field(..., min_length=1, description="Playbook path relative to project root (e.g., 'site.yml')")
        inventory_id: Optional[int] = Field(default=None, ge=1, description="Inventory ID (can be asked at launch)")
        description: str = Field(default="", description="Optional description")
        job_type: str = Field(default="run", description="Job type: 'run' or 'check'")
        verbosity: int = Field(default=0, ge=0, le=5, description="Ansible verbosity (0=normal, 5=maximum)")
        extra_vars: str = Field(default="", description="Extra variables in YAML or JSON format")
        become_enabled: bool = Field(default=False, description="Enable privilege escalation")
        ask_variables_on_launch: bool = Field(default=False)
        ask_inventory_on_launch: bool = Field(default=False)
        ask_credential_on_launch: bool = Field(default=False)
        credential_ids: Optional[List[int]] = Field(default=None, description="List of credential IDs to attach")

    @mcp.tool(
        name="aap_create_job_template",
        annotations={"title": "Create Job Template", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_job_template(params: CreateJTInput, ctx: Context) -> str:
        """Create a new AAP job template.

        Example: Create a job template for Apache installation using a project
        and inventory, with become enabled and check mode disabled.

        Args:
            params (CreateJTInput): Template configuration. See field descriptions.

        Returns:
            str: JSON with created template id, name, and launch URL.
        """
        try:
            payload: Dict[str, Any] = {
                "name": params.name,
                "description": params.description,
                "job_type": params.job_type,
                "project": params.project_id,
                "playbook": params.playbook,
                "verbosity": params.verbosity,
                "extra_vars": params.extra_vars,
                "become_enabled": params.become_enabled,
                "ask_variables_on_launch": params.ask_variables_on_launch,
                "ask_inventory_on_launch": params.ask_inventory_on_launch,
                "ask_credential_on_launch": params.ask_credential_on_launch,
            }
            if params.inventory_id:
                payload["inventory"] = params.inventory_id

            data = await aap_post(ctx, "/job_templates/", payload)
            jt_id = data["id"]

            # Attach credentials if provided
            if params.credential_ids:
                for cred_id in params.credential_ids:
                    try:
                        await aap_post(ctx, f"/job_templates/{jt_id}/credentials/", {"id": cred_id})
                    except AAPAPIError as ce:
                        pass  # Non-fatal; report in response

            return json.dumps({
                "success": True,
                "id": jt_id,
                "name": data["name"],
                "launch_url": f"/api/v2/job_templates/{jt_id}/launch/",
                "credentials_attached": params.credential_ids or [],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class LaunchJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        template_id: int = Field(..., ge=1, description="Job template ID to launch")
        extra_vars: Optional[str] = Field(
            default=None,
            description="Extra variables as JSON or YAML string to pass at launch"
        )
        inventory_id: Optional[int] = Field(default=None, ge=1, description="Override inventory ID at launch")
        credential_id: Optional[int] = Field(default=None, ge=1, description="Override credential at launch")
        limit: Optional[str] = Field(default=None, description="Host limit pattern (e.g., 'web01.example.com')")
        tags: Optional[str] = Field(default=None, description="Ansible tags to run (comma-separated)")
        skip_tags: Optional[str] = Field(default=None, description="Ansible tags to skip")
        verbosity: Optional[int] = Field(default=None, ge=0, le=5, description="Override verbosity level")
        diff_mode: Optional[bool] = Field(default=None, description="Enable diff mode for this run")

    @mcp.tool(
        name="aap_launch_job_template",
        annotations={
            "title": "Launch Job Template",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    )
    async def aap_launch_job_template(params: LaunchJTInput, ctx: Context) -> str:
        """Launch an AAP job template and return the job ID.

        Example: "Launch the Redis production workflow" or
        "Run the Apache installation template on web01.example.com"

        Args:
            params (LaunchJTInput):
                - template_id (int): Job template ID
                - extra_vars (Optional[str]): Variables as JSON/YAML
                - inventory_id (Optional[int]): Override inventory
                - limit (Optional[str]): Host limit pattern
                - tags (Optional[str]): Ansible tags
                - skip_tags (Optional[str]): Tags to skip
                - verbosity (Optional[int]): Verbosity level
                - diff_mode (Optional[bool]): Show diffs

        Returns:
            str: JSON with job id, status, url, and monitoring instructions.
        """
        try:
            payload: Dict[str, Any] = {}
            if params.extra_vars:
                payload["extra_vars"] = params.extra_vars
            if params.inventory_id:
                payload["inventory"] = params.inventory_id
            if params.credential_id:
                payload["credentials"] = [params.credential_id]
            if params.limit:
                payload["limit"] = params.limit
            if params.tags:
                payload["job_tags"] = params.tags
            if params.skip_tags:
                payload["skip_tags"] = params.skip_tags
            if params.verbosity is not None:
                payload["verbosity"] = params.verbosity
            if params.diff_mode is not None:
                payload["diff_mode"] = params.diff_mode

            data = await aap_post(ctx, f"/job_templates/{params.template_id}/launch/", payload)
            job_id = data.get("id")
            return json.dumps({
                "success": True,
                "job_id": job_id,
                "status": data.get("status", "pending"),
                "job_url": f"/api/v2/jobs/{job_id}/",
                "monitor_tip": f"Use aap_get_job_output(job_id={job_id}) to stream output or aap_list_running_jobs() to check status.",
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class RelaunchJobInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        job_id: int = Field(..., ge=1, description="Job ID to relaunch")
        hosts: str = Field(
            default="all",
            description="Which hosts to relaunch against: 'all' or 'failed'"
        )

    @mcp.tool(
        name="aap_relaunch_job",
        annotations={"title": "Relaunch Job", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_relaunch_job(params: RelaunchJobInput, ctx: Context) -> str:
        """Relaunch a completed or failed AAP job.

        Args:
            params (RelaunchJobInput):
                - job_id (int): Job ID to relaunch
                - hosts (str): 'all' or 'failed' (retry only failed hosts)

        Returns:
            str: JSON with new job_id and status.
        """
        try:
            data = await aap_post(ctx, f"/jobs/{params.job_id}/relaunch/", {"hosts": params.hosts})
            return json.dumps({
                "success": True,
                "new_job_id": data.get("id"),
                "status": data.get("status"),
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CancelJobInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        job_id: int = Field(..., ge=1, description="Running job ID to cancel")
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_cancel_job",
        annotations={"title": "Cancel Job", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_cancel_job(params: CancelJobInput, ctx: Context) -> str:
        """Cancel a running AAP job. Requires confirmation.

        Args:
            params (CancelJobInput):
                - job_id (int): Job ID to cancel
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation prompt or success JSON.
        """
        op_id = f"cancel_job_{params.job_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            return require_confirmation_token(op_id, f"Cancel running job ID {params.job_id}")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."

        try:
            await aap_post(ctx, f"/jobs/{params.job_id}/cancel/", {})
            return json.dumps({"success": True, "cancelled_job_id": params.job_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        template_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_job_template",
        annotations={"title": "Delete Job Template", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_job_template(params: DeleteJTInput, ctx: Context) -> str:
        """Delete an AAP job template. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteJTInput):
                - template_id (int): Template ID to delete
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation prompt or success JSON.
        """
        op_id = f"delete_jt_{params.template_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            try:
                jt = await aap_get(ctx, f"/job_templates/{params.template_id}/")
                name = jt.get("name", f"ID {params.template_id}")
            except AAPAPIError:
                name = f"ID {params.template_id}"
            return require_confirmation_token(op_id, f"Delete job template '{name}'")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."

        try:
            await aap_delete(ctx, f"/job_templates/{params.template_id}/")
            return json.dumps({"success": True, "deleted_template_id": params.template_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CopyJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        template_id: int = Field(..., ge=1, description="Source job template ID to copy")
        name: str = Field(..., min_length=1, description="Name for the new copy")

    @mcp.tool(
        name="aap_copy_job_template",
        annotations={"title": "Copy Job Template", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_copy_job_template(params: CopyJTInput, ctx: Context) -> str:
        """Copy an existing job template with a new name.

        Args:
            params (CopyJTInput):
                - template_id (int): Source template ID
                - name (str): Name for the copy

        Returns:
            str: JSON with new template id and name.
        """
        try:
            data = await aap_post(ctx, f"/job_templates/{params.template_id}/copy/", {"name": params.name})
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateJTInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        template_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1, max_length=512)
        description: Optional[str] = Field(default=None)
        playbook: Optional[str] = Field(default=None, min_length=1)
        inventory_id: Optional[int] = Field(default=None, ge=1)
        extra_vars: Optional[str] = Field(default=None)
        verbosity: Optional[int] = Field(default=None, ge=0, le=5)
        become_enabled: Optional[bool] = Field(default=None)

    @mcp.tool(
        name="aap_update_job_template",
        annotations={"title": "Update Job Template", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_job_template(params: UpdateJTInput, ctx: Context) -> str:
        """Update an existing AAP job template (PATCH).

        Only fields provided will be changed.

        Args:
            params (UpdateJTInput): Fields to update.

        Returns:
            str: JSON with updated template id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "playbook": params.playbook,
                "inventory": params.inventory_id,
                "extra_vars": params.extra_vars,
                "verbosity": params.verbosity,
                "become_enabled": params.become_enabled,
            }.items() if v is not None}

            if not payload:
                return "Error: No fields to update."

            data = await aap_patch(ctx, f"/job_templates/{params.template_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
