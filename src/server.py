"""
AAP MCP Server - Ansible Automation Platform MCP Server
Enterprise-grade MCP server exposing AAP Controller REST APIs to LLMs.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP, Context

from .utils.auth import AAPAuthClient
from .utils.config import Settings
from .utils.audit import AuditLogger
from .tools import (
    organizations,
    users,
    projects,
    inventories,
    credentials,
    execution_environments,
    job_templates,
    workflows,
    schedules,
    automation_hub,
    platform_admin,
    monitoring,
    config_as_code,
)
from .resources import aap_resources
from .prompts import aap_prompts

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastMCP):
    """Manage AAP client lifecycle across all tool calls.

    FastMCP passes the server instance as the first argument — must be accepted
    even if unused here.
    """
    # Settings are loaded lazily here (not at module import time) so that
    # missing env vars raise a clear error at startup, not at import.
    settings = Settings()

    auth_client = AAPAuthClient(
        controller_url=settings.aap_controller_url,
        username=settings.aap_username,
        password=settings.aap_password,
        oauth_token=settings.aap_oauth_token,
        verify_ssl=settings.aap_verify_ssl,
    )
    audit_logger = AuditLogger(
        log_file=settings.audit_log_file,
        structured=True,
    )

    http_client = httpx.AsyncClient(
        base_url=settings.aap_controller_url,
        headers=await auth_client.get_auth_headers(),
        verify=settings.aap_verify_ssl,
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        limits=httpx.Limits(
            max_connections=settings.max_connections,
            max_keepalive_connections=settings.max_keepalive_connections,
        ),
    )

    logger.info("AAP MCP Server starting. Controller: %s", settings.aap_controller_url)

    yield {
        "http_client": http_client,
        "auth_client": auth_client,
        "audit_logger": audit_logger,
        "settings": settings,
    }

    await http_client.aclose()
    logger.info("AAP MCP Server shutdown complete.")


# Initialize FastMCP server
mcp = FastMCP(
    name="aap_mcp",
    instructions="""You are an AI interface for Ansible Automation Platform (AAP).
You can manage organizations, users, projects, inventories, credentials, job templates,
workflows, schedules, and execution environments. You can launch jobs, monitor their
status, troubleshoot failures, and export/import configuration-as-code.

Always confirm before destructive operations (delete, cancel). For read-only queries,
respond immediately. For job launches, confirm the target template and any extra variables.
""",
    lifespan=app_lifespan,
)

# Register all tool modules
organizations.register(mcp)
users.register(mcp)
projects.register(mcp)
inventories.register(mcp)
credentials.register(mcp)
execution_environments.register(mcp)
job_templates.register(mcp)
workflows.register(mcp)
schedules.register(mcp)
automation_hub.register(mcp)
platform_admin.register(mcp)
monitoring.register(mcp)
config_as_code.register(mcp)

# Register resources and prompts
aap_resources.register(mcp)
aap_prompts.register(mcp)


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "streamable_http")
    port = int(os.getenv("MCP_PORT", "8000"))
    host = os.getenv("MCP_HOST", "0.0.0.0")

    mcp.settings.host = host
    mcp.settings.port = port

    run_transport = "streamable-http" if transport in ("streamable_http", "streamable-http") else transport
    mcp.run(transport=run_transport)


def main():
    """Main entrypoint — called by Dockerfile ENTRYPOINT: python -m src.server"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    transport = os.getenv("MCP_TRANSPORT", "streamable_http")
    port = int(os.getenv("MCP_PORT", "8000"))
    host = os.getenv("MCP_HOST", "0.0.0.0")

    logger.info("Starting AAP MCP Server | transport=%s port=%s", transport, port)

    mcp.settings.host = host
    mcp.settings.port = port

    run_transport = "streamable-http" if transport in ("streamable_http", "streamable-http") else transport
    mcp.run(transport=run_transport)

