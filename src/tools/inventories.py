"""
Inventory Management Tools for AAP MCP Server.

AAP API Mapping:
  list_inventories        GET    /api/v2/inventories/
  create_inventory        POST   /api/v2/inventories/
  update_inventory        PATCH  /api/v2/inventories/{id}/
  delete_inventory        DELETE /api/v2/inventories/{id}/
  list_hosts              GET    /api/v2/inventories/{id}/hosts/ or /api/v2/hosts/
  create_host             POST   /api/v2/hosts/
  update_host             PATCH  /api/v2/hosts/{id}/
  delete_host             DELETE /api/v2/hosts/{id}/
  list_groups             GET    /api/v2/inventories/{id}/groups/
  create_group            POST   /api/v2/groups/
  update_group            PATCH  /api/v2/groups/{id}/
  delete_group            DELETE /api/v2/groups/{id}/
  add_host_to_group       POST   /api/v2/groups/{id}/hosts/
  remove_host_from_group  POST   /api/v2/groups/{id}/hosts/ (disassociate)
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


def register(mcp: FastMCP):

    class ListInventoriesInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: Optional[str] = Field(default=None)
        organization: Optional[int] = Field(default=None)

    @mcp.tool(
        name="aap_list_inventories",
        annotations={"title": "List Inventories", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_inventories(params: ListInventoriesInput, ctx: Context) -> str:
        """List AAP inventories.

        Args:
            params (ListInventoriesInput): Pagination and filter options.

        Returns:
            str: JSON with count and inventory list (id, name, description,
                 total_hosts, groups_with_active_failures).
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            if params.organization:
                q["organization"] = params.organization

            data = await aap_get(ctx, "/inventories/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "results": [
                    {
                        "id": inv["id"],
                        "name": inv["name"],
                        "description": inv.get("description", ""),
                        "kind": inv.get("kind", ""),
                        "total_hosts": inv.get("total_hosts", 0),
                        "hosts_with_active_failures": inv.get("hosts_with_active_failures", 0),
                        "organization": inv.get("summary_fields", {}).get("organization", {}).get("name"),
                    }
                    for inv in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateInventoryInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512, description="Inventory name (e.g., 'AWS-Production')")
        organization_id: int = Field(..., ge=1, description="Organization ID that owns this inventory")
        description: str = Field(default="")
        variables: str = Field(default="", description="Inventory-level variables as YAML or JSON string")
        kind: str = Field(default="", description="Inventory kind: '' (standard), 'smart', or 'constructed'")

    @mcp.tool(
        name="aap_create_inventory",
        annotations={"title": "Create Inventory", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_inventory(params: CreateInventoryInput, ctx: Context) -> str:
        """Create a new AAP inventory.

        Example: "Create an inventory called AWS-Production"

        Args:
            params (CreateInventoryInput): Inventory configuration.

        Returns:
            str: JSON with created inventory id and name.
        """
        try:
            data = await aap_post(ctx, "/inventories/", {
                "name": params.name,
                "description": params.description,
                "organization": params.organization_id,
                "variables": params.variables,
                "kind": params.kind,
            })
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ListHostsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        inventory_id: Optional[int] = Field(default=None, ge=1, description="Filter by inventory ID")
        search: Optional[str] = Field(default=None, description="Filter by hostname substring")
        enabled: Optional[bool] = Field(default=None, description="Filter by enabled status")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)

    @mcp.tool(
        name="aap_list_hosts",
        annotations={"title": "List Hosts", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_hosts(params: ListHostsInput, ctx: Context) -> str:
        """List hosts in an AAP inventory.

        Args:
            params (ListHostsInput): Pagination and filter options.

        Returns:
            str: JSON with host list including id, name, inventory, enabled, variables.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            if params.enabled is not None:
                q["enabled"] = params.enabled
            if params.inventory_id:
                q["inventory"] = params.inventory_id

            data = await aap_get(ctx, "/hosts/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "results": [
                    {
                        "id": h["id"],
                        "name": h["name"],
                        "description": h.get("description", ""),
                        "enabled": h.get("enabled", True),
                        "inventory": h.get("summary_fields", {}).get("inventory", {}).get("name"),
                        "variables": h.get("variables", ""),
                        "has_active_failures": h.get("has_active_failures", False),
                        "last_job": h.get("summary_fields", {}).get("recent_jobs", [{}])[0].get("status") if h.get("summary_fields", {}).get("recent_jobs") else None,
                    }
                    for h in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateHostInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, description="Hostname or IP (e.g., 'web01.example.com')")
        inventory_id: int = Field(..., ge=1, description="Inventory ID to add this host to")
        description: str = Field(default="")
        variables: str = Field(default="", description="Host variables as YAML or JSON string")
        enabled: bool = Field(default=True, description="Whether host is enabled for automation")

    @mcp.tool(
        name="aap_create_host",
        annotations={"title": "Create Host", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_host(params: CreateHostInput, ctx: Context) -> str:
        """Add a host to an AAP inventory.

        Example: "Add host web01.example.com to the Production inventory"

        Args:
            params (CreateHostInput): Host configuration.

        Returns:
            str: JSON with created host id and name.
        """
        try:
            data = await aap_post(ctx, "/hosts/", {
                "name": params.name,
                "description": params.description,
                "inventory": params.inventory_id,
                "variables": params.variables,
                "enabled": params.enabled,
            })
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateGroupInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, description="Group name (e.g., 'web_servers')")
        inventory_id: int = Field(..., ge=1, description="Inventory ID")
        description: str = Field(default="")
        variables: str = Field(default="", description="Group variables as YAML or JSON")

    @mcp.tool(
        name="aap_create_group",
        annotations={"title": "Create Group", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_group(params: CreateGroupInput, ctx: Context) -> str:
        """Create a host group inside an AAP inventory.

        Args:
            params (CreateGroupInput): Group configuration.

        Returns:
            str: JSON with created group id and name.
        """
        try:
            data = await aap_post(ctx, "/groups/", {
                "name": params.name,
                "description": params.description,
                "inventory": params.inventory_id,
                "variables": params.variables,
            })
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class AddHostToGroupInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        group_id: int = Field(..., ge=1, description="Group ID to add host to")
        host_id: int = Field(..., ge=1, description="Host ID to add")

    @mcp.tool(
        name="aap_add_host_to_group",
        annotations={"title": "Add Host to Group", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_add_host_to_group(params: AddHostToGroupInput, ctx: Context) -> str:
        """Add an existing host to a group within an inventory.

        Args:
            params (AddHostToGroupInput):
                - group_id (int): Target group ID
                - host_id (int): Host ID to add

        Returns:
            str: JSON confirmation.
        """
        try:
            await aap_post(ctx, f"/groups/{params.group_id}/hosts/", {"id": params.host_id})
            return json.dumps({"success": True, "group_id": params.group_id, "host_id": params.host_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class RemoveHostFromGroupInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        group_id: int = Field(..., ge=1)
        host_id: int = Field(..., ge=1)

    @mcp.tool(
        name="aap_remove_host_from_group",
        annotations={"title": "Remove Host from Group", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_remove_host_from_group(params: RemoveHostFromGroupInput, ctx: Context) -> str:
        """Remove a host from a group (disassociate, not delete the host).

        Args:
            params (RemoveHostFromGroupInput):
                - group_id (int): Group ID
                - host_id (int): Host ID to remove

        Returns:
            str: JSON confirmation.
        """
        try:
            await aap_post(ctx, f"/groups/{params.group_id}/hosts/", {"id": params.host_id, "disassociate": True})
            return json.dumps({"success": True, "removed_host_id": params.host_id, "from_group_id": params.group_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteInventoryInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        inventory_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_inventory",
        annotations={"title": "Delete Inventory", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_inventory(params: DeleteInventoryInput, ctx: Context) -> str:
        """Delete an AAP inventory. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteInventoryInput):
                - inventory_id (int): Inventory ID
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation prompt or success JSON.
        """
        op_id = f"delete_inv_{params.inventory_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            try:
                inv = await aap_get(ctx, f"/inventories/{params.inventory_id}/")
                name = inv.get("name", f"ID {params.inventory_id}")
            except AAPAPIError:
                name = f"ID {params.inventory_id}"
            return require_confirmation_token(op_id, f"Delete inventory '{name}' and all its hosts/groups")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."

        try:
            await aap_delete(ctx, f"/inventories/{params.inventory_id}/")
            return json.dumps({"success": True, "deleted_inventory_id": params.inventory_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── UPDATE INVENTORY ─────────────────────────────────────────────────────

    class UpdateInventoryInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        inventory_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1)
        description: Optional[str] = Field(default=None)
        variables: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_update_inventory",
        annotations={"title": "Update Inventory", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_inventory(params: UpdateInventoryInput, ctx: Context) -> str:
        """Update an existing AAP inventory (PATCH).

        Args:
            params (UpdateInventoryInput): Fields to update.

        Returns:
            str: JSON with updated inventory id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "variables": params.variables,
            }.items() if v is not None}
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/inventories/{params.inventory_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── UPDATE / DELETE HOST ─────────────────────────────────────────────────

    class UpdateHostInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        host_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1)
        description: Optional[str] = Field(default=None)
        variables: Optional[str] = Field(default=None)
        enabled: Optional[bool] = Field(default=None)

    @mcp.tool(
        name="aap_update_host",
        annotations={"title": "Update Host", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_host(params: UpdateHostInput, ctx: Context) -> str:
        """Update an existing AAP host (PATCH).

        Args:
            params (UpdateHostInput): Fields to update.

        Returns:
            str: JSON with updated host id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "variables": params.variables,
                "enabled": params.enabled,
            }.items() if v is not None}
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/hosts/{params.host_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteHostInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        host_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_host",
        annotations={"title": "Delete Host", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_host(params: DeleteHostInput, ctx: Context) -> str:
        """Delete a host from an AAP inventory. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteHostInput):
                - host_id (int): Host ID
                - confirmation_token (Optional[str]): Token from first call
        """
        op_id = f"delete_host_{params.host_id}"
        settings = ctx.request_context.lifespan_context["settings"]
        if settings.require_confirmation and not params.confirmation_token:
            try:
                h = await aap_get(ctx, f"/hosts/{params.host_id}/")
                name = h.get("name", f"ID {params.host_id}")
            except AAPAPIError:
                name = f"ID {params.host_id}"
            return require_confirmation_token(op_id, f"Delete host '{name}'")
        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."
        try:
            await aap_delete(ctx, f"/hosts/{params.host_id}/")
            return json.dumps({"success": True, "deleted_host_id": params.host_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── UPDATE / DELETE GROUP ────────────────────────────────────────────────

    class UpdateGroupInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        group_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1)
        description: Optional[str] = Field(default=None)
        variables: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_update_group",
        annotations={"title": "Update Group", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_group(params: UpdateGroupInput, ctx: Context) -> str:
        """Update an existing AAP inventory group (PATCH).

        Args:
            params (UpdateGroupInput): Fields to update.

        Returns:
            str: JSON with updated group id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
                "variables": params.variables,
            }.items() if v is not None}
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/groups/{params.group_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteGroupInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        group_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_group",
        annotations={"title": "Delete Group", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_group(params: DeleteGroupInput, ctx: Context) -> str:
        """Delete a host group from an AAP inventory. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteGroupInput):
                - group_id (int): Group ID
                - confirmation_token (Optional[str]): Token from first call
        """
        op_id = f"delete_group_{params.group_id}"
        settings = ctx.request_context.lifespan_context["settings"]
        if settings.require_confirmation and not params.confirmation_token:
            try:
                g = await aap_get(ctx, f"/groups/{params.group_id}/")
                name = g.get("name", f"ID {params.group_id}")
            except AAPAPIError:
                name = f"ID {params.group_id}"
            return require_confirmation_token(op_id, f"Delete group '{name}' and all child groups")
        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."
        try:
            await aap_delete(ctx, f"/groups/{params.group_id}/")
            return json.dumps({"success": True, "deleted_group_id": params.group_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
