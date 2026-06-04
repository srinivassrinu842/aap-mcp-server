"""
AAP MCP Prompt Templates.

Pre-built prompts for common AAP operational workflows.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP):

    @mcp.prompt(name="aap_deploy_project")
    def deploy_project_prompt(project_name: str, github_url: str, branch: str = "main") -> str:
        """Prompt to create a project and set up a job template from GitHub."""
        return f"""Create a new AAP project called '{project_name}' from GitHub at {github_url} on branch '{branch}'.

Steps to follow:
1. Use aap_list_organizations to find the target organization ID
2. Use aap_create_project with scm_type='git', scm_url='{github_url}', scm_branch='{branch}'
3. Use aap_sync_project to trigger an initial sync
4. Use aap_get_project_sync_status to confirm the sync succeeded
5. Report the project ID and status back to the user"""

    @mcp.prompt(name="aap_troubleshoot_failures")
    def troubleshoot_failures_prompt(hours: int = 24) -> str:
        """Prompt to investigate failed jobs and summarize root causes."""
        return f"""Investigate failed AAP jobs from the last {hours} hours and provide a summary.

Steps to follow:
1. Use aap_get_failed_jobs(hours={hours}) to get the list of failed jobs
2. For the top 3 most recent failures, use aap_get_job_events with event_type='runner_on_failed'
3. Look for common failure patterns across hosts and tasks
4. Summarize: which job templates failed, how many hosts were affected, and likely root causes
5. Suggest remediation steps where possible"""

    @mcp.prompt(name="aap_cluster_health_check")
    def cluster_health_prompt() -> str:
        """Prompt for a comprehensive AAP cluster health report."""
        return """Perform a comprehensive health check of the AAP cluster and produce a status report.

Steps to follow:
1. Use aap_get_controller_health to check the ping endpoint
2. Use aap_get_cluster_status to check all node capacities and states
3. Use aap_get_license_info to check subscription validity and host count compliance
4. Use aap_list_running_jobs to show current workload
5. Use aap_get_failed_jobs(hours=1) to check for recent failures
6. Produce a summary report with: overall status (green/yellow/red), node health, license status, active jobs, and recent failures"""

    @mcp.prompt(name="aap_export_as_code")
    def export_as_code_prompt(org_id: str = "") -> str:
        """Prompt to export all AAP resources as Configuration-as-Code."""
        org_filter = f" scoped to organization ID {org_id}" if org_id else ""
        return f"""Export all AAP resources{org_filter} as Configuration-as-Code YAML compatible with the infra.aap_configuration Ansible collection.

Steps to follow:
1. Use aap_export_all_resources{f'(organization_id={org_id})' if org_id else '()'} to get all resources
2. Review the exported YAML structure and confirm it covers: projects, inventories, job templates, workflows, and schedules
3. Note any resources that require manual attention (e.g., credentials with secrets that cannot be exported)
4. Present the final YAML to the user with instructions for using it with the infra.aap_configuration collection"""

    @mcp.prompt(name="aap_new_inventory_setup")
    def new_inventory_prompt(inventory_name: str, org_name: str) -> str:
        """Prompt to create and populate a new inventory."""
        return f"""Set up a new AAP inventory called '{inventory_name}' for organization '{org_name}'.

Steps to follow:
1. Use aap_list_organizations with search='{org_name}' to find the organization ID
2. Use aap_create_inventory with name='{inventory_name}' and the found organization_id
3. Ask the user if they want to add hosts or groups now
4. If yes, use aap_create_host and aap_create_group as needed
5. Confirm the inventory is ready with total host count"""

    @mcp.prompt(name="aap_launch_and_monitor")
    def launch_and_monitor_prompt(template_name: str) -> str:
        """Prompt to find, launch, and monitor a job template."""
        return f"""Find and launch the job template named '{template_name}' and monitor it to completion.

Steps to follow:
1. Use aap_list_job_templates with search='{template_name}' to find the template ID
2. Use aap_get_job_template to review its configuration before launching
3. Use aap_launch_job_template with the found template_id
4. Use aap_get_job_output with the returned job_id to check progress
5. Report the final status (successful/failed) and any notable output"""
