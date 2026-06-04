"""
Monitoring and Troubleshooting Tools for AAP MCP Server.

AAP API Mapping:
  get_job_output      GET /api/v2/jobs/{id}/stdout/
  get_job_events      GET /api/v2/jobs/{id}/job_events/
  get_failed_jobs     GET /api/v2/jobs/?status=failed&...
  get_recent_activity GET /api/v2/activity_stream/
  get_system_logs     GET /api/v2/system_jobs/
  get_audit_logs      GET /api/v2/activity_stream/
  list_running_jobs   GET /api/v2/jobs/?status=running
"""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

from ..utils.api_client import (
    aap_get, aap_list_all, AAPAPIError, format_job_status, paginate_params
)


def register(mcp: FastMCP):

    class GetJobOutputInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        job_id: int = Field(..., ge=1, description="Job ID to fetch output for")
        format: str = Field(
            default="txt",
            description="Output format: 'txt' (human-readable) or 'json' (structured)"
        )
        max_lines: int = Field(
            default=200,
            ge=1,
            le=5000,
            description="Maximum number of output lines to return"
        )

    @mcp.tool(
        name="aap_get_job_output",
        annotations={"title": "Get Job Output", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_job_output(params: GetJobOutputInput, ctx: Context) -> str:
        """Fetch stdout/stderr output from an AAP job run.

        Useful for troubleshooting failures or reviewing what a job did.

        Args:
            params (GetJobOutputInput):
                - job_id (int): Job ID
                - format (str): 'txt' or 'json'
                - max_lines (int): Max output lines (default 200)

        Returns:
            str: Job output text or JSON with status and truncated output.
        """
        try:
            # Get job status first
            job = await aap_get(ctx, f"/jobs/{params.job_id}/")
            status = job.get("status", "unknown")

            # Get stdout
            output_data = await aap_get(ctx, f"/jobs/{params.job_id}/stdout/", params={"format": params.format})

            if params.format == "json":
                return json.dumps({
                    "job_id": params.job_id,
                    "status": status,
                    "output": output_data,
                }, indent=2)

            content = str(output_data) if not isinstance(output_data, str) else output_data
            lines = content.split("\n")
            truncated = len(lines) > params.max_lines
            display_lines = lines[-params.max_lines:] if truncated else lines

            return json.dumps({
                "job_id": params.job_id,
                "status": format_job_status(job),
                "started": job.get("started"),
                "finished": job.get("finished"),
                "elapsed": job.get("elapsed"),
                "truncated": truncated,
                "total_lines": len(lines),
                "output": "\n".join(display_lines),
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetJobEventsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        job_id: int = Field(..., ge=1, description="Job ID")
        event_type: Optional[str] = Field(
            default=None,
            description="Filter by event type: 'runner_on_failed', 'runner_on_ok', 'runner_on_unreachable'"
        )
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=50, ge=1, le=200)

    @mcp.tool(
        name="aap_get_job_events",
        annotations={"title": "Get Job Events", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_job_events(params: GetJobEventsInput, ctx: Context) -> str:
        """Get structured events from an AAP job (tasks, roles, failures).

        More granular than stdout - shows individual task results per host.

        Args:
            params (GetJobEventsInput):
                - job_id (int): Job ID
                - event_type (Optional[str]): Filter by event type
                - page/page_size: Pagination

        Returns:
            str: JSON with event list including host, task, result details.
        """
        try:
            q = paginate_params(params.page, params.page_size)
            if params.event_type:
                q["event"] = params.event_type

            data = await aap_get(ctx, f"/jobs/{params.job_id}/job_events/", params=q)
            events = []
            for ev in data.get("results", []):
                events.append({
                    "counter": ev.get("counter"),
                    "event": ev.get("event"),
                    "task": ev.get("task"),
                    "host": ev.get("host"),
                    "failed": ev.get("failed", False),
                    "changed": ev.get("changed", False),
                    "stdout": ev.get("stdout", "")[:500],  # Truncate long lines
                })
            return json.dumps({
                "job_id": params.job_id,
                "count": data.get("count", 0),
                "events": events,
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetFailedJobsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        hours: int = Field(default=24, ge=1, le=720, description="Look back N hours for failed jobs")
        limit: int = Field(default=20, ge=1, le=100, description="Max failed jobs to return")
        job_template: Optional[str] = Field(default=None, description="Filter by job template name")

    @mcp.tool(
        name="aap_get_failed_jobs",
        annotations={"title": "Get Failed Jobs", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_failed_jobs(params: GetFailedJobsInput, ctx: Context) -> str:
        """List failed AAP jobs within the last N hours.

        Example: "Show failed jobs from the last 24 hours"

        Args:
            params (GetFailedJobsInput):
                - hours (int): Look-back window in hours (default 24)
                - limit (int): Max results (default 20)
                - job_template (Optional[str]): Filter by template name

        Returns:
            str: JSON with list of failed jobs including id, name, started,
                 finished, elapsed, and template name.
        """
        try:
            from datetime import datetime, timedelta, timezone
            since = (datetime.now(timezone.utc) - timedelta(hours=params.hours)).isoformat()
            q = {
                "status": "failed",
                "finished__gte": since,
                "page_size": params.limit,
                "order_by": "-finished",
            }
            if params.job_template:
                q["job_template__name__icontains"] = params.job_template

            data = await aap_get(ctx, "/jobs/", params=q)
            jobs = []
            for j in data.get("results", []):
                sf = j.get("summary_fields", {})
                jobs.append({
                    "id": j["id"],
                    "status": format_job_status(j),
                    "template_name": sf.get("job_template", {}).get("name", "N/A"),
                    "started": j.get("started"),
                    "finished": j.get("finished"),
                    "elapsed_seconds": j.get("elapsed"),
                    "failed_hosts": j.get("failed", 0),
                    "launched_by": sf.get("created_by", {}).get("username", "unknown"),
                })
            return json.dumps({
                "window_hours": params.hours,
                "total_failed": data.get("count", 0),
                "returned": len(jobs),
                "jobs": jobs,
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class ListRunningJobsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        include_workflow_jobs: bool = Field(default=True)

    @mcp.tool(
        name="aap_list_running_jobs",
        annotations={"title": "List Running Jobs", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_list_running_jobs(params: ListRunningJobsInput, ctx: Context) -> str:
        """List all currently running jobs in AAP.

        Args:
            params (ListRunningJobsInput):
                - include_workflow_jobs (bool): Also show running workflow jobs

        Returns:
            str: JSON with list of running jobs.
        """
        try:
            q = {"status": "running", "page_size": 100, "order_by": "-started"}
            data = await aap_get(ctx, "/jobs/", params=q)
            jobs = []
            for j in data.get("results", []):
                sf = j.get("summary_fields", {})
                jobs.append({
                    "id": j["id"],
                    "type": "job",
                    "template": sf.get("job_template", {}).get("name", "N/A"),
                    "started": j.get("started"),
                    "elapsed_seconds": j.get("elapsed"),
                    "launched_by": sf.get("created_by", {}).get("username"),
                })

            if params.include_workflow_jobs:
                wf_data = await aap_get(ctx, "/workflow_jobs/", params={"status": "running", "page_size": 100})
                for wj in wf_data.get("results", []):
                    sf = wj.get("summary_fields", {})
                    jobs.append({
                        "id": wj["id"],
                        "type": "workflow_job",
                        "template": sf.get("workflow_job_template", {}).get("name", "N/A"),
                        "started": wj.get("started"),
                        "elapsed_seconds": wj.get("elapsed"),
                        "launched_by": sf.get("created_by", {}).get("username"),
                    })

            return json.dumps({
                "running_count": len(jobs),
                "jobs": sorted(jobs, key=lambda x: x.get("started") or "", reverse=True),
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetActivityInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        limit: int = Field(default=20, ge=1, le=100)
        operation: Optional[str] = Field(
            default=None,
            description="Filter by operation: 'create', 'update', 'delete', 'associate'"
        )
        object_type: Optional[str] = Field(
            default=None,
            description="Filter by object type: 'job_template', 'inventory', 'project', etc."
        )
        username: Optional[str] = Field(default=None, description="Filter by AAP username")

    @mcp.tool(
        name="aap_get_recent_activity",
        annotations={"title": "Get Recent Activity", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_recent_activity(params: GetActivityInput, ctx: Context) -> str:
        """Get recent AAP activity stream (audit trail of changes).

        Args:
            params (GetActivityInput):
                - limit (int): Number of events to return
                - operation (Optional[str]): Filter by CRUD operation
                - object_type (Optional[str]): Filter by resource type
                - username (Optional[str]): Filter by actor username

        Returns:
            str: JSON with activity events.
        """
        try:
            q: dict = {"page_size": params.limit, "order_by": "-timestamp"}
            if params.operation:
                q["operation"] = params.operation
            if params.object_type:
                q["object1"] = params.object_type
            if params.username:
                q["actor__username"] = params.username

            data = await aap_get(ctx, "/activity_stream/", params=q)
            events = []
            for ev in data.get("results", []):
                events.append({
                    "timestamp": ev.get("timestamp"),
                    "operation": ev.get("operation"),
                    "object_type": ev.get("object1"),
                    "object_name": ev.get("summary_fields", {}).get("object1", {}).get("name"),
                    "actor": ev.get("summary_fields", {}).get("actor", {}).get("username", "system"),
                    "changes": ev.get("changes", {}),
                })
            return json.dumps({"total": data.get("count", 0), "events": events}, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"

    class GetAuditLogsInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        limit: int = Field(default=50, ge=1, le=200)
        username: Optional[str] = Field(default=None, description="Filter by AAP username")

    @mcp.tool(
        name="aap_get_audit_logs",
        annotations={"title": "Get Audit Logs", "readOnlyHint": True, "destructiveHint": False},
    )
    async def aap_get_audit_logs(params: GetAuditLogsInput, ctx: Context) -> str:
        """Get AAP audit logs (alias for activity stream with delete/create focus).

        Args:
            params (GetAuditLogsInput):
                - limit (int): Number of log entries
                - username (Optional[str]): Filter by actor

        Returns:
            str: JSON with audit log entries.
        """
        try:
            q = {"page_size": params.limit, "order_by": "-timestamp"}
            if params.username:
                q["actor__username"] = params.username

            data = await aap_get(ctx, "/activity_stream/", params=q)
            return json.dumps({
                "count": data.get("count", 0),
                "logs": [
                    {
                        "timestamp": e.get("timestamp"),
                        "actor": e.get("summary_fields", {}).get("actor", {}).get("username", "system"),
                        "operation": e.get("operation"),
                        "resource": f"{e.get('object1', 'unknown')}:{e.get('summary_fields', {}).get('object1', {}).get('name', '')}",
                        "changes_summary": list(e.get("changes", {}).keys()),
                    }
                    for e in data.get("results", [])
                ],
            }, indent=2)
        except AAPAPIError as e:
            return f"Error: {e}"
