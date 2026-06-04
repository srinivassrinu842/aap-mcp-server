"""
Project Management Tools for AAP MCP Server.

AAP API Mapping:
  list_projects          GET    /api/v2/projects/
  get_project            GET    /api/v2/projects/{id}/
  create_project         POST   /api/v2/projects/
  update_project         PATCH  /api/v2/projects/{id}/
  delete_project         DELETE /api/v2/projects/{id}/
  sync_project           POST   /api/v2/projects/{id}/update/
  get_project_sync_status GET   /api/v2/project_updates/{id}/
"""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from ..utils.api_client import (
    aap_get, aap_post, aap_patch, aap_delete,
    AAPAPIError, require_confirmation_token, validate_confirmation_token,
    paginate_params,
)


SCM_TYPE_CHOICES = ["git", "svn", "insights", "archive", ""]


def register(mcp: FastMCP):

    class ListProjectsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: Optional[str] = Field(default=None, description="Filter by name substring")
        scm_type: Optional[str] = Field(default=None, description="Filter: 'git', 'svn', 'archive'")

    @mcp.tool(
        name="aap_list_projects",
        annotations={"title": "List Projects", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_projects(params: ListProjectsInput, ctx: Context) -> str:
        """List AAP projects (SCM-backed playbook repositories).

        Args:
            params (ListProjectsInput): Pagination and filter options.

        Returns:
            str: JSON with count and project list. Each entry has id, name,
                 scm_type, scm_url, status, last_updated.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            if params.scm_type:
                q["scm_type"] = params.scm_type

            data = await aap_get(ctx, "/projects/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "results": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "description": p.get("description", ""),
                        "scm_type": p.get("scm_type", ""),
                        "scm_url": p.get("scm_url", ""),
                        "scm_branch": p.get("scm_branch", ""),
                        "status": p.get("status", ""),
                        "last_updated": p.get("last_updated"),
                    }
                    for p in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetProjectInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        project_id: int = Field(..., ge=1, description="Project ID")

    @mcp.tool(
        name="aap_get_project",
        annotations={"title": "Get Project", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_project(params: GetProjectInput, ctx: Context) -> str:
        """Get full details of an AAP project.

        Args:
            params (GetProjectInput):
                - project_id (int): Project ID

        Returns:
            str: JSON with full project details.
        """
        try:
            data = await aap_get(ctx, f"/projects/{params.project_id}/")
            return json.dumps({
                "id": data["id"],
                "name": data["name"],
                "description": data.get("description", ""),
                "scm_type": data.get("scm_type"),
                "scm_url": data.get("scm_url"),
                "scm_branch": data.get("scm_branch"),
                "scm_refspec": data.get("scm_refspec"),
                "scm_clean": data.get("scm_clean"),
                "scm_delete_on_update": data.get("scm_delete_on_update"),
                "status": data.get("status"),
                "last_updated": data.get("last_updated"),
                "last_update_failed": data.get("last_update_failed"),
                "organization": data.get("summary_fields", {}).get("organization", {}),
                "credential": data.get("summary_fields", {}).get("credential", {}),
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateProjectInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512, description="Project name (e.g., 'redis-automation')")
        scm_type: str = Field(..., description="SCM type: 'git', 'svn', 'archive', or '' for manual")
        scm_url: Optional[str] = Field(default=None, description="Repository URL (e.g., 'https://github.com/org/repo')")
        scm_branch: str = Field(default="", description="Branch, tag, or commit hash (default: repo default)")
        organization_id: Optional[int] = Field(default=None, ge=1, description="Organization ID")
        credential_id: Optional[int] = Field(default=None, ge=1, description="SCM credential ID for private repos")
        description: str = Field(default="")
        scm_clean: bool = Field(default=False, description="Remove local modifications before update")
        scm_delete_on_update: bool = Field(default=False, description="Delete and re-clone on every update")
        update_on_launch: bool = Field(default=True, description="Automatically sync before running jobs")

    @mcp.tool(
        name="aap_create_project",
        annotations={"title": "Create Project", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_project(params: CreateProjectInput, ctx: Context) -> str:
        """Create a new AAP project from a Git/SCM repository.

        Example: "Create a new project called redis-automation from GitHub"

        Args:
            params (CreateProjectInput): Project configuration.

        Returns:
            str: JSON with created project id, name, and initial status.
        """
        try:
            payload = {
                "name": params.name,
                "description": params.description,
                "scm_type": params.scm_type,
                "scm_branch": params.scm_branch,
                "scm_clean": params.scm_clean,
                "scm_delete_on_update": params.scm_delete_on_update,
                "update_on_launch": params.update_on_launch,
            }
            if params.scm_url:
                payload["scm_url"] = params.scm_url
            if params.organization_id:
                payload["organization"] = params.organization_id
            if params.credential_id:
                payload["credential"] = params.credential_id

            data = await aap_post(ctx, "/projects/", payload)
            return json.dumps({
                "success": True,
                "id": data["id"],
                "name": data["name"],
                "status": data.get("status"),
                "sync_tip": f"Use aap_sync_project(project_id={data['id']}) to trigger an initial sync.",
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class SyncProjectInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        project_id: int = Field(..., ge=1, description="Project ID to sync")

    @mcp.tool(
        name="aap_sync_project",
        annotations={"title": "Sync Project", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_sync_project(params: SyncProjectInput, ctx: Context) -> str:
        """Trigger an SCM sync (git pull) for an AAP project.

        Args:
            params (SyncProjectInput):
                - project_id (int): Project ID to sync

        Returns:
            str: JSON with project_update_id for status tracking.
        """
        try:
            data = await aap_post(ctx, f"/projects/{params.project_id}/update/", {})
            update_id = data.get("id") if isinstance(data, dict) else None
            return json.dumps({
                "success": True,
                "project_id": params.project_id,
                "project_update_id": update_id,
                "tip": f"Use aap_get_project_sync_status(update_id=<id>) to check progress.",
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetSyncStatusInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        update_id: int = Field(..., ge=1, description="Project update ID from sync_project response")

    @mcp.tool(
        name="aap_get_project_sync_status",
        annotations={"title": "Get Project Sync Status", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_project_sync_status(params: GetSyncStatusInput, ctx: Context) -> str:
        """Get the status of an ongoing or completed project SCM sync.

        Args:
            params (GetSyncStatusInput):
                - update_id (int): Project update ID

        Returns:
            str: JSON with status, elapsed time, and output preview.
        """
        try:
            data = await aap_get(ctx, f"/project_updates/{params.update_id}/")
            return json.dumps({
                "update_id": data["id"],
                "project_id": data.get("project"),
                "status": data.get("status"),
                "started": data.get("started"),
                "finished": data.get("finished"),
                "elapsed": data.get("elapsed"),
                "failed": data.get("failed", False),
                "result_stdout_preview": str(data.get("result_stdout", ""))[:1000],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteProjectInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        project_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_project",
        annotations={"title": "Delete Project", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_project(params: DeleteProjectInput, ctx: Context) -> str:
        """Delete an AAP project. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteProjectInput):
                - project_id (int): Project ID
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation prompt or success JSON.
        """
        op_id = f"delete_project_{params.project_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            try:
                proj = await aap_get(ctx, f"/projects/{params.project_id}/")
                name = proj.get("name", f"ID {params.project_id}")
            except AAPAPIError:
                name = f"ID {params.project_id}"
            return require_confirmation_token(op_id, f"Delete project '{name}'")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."

        try:
            await aap_delete(ctx, f"/projects/{params.project_id}/")
            return json.dumps({"success": True, "deleted_project_id": params.project_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateProjectInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        project_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1)
        description: Optional[str] = Field(default=None)
        scm_url: Optional[str] = Field(default=None)
        scm_branch: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_update_project",
        annotations={"title": "Update Project", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_project(params: UpdateProjectInput, ctx: Context) -> str:
        """Update an AAP project (PATCH).

        Args:
            params (UpdateProjectInput): Fields to update.

        Returns:
            str: JSON with updated project id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "scm_url": params.scm_url,
                "scm_branch": params.scm_branch,
            }.items() if v is not None}

            if not payload:
                return "Error: No fields provided to update."

            data = await aap_patch(ctx, f"/projects/{params.project_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
