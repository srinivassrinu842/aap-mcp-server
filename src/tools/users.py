"""
User & Team Management Tools for AAP MCP Server.

AAP API Mapping:
  list_users          GET    /api/v2/users/
  get_user            GET    /api/v2/users/{id}/
  create_user         POST   /api/v2/users/
  update_user         PATCH  /api/v2/users/{id}/
  delete_user         DELETE /api/v2/users/{id}/
  assign_roles        POST   /api/v2/users/{id}/roles/
  revoke_roles        POST   /api/v2/users/{id}/roles/ (disassociate)
  list_teams          GET    /api/v2/teams/
  create_team         POST   /api/v2/teams/
  update_team         PATCH  /api/v2/teams/{id}/
  delete_team         DELETE /api/v2/teams/{id}/
  add_user_to_team    POST   /api/v2/teams/{id}/users/
  remove_user         POST   /api/v2/teams/{id}/users/ (disassociate)
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

    # ─── USERS ────────────────────────────────────────────────────

    class ListUsersInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: Optional[str] = Field(default=None, description="Username or email substring filter")
        is_superuser: Optional[bool] = Field(default=None, description="Filter to superusers only")

    @mcp.tool(
        name="aap_list_users",
        annotations={"title": "List Users", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_users(params: ListUsersInput, ctx: Context) -> str:
        """List AAP users. Can filter for superusers/admins.

        Example: "List users with admin privileges" → set is_superuser=True

        Args:
            params (ListUsersInput):
                - page, page_size: Pagination
                - search (Optional[str]): Username/email substring
                - is_superuser (Optional[bool]): Filter superusers

        Returns:
            str: JSON with user list.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["username__icontains"] = params.search
            if params.is_superuser is not None:
                q["is_superuser"] = params.is_superuser

            data = await aap_get(ctx, "/users/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "results": [
                    {
                        "id": u["id"],
                        "username": u["username"],
                        "email": u.get("email", ""),
                        "first_name": u.get("first_name", ""),
                        "last_name": u.get("last_name", ""),
                        "is_superuser": u.get("is_superuser", False),
                        "is_system_auditor": u.get("is_system_auditor", False),
                        "last_login": u.get("last_login"),
                    }
                    for u in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateUserInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        username: str = Field(..., min_length=1, max_length=150, description="AAP username")
        password: str = Field(..., min_length=8, description="Initial password")
        email: str = Field(default="", description="User email address")
        first_name: str = Field(default="")
        last_name: str = Field(default="")
        is_superuser: bool = Field(default=False)
        is_system_auditor: bool = Field(default=False)

    @mcp.tool(
        name="aap_create_user",
        annotations={"title": "Create User", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_user(params: CreateUserInput, ctx: Context) -> str:
        """Create a new AAP user.

        Args:
            params (CreateUserInput): User details.

        Returns:
            str: JSON with created user id and username.
        """
        try:
            data = await aap_post(ctx, "/users/", {
                "username": params.username,
                "password": params.password,
                "email": params.email,
                "first_name": params.first_name,
                "last_name": params.last_name,
                "is_superuser": params.is_superuser,
                "is_system_auditor": params.is_system_auditor,
            })
            return json.dumps({"success": True, "id": data["id"], "username": data["username"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class AssignRoleInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        user_id: int = Field(..., ge=1, description="User ID")
        role_id: int = Field(..., ge=1, description="Role ID to assign (get IDs from resource role endpoints)")

    @mcp.tool(
        name="aap_assign_role",
        annotations={"title": "Assign Role to User", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_assign_role(params: AssignRoleInput, ctx: Context) -> str:
        """Assign an RBAC role to an AAP user.

        Args:
            params (AssignRoleInput):
                - user_id (int): User ID
                - role_id (int): Role ID (from /api/v2/roles/ or resource role lists)

        Returns:
            str: JSON confirmation.
        """
        try:
            await aap_post(ctx, f"/users/{params.user_id}/roles/", {"id": params.role_id})
            return json.dumps({"success": True, "user_id": params.user_id, "role_id": params.role_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class RevokeRoleInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        user_id: int = Field(..., ge=1)
        role_id: int = Field(..., ge=1)

    @mcp.tool(
        name="aap_revoke_role",
        annotations={"title": "Revoke Role from User", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_revoke_role(params: RevokeRoleInput, ctx: Context) -> str:
        """Revoke an RBAC role from an AAP user.

        Args:
            params (RevokeRoleInput):
                - user_id (int): User ID
                - role_id (int): Role ID to revoke

        Returns:
            str: JSON confirmation.
        """
        try:
            await aap_post(ctx, f"/users/{params.user_id}/roles/", {"id": params.role_id, "disassociate": True})
            return json.dumps({"success": True, "revoked_role_id": params.role_id, "from_user_id": params.user_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── TEAMS ────────────────────────────────────────────────────

    class ListTeamsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_list_teams",
        annotations={"title": "List Teams", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_teams(params: ListTeamsInput, ctx: Context) -> str:
        """List AAP teams.

        Args:
            params (ListTeamsInput): Pagination and filter.

        Returns:
            str: JSON with team list.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            data = await aap_get(ctx, "/teams/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "results": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "organization": t.get("summary_fields", {}).get("organization", {}).get("name"),
                    }
                    for t in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateTeamInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512)
        organization_id: int = Field(..., ge=1)
        description: str = Field(default="")

    @mcp.tool(
        name="aap_create_team",
        annotations={"title": "Create Team", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_team(params: CreateTeamInput, ctx: Context) -> str:
        """Create a new AAP team within an organization.

        Args:
            params (CreateTeamInput): Team name, organization_id, description.

        Returns:
            str: JSON with created team id and name.
        """
        try:
            data = await aap_post(ctx, "/teams/", {
                "name": params.name,
                "description": params.description,
                "organization": params.organization_id,
            })
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class AddUserToTeamInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        team_id: int = Field(..., ge=1)
        user_id: int = Field(..., ge=1)

    @mcp.tool(
        name="aap_add_user_to_team",
        annotations={"title": "Add User to Team", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_add_user_to_team(params: AddUserToTeamInput, ctx: Context) -> str:
        """Add a user to an AAP team.

        Args:
            params (AddUserToTeamInput):
                - team_id (int): Team ID
                - user_id (int): User ID to add

        Returns:
            str: JSON confirmation.
        """
        try:
            await aap_post(ctx, f"/teams/{params.team_id}/users/", {"id": params.user_id})
            return json.dumps({"success": True, "team_id": params.team_id, "user_id": params.user_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class RemoveUserFromTeamInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        team_id: int = Field(..., ge=1)
        user_id: int = Field(..., ge=1)

    @mcp.tool(
        name="aap_remove_user_from_team",
        annotations={"title": "Remove User from Team", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_remove_user_from_team(params: RemoveUserFromTeamInput, ctx: Context) -> str:
        """Remove a user from an AAP team.

        Args:
            params (RemoveUserFromTeamInput):
                - team_id (int): Team ID
                - user_id (int): User ID to remove

        Returns:
            str: JSON confirmation.
        """
        try:
            await aap_post(ctx, f"/teams/{params.team_id}/users/", {"id": params.user_id, "disassociate": True})
            return json.dumps({"success": True, "removed_user_id": params.user_id, "from_team_id": params.team_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── GET / UPDATE / DELETE USER ───────────────────────────────────────────

    class GetUserInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        user_id: int = Field(..., ge=1, description="User ID")

    @mcp.tool(
        name="aap_get_user",
        annotations={"title": "Get User", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_user(params: GetUserInput, ctx: Context) -> str:
        """Get details of a specific AAP user by ID.

        Args:
            params (GetUserInput):
                - user_id (int): User ID

        Returns:
            str: JSON with user details.
        """
        try:
            data = await aap_get(ctx, f"/users/{params.user_id}/")
            return json.dumps({
                "id": data["id"],
                "username": data["username"],
                "email": data.get("email", ""),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "is_superuser": data.get("is_superuser", False),
                "is_system_auditor": data.get("is_system_auditor", False),
                "last_login": data.get("last_login"),
                "created": data.get("created"),
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateUserInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        user_id: int = Field(..., ge=1)
        email: Optional[str] = Field(default=None)
        first_name: Optional[str] = Field(default=None)
        last_name: Optional[str] = Field(default=None)
        password: Optional[str] = Field(default=None, min_length=8, description="New password")
        is_superuser: Optional[bool] = Field(default=None)
        is_system_auditor: Optional[bool] = Field(default=None)

    @mcp.tool(
        name="aap_update_user",
        annotations={"title": "Update User", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_user(params: UpdateUserInput, ctx: Context) -> str:
        """Update an existing AAP user (PATCH).

        Args:
            params (UpdateUserInput): Fields to update.

        Returns:
            str: JSON with updated user id and username.
        """
        try:
            payload = {k: v for k, v in {
                "email": params.email,
                "first_name": params.first_name,
                "last_name": params.last_name,
                "password": params.password,
                "is_superuser": params.is_superuser,
                "is_system_auditor": params.is_system_auditor,
            }.items() if v is not None}
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/users/{params.user_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "username": data["username"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteUserInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        user_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_user",
        annotations={"title": "Delete User", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_user(params: DeleteUserInput, ctx: Context) -> str:
        """Delete an AAP user. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteUserInput):
                - user_id (int): User ID
                - confirmation_token (Optional[str]): Token from first call
        """
        op_id = f"delete_user_{params.user_id}"
        settings = ctx.request_context.lifespan_context["settings"]
        if settings.require_confirmation and not params.confirmation_token:
            try:
                u = await aap_get(ctx, f"/users/{params.user_id}/")
                name = u.get("username", f"ID {params.user_id}")
            except AAPAPIError:
                name = f"ID {params.user_id}"
            return require_confirmation_token(op_id, f"Delete user '{name}'")
        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."
        try:
            await aap_delete(ctx, f"/users/{params.user_id}/")
            return json.dumps({"success": True, "deleted_user_id": params.user_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    # ─── UPDATE / DELETE TEAM ─────────────────────────────────────────────────

    class UpdateTeamInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        team_id: int = Field(..., ge=1)
        name: Optional[str] = Field(default=None, min_length=1)
        description: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_update_team",
        annotations={"title": "Update Team", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_team(params: UpdateTeamInput, ctx: Context) -> str:
        """Update an existing AAP team (PATCH).

        Args:
            params (UpdateTeamInput): Fields to update (name, description).

        Returns:
            str: JSON with updated team id and name.
        """
        try:
            payload = {k: v for k, v in {
                "name": params.name,
                "description": params.description,
            }.items() if v is not None}
            if not payload:
                return "Error: No fields to update."
            data = await aap_patch(ctx, f"/teams/{params.team_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteTeamInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        team_id: int = Field(..., ge=1)
        confirmation_token: Optional[str] = Field(default=None)

    @mcp.tool(
        name="aap_delete_team",
        annotations={"title": "Delete Team", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_team(params: DeleteTeamInput, ctx: Context) -> str:
        """Delete an AAP team. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteTeamInput):
                - team_id (int): Team ID
                - confirmation_token (Optional[str]): Token from first call
        """
        op_id = f"delete_team_{params.team_id}"
        settings = ctx.request_context.lifespan_context["settings"]
        if settings.require_confirmation and not params.confirmation_token:
            try:
                t = await aap_get(ctx, f"/teams/{params.team_id}/")
                name = t.get("name", f"ID {params.team_id}")
            except AAPAPIError:
                name = f"ID {params.team_id}"
            return require_confirmation_token(op_id, f"Delete team '{name}'")
        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."
        try:
            await aap_delete(ctx, f"/teams/{params.team_id}/")
            return json.dumps({"success": True, "deleted_team_id": params.team_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
