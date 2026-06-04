"""
Credential Management Tools for AAP MCP Server.

AAP API Mapping:
  list_credentials        GET    /api/v2/credentials/
  get_credential          GET    /api/v2/credentials/{id}/
  create_credential       POST   /api/v2/credentials/
  update_credential       PATCH  /api/v2/credentials/{id}/
  delete_credential       DELETE /api/v2/credentials/{id}/
  list_credential_types   GET    /api/v2/credential_types/
  create_credential_type  POST   /api/v2/credential_types/
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


def register(mcp: FastMCP):

    class ListCredsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=200)
        search: str | None = Field(default=None, description="Name substring filter")
        credential_type: int | None = Field(default=None, description="Filter by credential type ID")

    @mcp.tool(
        name="aap_list_credentials",
        annotations={"title": "List Credentials", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_credentials(params: ListCredsInput, ctx: Context) -> str:
        """List AAP credentials. Secrets are never returned by the API.

        Args:
            params (ListCredsInput): Pagination and filter options.

        Returns:
            str: JSON with credential list (id, name, kind, type_name, organization).
                 Note: secret fields are always masked by AAP.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.search:
                q["name__icontains"] = params.search
            if params.credential_type:
                q["credential_type"] = params.credential_type

            data = await aap_get(ctx, "/credentials/", params=q)
            return json.dumps(
                {
                    "count": data.get("count", 0),
                    "results": [
                        {
                            "id": c["id"],
                            "name": c["name"],
                            "description": c.get("description", ""),
                            "kind": c.get("kind", ""),
                            "credential_type": c.get("summary_fields", {}).get("credential_type", {}).get("name"),
                            "organization": c.get("summary_fields", {}).get("organization", {}).get("name"),
                            "managed": c.get("managed", False),
                        }
                        for c in data.get("results", [])
                    ],
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetCredInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        credential_id: int = Field(..., ge=1, description="Credential ID")

    @mcp.tool(
        name="aap_get_credential",
        annotations={"title": "Get Credential", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_credential(params: GetCredInput, ctx: Context) -> str:
        """Get details of an AAP credential (secrets masked by AAP).

        Args:
            params (GetCredInput):
                - credential_id (int): Credential ID

        Returns:
            str: JSON with credential metadata. Secret fields shown as '$encrypted$'.
        """
        try:
            data = await aap_get(ctx, f"/credentials/{params.credential_id}/")
            return json.dumps(
                {
                    "id": data["id"],
                    "name": data["name"],
                    "description": data.get("description", ""),
                    "kind": data.get("kind", ""),
                    "credential_type": data.get("summary_fields", {}).get("credential_type", {}),
                    "organization": data.get("summary_fields", {}).get("organization", {}),
                    "inputs": data.get("inputs", {}),  # Secrets will be $encrypted$
                    "managed": data.get("managed", False),
                    "created": data.get("created"),
                    "modified": data.get("modified"),
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateCredInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, max_length=512, description="Credential name")
        credential_type_id: int = Field(
            ..., ge=1, description="Credential type ID (use aap_list_credential_types to find)"
        )
        inputs: dict[str, Any] = Field(
            ...,
            description="Credential inputs matching the type schema (e.g., {'username': 'admin', 'password': 'secret'})",
        )
        organization_id: int | None = Field(default=None, ge=1, description="Owner organization ID")
        description: str = Field(default="")

    @mcp.tool(
        name="aap_create_credential",
        annotations={"title": "Create Credential", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_credential(params: CreateCredInput, ctx: Context) -> str:
        """Create a new AAP credential.

        Use aap_list_credential_types first to find the correct type ID and
        understand required inputs schema for that type.

        Args:
            params (CreateCredInput):
                - name (str): Credential name
                - credential_type_id (int): Type ID
                - inputs (dict): Type-specific inputs (username, password, ssh_key_data, etc.)
                - organization_id (Optional[int]): Owner org
                - description (str): Optional description

        Returns:
            str: JSON with created credential id and name.
        """
        try:
            payload: dict[str, Any] = {
                "name": params.name,
                "description": params.description,
                "credential_type": params.credential_type_id,
                "inputs": params.inputs,
            }
            if params.organization_id:
                payload["organization"] = params.organization_id

            data = await aap_post(ctx, "/credentials/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class UpdateCredInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        credential_id: int = Field(..., ge=1)
        name: str | None = Field(default=None, min_length=1)
        description: str | None = Field(default=None)
        inputs: dict[str, Any] | None = Field(default=None, description="Updated inputs (only changed fields needed)")

    @mcp.tool(
        name="aap_update_credential",
        annotations={"title": "Update Credential", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_update_credential(params: UpdateCredInput, ctx: Context) -> str:
        """Update an existing AAP credential (PATCH).

        Args:
            params (UpdateCredInput): Fields to update.

        Returns:
            str: JSON with updated credential id and name.
        """
        try:
            payload = {
                k: v
                for k, v in {
                    "name": params.name,
                    "description": params.description,
                    "inputs": params.inputs,
                }.items()
                if v is not None
            }

            if not payload:
                return "Error: No fields to update."

            data = await aap_patch(ctx, f"/credentials/{params.credential_id}/", payload)
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class DeleteCredInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        credential_id: int = Field(..., ge=1)
        confirmation_token: str | None = Field(default=None)

    @mcp.tool(
        name="aap_delete_credential",
        annotations={"title": "Delete Credential", "readOnlyHint": False, "destructiveHint": True},
    )
    async def aap_delete_credential(params: DeleteCredInput, ctx: Context) -> str:
        """Delete an AAP credential. DESTRUCTIVE - requires confirmation.

        Args:
            params (DeleteCredInput):
                - credential_id (int): Credential ID
                - confirmation_token (Optional[str]): Token from first call

        Returns:
            str: Confirmation prompt or success JSON.
        """
        op_id = f"delete_cred_{params.credential_id}"
        settings = ctx.request_context.lifespan_context["settings"]

        if settings.require_confirmation and not params.confirmation_token:
            try:
                cred = await aap_get(ctx, f"/credentials/{params.credential_id}/")
                name = cred.get("name", f"ID {params.credential_id}")
            except AAPAPIError:
                name = f"ID {params.credential_id}"
            return require_confirmation_token(op_id, f"Delete credential '{name}'")

        if settings.require_confirmation and not validate_confirmation_token(params.confirmation_token, op_id):
            return "Error: Invalid or expired confirmation token."

        try:
            await aap_delete(ctx, f"/credentials/{params.credential_id}/")
            return json.dumps({"success": True, "deleted_credential_id": params.credential_id}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ListCredTypesInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=50, ge=1, le=200)
        managed: bool | None = Field(default=None, description="True = built-in types, False = custom types")

    @mcp.tool(
        name="aap_list_credential_types",
        annotations={"title": "List Credential Types", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_credential_types(params: ListCredTypesInput, ctx: Context) -> str:
        """List available AAP credential types (SSH, Vault, AWS, Azure, etc.).

        Use the returned id when calling aap_create_credential.

        Args:
            params (ListCredTypesInput):
                - managed (Optional[bool]): Filter built-in vs custom types

        Returns:
            str: JSON with credential type list including id, name, kind, and injectors schema.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.managed is not None:
                q["managed"] = params.managed

            data = await aap_get(ctx, "/credential_types/", params=q)
            return json.dumps(
                {
                    "count": data.get("count", 0),
                    "results": [
                        {
                            "id": ct["id"],
                            "name": ct["name"],
                            "kind": ct.get("kind", ""),
                            "managed": ct.get("managed", False),
                            "description": ct.get("description", ""),
                            "inputs_required_fields": list(ct.get("inputs", {}).get("required", [])),
                        }
                        for ct in data.get("results", [])
                    ],
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class CreateCredTypeInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        name: str = Field(..., min_length=1, description="Custom credential type name")
        kind: str = Field(default="cloud", description="Kind: 'cloud', 'net', or 'ssh'")
        description: str = Field(default="")
        inputs: dict[str, Any] = Field(
            ...,
            description="JSON schema for inputs (fields definition). E.g.: {'fields': [{'id': 'api_token', 'type': 'string', 'secret': true}]}",
        )
        injectors: dict[str, Any] = Field(
            default_factory=dict,
            description="Injector mappings (env vars or extra_vars). E.g.: {'env': {'MY_TOKEN': '{{ api_token }}'}}",
        )

    @mcp.tool(
        name="aap_create_credential_type",
        annotations={"title": "Create Custom Credential Type", "readOnlyHint": False, "destructiveHint": False},
    )
    async def aap_create_credential_type(params: CreateCredTypeInput, ctx: Context) -> str:
        """Create a custom AAP credential type with custom fields and injectors.

        Args:
            params (CreateCredTypeInput):
                - name (str): Type name
                - kind (str): 'cloud', 'net', or 'ssh'
                - inputs (dict): Field schema definition
                - injectors (dict): Environment/extra_vars injection mapping

        Returns:
            str: JSON with created credential type id and name.
        """
        try:
            data = await aap_post(
                ctx,
                "/credential_types/",
                {
                    "name": params.name,
                    "kind": params.kind,
                    "description": params.description,
                    "inputs": params.inputs,
                    "injectors": params.injectors,
                },
            )
            return json.dumps({"success": True, "id": data["id"], "name": data["name"]}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
