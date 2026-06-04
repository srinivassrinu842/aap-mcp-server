"""
Schedule Management, Execution Environment, and Automation Hub Tools.

AAP API Mapping:
  list_schedules          GET    /api/v2/schedules/
  create_schedule         POST   /api/v2/schedules/
  update_schedule         PATCH  /api/v2/schedules/{id}/
  delete_schedule         DELETE /api/v2/schedules/{id}/
  list_execution_envs     GET    /api/v2/execution_environments/
  create_execution_env    POST   /api/v2/execution_environments/
  update_execution_env    PATCH  /api/v2/execution_environments/{id}/
  delete_execution_env    DELETE /api/v2/execution_environments/{id}/
  list_collections        GET    /api/v2/collections/ (Hub API)
  sync_collections        POST   /api/v2/collection_imports/
"""

import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from ..utils.api_client import (
    AAPAPIError,
    aap_delete,
    aap_get,
    aap_patch,
    aap_post,
    paginate_params,
    require_confirmation_token,
    validate_confirmation_token,
)


def register_schedules(mcp: FastMCP):

    class ListSchedulesInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: str | None = Field(default=None)
        enabled: bool | None = Field(default=None)

    @mcp.tool(
        name="aap_list_schedules",
        annotations={"title": "List Schedules", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_schedules(params: ListSchedulesInput, ctx: Context) -> str:
        """List AAP schedules for jobs and workflows.

        Args:
            params (ListSchedulesInput): Pagination and filter options.

        Returns:
            str: JSON with schedule list including rrule, next_run, and linked template.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            if params.enabled is not None:
                q["enabled"] = params.enabled

            data = await aap_get(ctx, "/schedules/", params=q)
            return json.dumps(
                {
                    "count": data.get("count", 0),
                    "results": [
                        {
                            "id": s["id"],
                            "name": s["name"],
                            "enabled": s.get("enabled", True),
                            "rrule": s.get("rrule", ""),
                            "next_run": s.get("next_run"),
                            "dtstart": s.get("dtstart"),
                            "unified_job_template": s.get("summary_fields", {})
                            .get("unified_job_template", {})
                            .get("name"),
                            "template_type": s.get("summary_fields", {})
                            .get("unified_job_template", {})
                            .get("unified_job_type"),
                        }
                        for s in data.get("results", [])
                    ],
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateScheduleInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, description="Schedule name")
        unified_job_template_id: int = Field(..., ge=1, description="Job template or workflow template ID to schedule")
        rrule: str = Field(
            ..., description="RFC 5545 RRULE string. E.g.: 'DTSTART:20240101T020000Z RRULE:FREQ=DAILY;INTERVAL=1'"
        )
        description: str = Field(default="")
        enabled: bool = Field(default=True)
        extra_vars: str = Field(default="", description="Extra variables to pass at scheduled launch")

    @mcp.tool(
        name="aap_create_schedule",
        annotations={"title": "Create Schedule", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_schedule(params: CreateScheduleInput, ctx: Context) -> str:
        """Create a schedule for an AAP job template or workflow.

        Args:
            params (CreateScheduleInput):
                - name (str): Schedule name
                - unified_job_template_id (int): Template ID to schedule
                - rrule (str): RFC 5545 recurrence rule string
                - enabled (bool): Activate the schedule immediately
                - extra_vars (str): Variables for each scheduled run

        Returns:
            str: JSON with created schedule id, name, and next_run.
        """
        try:
            payload = {
                "name": params.name,
                "description": params.description,
                "unified_job_template": params.unified_job_template_id,
                "rrule": params.rrule,
                "enabled": params.enabled,
                "extra_data": params.extra_vars or "{}",
            }
            data = await aap_post(ctx, "/schedules/", payload)
            return json.dumps(
                {
                    "success": True,
                    "id": data["id"],
                    "name": data["name"],
                    "next_run": data.get("next_run"),
                    "enabled": data.get("enabled"),
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateScheduleInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        schedule_id: int = Field(..., ge=1)
        name: str | None = Field(default=None)
        rrule: str | None = Field(default=None)
        enabled: bool | None = Field(default=None)
        extra_vars: str | None = Field(default=None)

    @mcp.tool(
        name="aap_update_schedule",
        annotations={"title": "Update Schedule", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_schedule(params: UpdateScheduleInput, ctx: Context) -> str:
        """Update an existing AAP schedule (PATCH).

        Args:
            params (UpdateScheduleInput): Fields to update.

        Returns:
            str: JSON with updated schedule id, name, next_run.
        """
        try:
            payload = {
                k: v
                for k, v in {
                    "name": params.name,
                    "rrule": params.rrule,
                    "enabled": params.enabled,
                    "extra_data": params.extra_vars,
                }.items()
                if v is not None
            }
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/schedules/{params.schedule_id}/", payload)
            return json.dumps(
                {
                    "success": True,
                    "id": data["id"],
                    "name": data["name"],
                    "next_run": data.get("next_run"),
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteScheduleInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        schedule_id: int = Field(..., ge=1)
        confirmation_token: str | None = Field(default=None)

    @mcp.tool(
        name="aap_delete_schedule",
        annotations={"title": "Delete Schedule", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_schedule(params: DeleteScheduleInput, ctx: Context) -> str:
        """Delete an AAP schedule. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteScheduleInput):
                - schedule_id (int): Schedule ID
                - confirmation_token (Optional[str]): Token from first call
        """
        op_id = f"delete_schedule_{params.schedule_id}"
        settings = ctx.request_context.lifespan_context["settings"]
        if settings.require_confirmation and not params.confirmation_token:
            try:
                s = await aap_get(ctx, f"/schedules/{params.schedule_id}/")
                name = s.get("name", f"ID {params.schedule_id}")
            except AAPAPIError:
                name = f"ID {params.schedule_id}"
            return require_confirmation_token(op_id, f"Delete schedule '{name}'")
        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."
        try:
            await aap_delete(ctx, f"/schedules/{params.schedule_id}/")
            return json.dumps({"success": True, "deleted_schedule_id": params.schedule_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"


def register_execution_environments(mcp: FastMCP):

    class ListEEInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: str | None = Field(default=None)

    @mcp.tool(
        name="aap_list_execution_environments",
        annotations={"title": "List Execution Environments", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_execution_environments(params: ListEEInput, ctx: Context) -> str:
        """List AAP execution environments (container images for job execution).

        Returns:
            str: JSON with EE list including id, name, image, and managed status.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            data = await aap_get(ctx, "/execution_environments/", params=q)
            return json.dumps(
                {
                    "count": data.get("count", 0),
                    "results": [
                        {
                            "id": ee["id"],
                            "name": ee["name"],
                            "description": ee.get("description", ""),
                            "image": ee.get("image", ""),
                            "managed": ee.get("managed", False),
                            "pull": ee.get("pull", "missing"),
                            "organization": ee.get("summary_fields", {}).get("organization", {}).get("name"),
                        }
                        for ee in data.get("results", [])
                    ],
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateEEInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, description="Execution environment name")
        image: str = Field(
            ..., min_length=1, description="Container image URI (e.g., 'quay.io/ansible/ee-supported-rhel8:latest')"
        )
        description: str = Field(default="")
        pull: str = Field(default="missing", description="Image pull policy: 'always', 'missing', or 'never'")
        organization_id: int | None = Field(default=None, ge=1)
        credential_id: int | None = Field(default=None, ge=1, description="Registry credential ID for private images")

    @mcp.tool(
        name="aap_create_execution_environment",
        annotations={"title": "Create Execution Environment", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_execution_environment(params: CreateEEInput, ctx: Context) -> str:
        """Create an AAP execution environment referencing a container image.

        Args:
            params (CreateEEInput): EE configuration.

        Returns:
            str: JSON with created EE id and name.
        """
        try:
            payload: dict[str, Any] = {
                "name": params.name,
                "description": params.description,
                "image": params.image,
                "pull": params.pull,
            }
            if params.organization_id:
                payload["organization"] = params.organization_id
            if params.credential_id:
                payload["credential"] = params.credential_id

            data = await aap_post(ctx, "/execution_environments/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateEEInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        ee_id: int = Field(..., ge=1)
        name: str | None = Field(default=None)
        image: str | None = Field(default=None)
        pull: str | None = Field(default=None)
        description: str | None = Field(default=None)

    @mcp.tool(
        name="aap_update_execution_environment",
        annotations={"title": "Update Execution Environment", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_execution_environment(params: UpdateEEInput, ctx: Context) -> str:
        """Update an existing AAP execution environment (PATCH).

        Args:
            params (UpdateEEInput): Fields to update.
        """
        try:
            payload = {
                k: v
                for k, v in {
                    "name": params.name,
                    "image": params.image,
                    "pull": params.pull,
                    "description": params.description,
                }.items()
                if v is not None
            }
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/execution_environments/{params.ee_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteEEInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        ee_id: int = Field(..., ge=1)
        confirmation_token: str | None = Field(default=None)

    @mcp.tool(
        name="aap_delete_execution_environment",
        annotations={"title": "Delete Execution Environment", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_execution_environment(params: DeleteEEInput, ctx: Context) -> str:
        """Delete an AAP execution environment. DESTRUCTIVE - requires confirmation."""
        op_id = f"delete_ee_{params.ee_id}"
        settings = ctx.request_context.lifespan_context["settings"]
        if settings.require_confirmation and not params.confirmation_token:
            try:
                ee = await aap_get(ctx, f"/execution_environments/{params.ee_id}/")
                name = ee.get("name", f"ID {params.ee_id}")
            except AAPAPIError:
                name = f"ID {params.ee_id}"
            return require_confirmation_token(op_id, f"Delete execution environment '{name}'")
        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."
        try:
            await aap_delete(ctx, f"/execution_environments/{params.ee_id}/")
            return json.dumps({"success": True, "deleted_ee_id": params.ee_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"


def register_automation_hub(mcp: FastMCP):

    class ListCollectionsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        namespace: str | None = Field(
            default=None, description="Filter by collection namespace (e.g., 'ansible', 'community')"
        )
        search: str | None = Field(default=None)

    @mcp.tool(
        name="aap_list_collections",
        annotations={"title": "List Automation Hub Collections", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_collections(params: ListCollectionsInput, ctx: Context) -> str:
        """List Ansible collections in Automation Hub.

        Note: Requires Automation Hub API access at /api/automation-hub/v3/

        Args:
            params (ListCollectionsInput): Pagination and filter.

        Returns:
            str: JSON with collection list.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.namespace:
                q["namespace"] = params.namespace
            if params.search:
                q["keywords"] = params.search

            # Automation Hub uses a different API path
            client = ctx.request_context.lifespan_context["http_client"]
            response = await client.get("/api/automation-hub/v3/collections/", params=q)
            if response.status_code == 404:
                return json.dumps(
                    {
                        "note": "Automation Hub API not available at this URL. Collections endpoint requires /api/automation-hub/v3/",
                        "tip": "Check that your AAP_CONTROLLER_URL points to a deployment with Automation Hub enabled.",
                    },
                    indent=2,
                )
            response.raise_for_status()
            data = response.json()
            return json.dumps(
                {
                    "count": data.get("meta", {}).get("count", 0),
                    "results": [
                        {
                            "namespace": c.get("namespace", {}).get("name"),
                            "name": c.get("name"),
                            "latest_version": c.get("latest_version", {}).get("version"),
                            "download_count": c.get("download_count", 0),
                            "deprecated": c.get("deprecated", False),
                        }
                        for c in data.get("data", [])
                    ],
                },
                indent=2,
            )
        except Exception as e:
            return f"Error accessing Automation Hub: {e}"


# Module-level register function that composes all sub-registrations
def register(mcp: FastMCP):
    """Register all schedule, EE, and hub tools."""
    register_schedules(mcp)
    register_execution_environments(mcp)
    register_automation_hub(mcp)
