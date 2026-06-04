"""
Platform Administration Tools for AAP MCP Server.

AAP API Mapping:
  get_controller_health  GET /api/v2/ping/
  get_cluster_status     GET /api/v2/instances/
  get_license_info       GET /api/v2/config/
  get_subscription_info  GET /api/v2/config/
  list_instances         GET /api/v2/instances/
  get_instance_capacity  GET /api/v2/instances/{id}/
"""

import json

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from ..utils.api_client import AAPAPIError, aap_get


def register(mcp: FastMCP):

    class HealthInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    @mcp.tool(
        name="aap_get_controller_health",
        annotations={"title": "Get Controller Health", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_controller_health(params: HealthInput, ctx: Context) -> str:
        """Check AAP Controller health status (ping endpoint).

        Returns:
            str: JSON with ha (bool), version, active_node, install_uuid, and instance statuses.
        """
        try:
            data = await aap_get(ctx, "/ping/")
            return json.dumps(
                {
                    "status": "healthy" if data.get("ha") is not None else "unknown",
                    "ha_enabled": data.get("ha", False),
                    "version": data.get("version"),
                    "active_node": data.get("active_node"),
                    "install_uuid": data.get("install_uuid"),
                    "instances": data.get("instances", {}),
                    "instance_groups": data.get("instance_groups", {}),
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    @mcp.tool(
        name="aap_get_cluster_status",
        annotations={"title": "Get Cluster Status", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_cluster_status(params: HealthInput, ctx: Context) -> str:
        """Get AAP cluster node status, capacity, and health summary.

        Returns:
            str: JSON with list of instances and their capacity/health.
        """
        try:
            data = await aap_get(ctx, "/instances/")
            instances = []
            for inst in data.get("results", []):
                instances.append(
                    {
                        "id": inst["id"],
                        "hostname": inst.get("hostname"),
                        "node_type": inst.get("node_type"),
                        "node_state": inst.get("node_state"),
                        "capacity": inst.get("capacity", 0),
                        "consumed_capacity": inst.get("consumed_capacity", 0),
                        "percent_capacity_remaining": inst.get("percent_capacity_remaining"),
                        "enabled": inst.get("enabled", True),
                        "version": inst.get("version"),
                    }
                )
            healthy = sum(1 for i in instances if i["node_state"] == "ready")
            return json.dumps(
                {
                    "total_nodes": len(instances),
                    "healthy_nodes": healthy,
                    "instances": instances,
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    @mcp.tool(
        name="aap_get_license_info",
        annotations={"title": "Get License Info", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_license_info(params: HealthInput, ctx: Context) -> str:
        """Get AAP subscription and license details.

        Returns:
            str: JSON with license type, expiry, host count, and validity status.
        """
        try:
            data = await aap_get(ctx, "/config/")
            lic = data.get("license_info", {})
            return json.dumps(
                {
                    "license_type": lic.get("license_type"),
                    "valid_key": lic.get("valid_key"),
                    "compliant": lic.get("compliant"),
                    "date_expired": lic.get("date_expired"),
                    "date_warning": lic.get("date_warning"),
                    "free_instances": lic.get("free_instances"),
                    "total_instances": lic.get("total_instances"),
                    "current_instances": lic.get("current_instances"),
                    "available_instances": lic.get("available_instances"),
                    "time_remaining": lic.get("time_remaining"),
                    "subscription_name": lic.get("subscription_name"),
                    "product_name": lic.get("product_name"),
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetInstanceInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        instance_id: int = Field(..., ge=1, description="Instance ID")

    @mcp.tool(
        name="aap_get_instance_capacity",
        annotations={"title": "Get Instance Capacity", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_instance_capacity(params: GetInstanceInput, ctx: Context) -> str:
        """Get capacity and workload details for a specific AAP controller node.

        Args:
            params (GetInstanceInput):
                - instance_id (int): Instance ID

        Returns:
            str: JSON with capacity, consumed capacity, running jobs.
        """
        try:
            data = await aap_get(ctx, f"/instances/{params.instance_id}/")
            return json.dumps(
                {
                    "id": data["id"],
                    "hostname": data.get("hostname"),
                    "node_type": data.get("node_type"),
                    "node_state": data.get("node_state"),
                    "capacity": data.get("capacity"),
                    "consumed_capacity": data.get("consumed_capacity"),
                    "percent_capacity_remaining": data.get("percent_capacity_remaining"),
                    "jobs_running": data.get("jobs_running", 0),
                    "jobs_total": data.get("jobs_total", 0),
                    "cpu": data.get("cpu"),
                    "memory": data.get("memory"),
                    "version": data.get("version"),
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"

    @mcp.tool(
        name="aap_list_instances",
        annotations={"title": "List Instances", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_instances(params: HealthInput, ctx: Context) -> str:
        """List all AAP controller and execution node instances.

        Returns:
            str: JSON with list of instances.
        """
        try:
            data = await aap_get(ctx, "/instances/")
            return json.dumps(
                {
                    "count": data.get("count", 0),
                    "instances": [
                        {
                            "id": i["id"],
                            "hostname": i.get("hostname"),
                            "node_type": i.get("node_type"),
                            "node_state": i.get("node_state"),
                            "enabled": i.get("enabled"),
                            "capacity": i.get("capacity"),
                        }
                        for i in data.get("results", [])
                    ],
                },
                indent=2,
            )
        except AAPAPIError as e:
            return f"Error: {e}"
