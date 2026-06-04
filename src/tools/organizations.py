"""
Organization Management Tools for AAP MCP Server.

AAP API Mapping:
  list_organizations      GET  /api/v2/organizations/
  get_organization        GET  /api/v2/organizations/{id}/
  create_organization     POST /api/v2/organizations/
  update_organization     PATCH /api/v2/organizations/{id}/
  delete_organization     DELETE /api/v2/organizations/{id}/
"""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from ..utils.api_client import (
    aap_get, aap_post, aap_patch, aap_delete, aap_list_all,
    AAPAPIError, require_confirmation_token, validate_confirmation_token,
    paginate_params,
)


def register(mcp: FastMCP):
    """Register all organization tools with the MCP server."""

    class ListOrgsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1, description="Page number")
        page_size: int = Field(default=20, ge=1, le=200, description="Results per page")
        search: Optional[str] = Field(default=None, description="Filter by name (substring match)")

    @mcp.tool(
        name="aap_list_organizations",
        annotations={
            "title": "List AAP Organizations",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def aap_list_organizations(params: ListOrgsInput, ctx: Context) -> str:
        """List all organizations in Ansible Automation Platform.

        Returns a paginated list of organizations with their IDs, names,
        descriptions, and member counts.

        Args:
            params (ListOrgsInput):
                - page (int): Page number, default 1
                - page_size (int): Results per page, default 20
                - search (Optional[str]): Filter by name substring

        Returns:
            str: JSON with keys: count, page, page_size, results (list of orgs)
        """
        try:
            query = {**paginate_params(params.page, params.page_size)}
            if params.search:
                query["name__icontains"] = params.search
            data = await aap_get(ctx, "/organizations/", params=query)
            return json.dumps({
                "count": data.get("count", 0),
                "page": params.page,
                "page_size": params.page_size,
                "results": [
                    {
                        "id": o["id"],
                        "name": o["name"],
                        "description": o.get("description", ""),
                        "max_hosts": o.get("max_hosts", 0),
                    }
                    for o in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetOrgInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        org_id: int = Field(..., ge=1, description="Organization ID (e.g., 1)")

    @mcp.tool(
        name="aap_get_organization",
        annotations={
            "title": "Get AAP Organization",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def aap_get_organization(params: GetOrgInput, ctx: Context) -> str:
        """Get details of a specific AAP organization by ID.

        Args:
            params (GetOrgInput):
                - org_id (int): Organization ID

        Returns:
            str: JSON with organization details including id, name, description,
                 max_hosts, custom_virtualenv, created, modified.
        """
        try:
            data = await aap_get(ctx, f"/organizations/{params.org_id}/")
            return json.dumps({
                "id": data["id"],
                "name": data["name"],
                "description": data.get("description", ""),
                "max_hosts": data.get("max_hosts", 0),
                "custom_virtualenv": data.get("custom_virtualenv"),
                "created": data.get("created"),
                "modified": data.get("modified"),
                "summary_fields": data.get("summary_fields", {}),
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateOrgInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512, description="Organization name (e.g., 'Production')")
        description: str = Field(default="", description="Human-readable description")
        max_hosts: int = Field(default=0, ge=0, description="Max hosts allowed (0 = unlimited)")

    @mcp.tool(
        name="aap_create_organization",
        annotations={
            "title": "Create AAP Organization",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def aap_create_organization(params: CreateOrgInput, ctx: Context) -> str:
        """Create a new organization in Ansible Automation Platform.

        Args:
            params (CreateOrgInput):
                - name (str): Organization name
                - description (str): Optional description
                - max_hosts (int): Max hosts (0 = unlimited)

        Returns:
            str: JSON with created organization details including id.
        """
        try:
            data = await aap_post(ctx, "/organizations/", {
                "name": params.name,
                "description": params.description,
                "max_hosts": params.max_hosts,
            })
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateOrgInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        org_id: int = Field(..., ge=1, description="Organization ID to update")
        name: Optional[str] = Field(default=None, min_length=1, max_length=512)
        description: Optional[str] = Field(default=None)
        max_hosts: Optional[int] = Field(default=None, ge=0)

    @mcp.tool(
        name="aap_update_organization",
        annotations={
            "title": "Update AAP Organization",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def aap_update_organization(params: UpdateOrgInput, ctx: Context) -> str:
        """Update an existing AAP organization.

        Only fields provided will be updated (PATCH semantics).

        Args:
            params (UpdateOrgInput):
                - org_id (int): Organization ID
                - name (Optional[str]): New name
                - description (Optional[str]): New description
                - max_hosts (Optional[int]): New max hosts limit

        Returns:
            str: JSON with updated organization details.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "max_hosts": params.max_hosts,
            }.items() if v is not None}

            if not payload:
                return "Error: No fields to update. Provide at least one of: name, description, max_hosts."

            data = await aap_patch(ctx, f"/organizations/{params.org_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteOrgInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        org_id: int = Field(..., ge=1, description="Organization ID to delete")
        confirmation_token: Optional[str] = Field(
            default=None,
            description="Confirmation token from previous call. Required to execute deletion."
        )

    @mcp.tool(
        name="aap_delete_organization",
        annotations={
            "title": "Delete AAP Organization",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def aap_delete_organization(params: DeleteOrgInput, ctx: Context) -> str:
        """Delete an AAP organization. DESTRUCTIVE - requires confirmation token.

        Call once without confirmation_token to get a token, then call again
        with the token to confirm deletion.

        Args:
            params (DeleteOrgInput):
                - org_id (int): Organization ID
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation request message, or success/error JSON.
        """
        op_id = f"delete_org_{params.org_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            # Fetch org name for informative message
            try:
                org = await aap_get(ctx, f"/organizations/{params.org_id}/")
                name = org.get("name", f"ID {params.org_id}")
            except AAPAPIError:
                name = f"ID {params.org_id}"
            return require_confirmation_token(op_id, f"Delete organization '{name}' (ID: {params.org_id}) and ALL its resources")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token. Call without token to get a new one."

        try:
            await aap_delete(ctx, f"/organizations/{params.org_id}/")
            return json.dumps({"success": True, "deleted_org_id": params.org_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
