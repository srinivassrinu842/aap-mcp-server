"""
AAP MCP Resources.

Exposes AAP data as MCP resources for efficient, URI-based access.
Resources are useful for frequently-accessed reference data.
"""

import json
from mcp.server.fastmcp import FastMCP, Context

from ..utils.api_client import aap_get, AAPAPIError


def register(mcp: FastMCP):

    @mcp.resource("aap://job/{job_id}/status")
    async def get_job_status_resource(job_id: str) -> str:
        """Get live job status as a resource URI.
        Access via: aap://job/42/status
        """
        # Resources don't receive Context in the same way; this is a static resource pattern
        return json.dumps({"note": "Use aap_get_job_output tool for live job data", "job_id": job_id})

    @mcp.resource("aap://api-map")
    async def get_api_map() -> str:
        """Complete MCP Tool → AAP REST API mapping reference."""
        mapping = [
            # Organizations
            {"tool": "aap_list_organizations",    "endpoint": "GET /api/v2/organizations/",                   "description": "List all organizations"},
            {"tool": "aap_get_organization",       "endpoint": "GET /api/v2/organizations/{id}/",              "description": "Get organization by ID"},
            {"tool": "aap_create_organization",    "endpoint": "POST /api/v2/organizations/",                  "description": "Create organization"},
            {"tool": "aap_update_organization",    "endpoint": "PATCH /api/v2/organizations/{id}/",            "description": "Update organization"},
            {"tool": "aap_delete_organization",    "endpoint": "DELETE /api/v2/organizations/{id}/",           "description": "Delete organization"},
            # Users
            {"tool": "aap_list_users",             "endpoint": "GET /api/v2/users/",                          "description": "List users"},
            {"tool": "aap_create_user",            "endpoint": "POST /api/v2/users/",                         "description": "Create user"},
            {"tool": "aap_assign_role",            "endpoint": "POST /api/v2/users/{id}/roles/",              "description": "Assign RBAC role to user"},
            {"tool": "aap_revoke_role",            "endpoint": "POST /api/v2/users/{id}/roles/ (disassociate)","description": "Revoke RBAC role from user"},
            # Teams
            {"tool": "aap_list_teams",             "endpoint": "GET /api/v2/teams/",                          "description": "List teams"},
            {"tool": "aap_create_team",            "endpoint": "POST /api/v2/teams/",                         "description": "Create team"},
            {"tool": "aap_add_user_to_team",       "endpoint": "POST /api/v2/teams/{id}/users/",              "description": "Add user to team"},
            {"tool": "aap_remove_user_from_team",  "endpoint": "POST /api/v2/teams/{id}/users/ (disassociate)","description": "Remove user from team"},
            # Projects
            {"tool": "aap_list_projects",          "endpoint": "GET /api/v2/projects/",                       "description": "List projects"},
            {"tool": "aap_get_project",            "endpoint": "GET /api/v2/projects/{id}/",                  "description": "Get project details"},
            {"tool": "aap_create_project",         "endpoint": "POST /api/v2/projects/",                      "description": "Create project"},
            {"tool": "aap_update_project",         "endpoint": "PATCH /api/v2/projects/{id}/",                "description": "Update project"},
            {"tool": "aap_delete_project",         "endpoint": "DELETE /api/v2/projects/{id}/",               "description": "Delete project"},
            {"tool": "aap_sync_project",           "endpoint": "POST /api/v2/projects/{id}/update/",          "description": "Trigger SCM sync"},
            {"tool": "aap_get_project_sync_status","endpoint": "GET /api/v2/project_updates/{id}/",           "description": "Get sync status"},
            # Inventories
            {"tool": "aap_list_inventories",       "endpoint": "GET /api/v2/inventories/",                    "description": "List inventories"},
            {"tool": "aap_create_inventory",       "endpoint": "POST /api/v2/inventories/",                   "description": "Create inventory"},
            {"tool": "aap_update_inventory",       "endpoint": "PATCH /api/v2/inventories/{id}/",             "description": "Update inventory"},
            {"tool": "aap_delete_inventory",       "endpoint": "DELETE /api/v2/inventories/{id}/",            "description": "Delete inventory"},
            {"tool": "aap_list_hosts",             "endpoint": "GET /api/v2/hosts/",                          "description": "List hosts"},
            {"tool": "aap_create_host",            "endpoint": "POST /api/v2/hosts/",                         "description": "Add host to inventory"},
            {"tool": "aap_create_group",           "endpoint": "POST /api/v2/groups/",                        "description": "Create host group"},
            {"tool": "aap_add_host_to_group",      "endpoint": "POST /api/v2/groups/{id}/hosts/",             "description": "Add host to group"},
            {"tool": "aap_remove_host_from_group", "endpoint": "POST /api/v2/groups/{id}/hosts/ (disassociate)","description": "Remove host from group"},
            # Credentials
            {"tool": "aap_list_credentials",       "endpoint": "GET /api/v2/credentials/",                   "description": "List credentials"},
            {"tool": "aap_get_credential",         "endpoint": "GET /api/v2/credentials/{id}/",              "description": "Get credential details"},
            {"tool": "aap_create_credential",      "endpoint": "POST /api/v2/credentials/",                  "description": "Create credential"},
            {"tool": "aap_update_credential",      "endpoint": "PATCH /api/v2/credentials/{id}/",            "description": "Update credential"},
            {"tool": "aap_delete_credential",      "endpoint": "DELETE /api/v2/credentials/{id}/",           "description": "Delete credential"},
            {"tool": "aap_list_credential_types",  "endpoint": "GET /api/v2/credential_types/",              "description": "List credential types"},
            {"tool": "aap_create_credential_type", "endpoint": "POST /api/v2/credential_types/",             "description": "Create custom credential type"},
            # Execution Environments
            {"tool": "aap_list_execution_environments",  "endpoint": "GET /api/v2/execution_environments/",        "description": "List EEs"},
            {"tool": "aap_create_execution_environment", "endpoint": "POST /api/v2/execution_environments/",       "description": "Create EE"},
            {"tool": "aap_update_execution_environment", "endpoint": "PATCH /api/v2/execution_environments/{id}/", "description": "Update EE"},
            {"tool": "aap_delete_execution_environment", "endpoint": "DELETE /api/v2/execution_environments/{id}/","description": "Delete EE"},
            # Job Templates
            {"tool": "aap_list_job_templates",     "endpoint": "GET /api/v2/job_templates/",                  "description": "List job templates"},
            {"tool": "aap_get_job_template",       "endpoint": "GET /api/v2/job_templates/{id}/",             "description": "Get job template"},
            {"tool": "aap_create_job_template",    "endpoint": "POST /api/v2/job_templates/",                 "description": "Create job template"},
            {"tool": "aap_update_job_template",    "endpoint": "PATCH /api/v2/job_templates/{id}/",           "description": "Update job template"},
            {"tool": "aap_delete_job_template",    "endpoint": "DELETE /api/v2/job_templates/{id}/",          "description": "Delete job template"},
            {"tool": "aap_copy_job_template",      "endpoint": "POST /api/v2/job_templates/{id}/copy/",       "description": "Copy job template"},
            {"tool": "aap_launch_job_template",    "endpoint": "POST /api/v2/job_templates/{id}/launch/",     "description": "Launch job template"},
            {"tool": "aap_relaunch_job",           "endpoint": "POST /api/v2/jobs/{id}/relaunch/",            "description": "Relaunch a job"},
            {"tool": "aap_cancel_job",             "endpoint": "POST /api/v2/jobs/{id}/cancel/",              "description": "Cancel a running job"},
            # Workflows
            {"tool": "aap_list_workflow_templates",   "endpoint": "GET /api/v2/workflow_job_templates/",          "description": "List workflows"},
            {"tool": "aap_get_workflow_template",     "endpoint": "GET /api/v2/workflow_job_templates/{id}/",     "description": "Get workflow"},
            {"tool": "aap_create_workflow_template",  "endpoint": "POST /api/v2/workflow_job_templates/",         "description": "Create workflow"},
            {"tool": "aap_update_workflow_template",  "endpoint": "PATCH /api/v2/workflow_job_templates/{id}/",   "description": "Update workflow"},
            {"tool": "aap_delete_workflow_template",  "endpoint": "DELETE /api/v2/workflow_job_templates/{id}/",  "description": "Delete workflow"},
            {"tool": "aap_launch_workflow",           "endpoint": "POST /api/v2/workflow_job_templates/{id}/launch/","description": "Launch workflow"},
            {"tool": "aap_get_workflow_status",       "endpoint": "GET /api/v2/workflow_jobs/{id}/",              "description": "Get workflow job status"},
            # Schedules
            {"tool": "aap_list_schedules",         "endpoint": "GET /api/v2/schedules/",                      "description": "List schedules"},
            {"tool": "aap_create_schedule",        "endpoint": "POST /api/v2/schedules/",                     "description": "Create schedule"},
            {"tool": "aap_update_schedule",        "endpoint": "PATCH /api/v2/schedules/{id}/",               "description": "Update schedule"},
            {"tool": "aap_delete_schedule",        "endpoint": "DELETE /api/v2/schedules/{id}/",              "description": "Delete schedule"},
            # Automation Hub
            {"tool": "aap_list_collections",       "endpoint": "GET /api/automation-hub/v3/collections/",    "description": "List Automation Hub collections"},
            # Platform Admin
            {"tool": "aap_get_controller_health",  "endpoint": "GET /api/v2/ping/",                          "description": "Controller health check"},
            {"tool": "aap_get_cluster_status",     "endpoint": "GET /api/v2/instances/",                     "description": "Cluster node status"},
            {"tool": "aap_get_license_info",       "endpoint": "GET /api/v2/config/",                        "description": "License and subscription info"},
            {"tool": "aap_list_instances",         "endpoint": "GET /api/v2/instances/",                     "description": "List controller instances"},
            {"tool": "aap_get_instance_capacity",  "endpoint": "GET /api/v2/instances/{id}/",                "description": "Instance capacity details"},
            # Monitoring
            {"tool": "aap_get_job_output",         "endpoint": "GET /api/v2/jobs/{id}/stdout/",              "description": "Get job stdout"},
            {"tool": "aap_get_job_events",         "endpoint": "GET /api/v2/jobs/{id}/job_events/",          "description": "Get structured job events"},
            {"tool": "aap_get_failed_jobs",        "endpoint": "GET /api/v2/jobs/?status=failed",            "description": "List failed jobs"},
            {"tool": "aap_list_running_jobs",      "endpoint": "GET /api/v2/jobs/?status=running",           "description": "List running jobs"},
            {"tool": "aap_get_recent_activity",    "endpoint": "GET /api/v2/activity_stream/",               "description": "Activity stream / audit trail"},
            {"tool": "aap_get_audit_logs",         "endpoint": "GET /api/v2/activity_stream/",               "description": "Audit logs"},
            # Config-as-Code
            {"tool": "aap_export_project",         "endpoint": "GET /api/v2/projects/{id}/",                 "description": "Export project as CaC YAML"},
            {"tool": "aap_export_job_template",    "endpoint": "GET /api/v2/job_templates/{id}/",            "description": "Export job template as CaC YAML"},
            {"tool": "aap_export_workflow",        "endpoint": "GET /api/v2/workflow_job_templates/{id}/",   "description": "Export workflow as CaC YAML"},
            {"tool": "aap_export_inventory",       "endpoint": "GET /api/v2/inventories/{id}/ + hosts",      "description": "Export inventory as CaC YAML"},
            {"tool": "aap_export_all_resources",   "endpoint": "Multiple GET /api/v2/ endpoints",            "description": "Export all resources as CaC YAML"},
        ]
        return json.dumps({"tool_count": len(mapping), "mapping": mapping}, indent=2)
