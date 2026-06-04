# AAP MCP Server

Enterprise-grade MCP (Model Context Protocol) server that exposes **Ansible Automation Platform (AAP) 2.x** as a complete AI interface for LLMs — Claude, ChatGPT, Cursor, Continue, OpenCode, and any MCP-compatible client.

---

## Features

| Category | Tools |
|---|---|
| Organizations | list, get, create, update, delete |
| Users & Teams | list, create, assign/revoke roles, team membership |
| Projects | list, get, create, update, delete, sync, sync-status |
| Inventories | list, create, update, delete + hosts + groups |
| Credentials | list, get, create, update, delete + credential types |
| Execution Environments | list, create, update, delete |
| Job Templates | list, get, create, update, delete, copy, **launch**, relaunch, cancel |
| Workflows | list, get, create, update, delete, **launch**, status |
| Schedules | list, create, update, delete |
| Automation Hub | list collections |
| Platform Admin | controller health, cluster status, license info, instances |
| Monitoring | job output, job events, failed jobs, running jobs, activity stream, audit logs |
| Config-as-Code | export project/inventory/job-template/workflow/all as YAML |

**Total: 60+ tools**

---

## Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/your-org/aap-mcp-server
cd aap-mcp-server
cp .env.example .env
# Edit .env with your AAP Controller URL and OAuth token
```

### 2. Run locally (stdio mode for Claude Desktop/local client)

```bash
pip install -r requirements.txt
python -m src.server
```

### 3. Run as Remote HTTP Server (exposes a network port)

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8000 python -m src.server
```

### 4. Deploy to OpenShift

```bash
# Build with Podman
podman build -f Containerfile -t quay.io/your-org/aap-mcp-server:latest .
podman push quay.io/your-org/aap-mcp-server:latest

# Deploy via Helm
helm upgrade --install aap-mcp helm/aap-mcp/ \
  --namespace aap-mcp \
  --create-namespace \
  --set aap.controllerUrl=https://controller.example.com \
  --set aap.oauthToken=your_token \
  --set route.enabled=true
```

---

## Claude Desktop / MCP Client Configuration

### Option A: Local Python (stdio)
Add to `~/.config/claude/claude_desktop_config.json` or your MCP client settings:

```json
{
  "mcpServers": {
    "aap": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/aap-mcp-server",
      "env": {
        "AAP_CONTROLLER_URL": "https://your-controller.example.com",
        "AAP_OAUTH_TOKEN": "your_token_here",
        "AAP_VERIFY_SSL": "false",
        "AAP_API_BASE_PATH": "/api/controller/v2",
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

### Option B: Docker Container (stdio)
Run the server inside a Docker container using stdio transport:

```json
{
  "mcpServers": {
    "aap-docker-stdio": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--env", "AAP_CONTROLLER_URL",
        "--env", "AAP_VERIFY_SSL",
        "--env", "AAP_API_BASE_PATH",
        "--env", "AAP_OAUTH_TOKEN",
        "--env", "MCP_TRANSPORT=stdio",
        "aap-mcp-server:latest"
      ],
      "env": {
        "AAP_CONTROLLER_URL": "https://your-controller.example.com",
        "AAP_VERIFY_SSL": "false",
        "AAP_API_BASE_PATH": "/api/controller/v2",
        "AAP_OAUTH_TOKEN": "your_token_here"
      }
    }
  }
}
```

### Option C: Remote HTTP / SSE Server (Docker)
Run the server as a background service exposing port `8000`:

```bash
docker run -d --name aap-mcp-server-container -p 8000:8000 \
  -e AAP_CONTROLLER_URL="https://your-controller.example.com" \
  -e AAP_OAUTH_TOKEN="your_token_here" \
  -e AAP_VERIFY_SSL="false" \
  -e AAP_API_BASE_PATH="/api/controller/v2" \
  -e MCP_TRANSPORT="streamable-http" \
  -e MCP_PORT="8000" \
  -e MCP_HOST="0.0.0.0" \
  aap-mcp-server:latest
```

Then configure your MCP client (like Cursor or remote Claude clients) to connect to the HTTP endpoint:
* **Endpoint URL**: `http://<your-host-ip>:8000/mcp`

---

## Natural Language Examples

Once connected, try:

- *"Create a new project called redis-automation from GitHub at https://github.com/myorg/redis-playbooks"*
- *"Launch the Redis production workflow"*
- *"Show failed jobs from the last 24 hours"*
- *"Create an inventory called AWS-Production in the Default organization"*
- *"Add host web01.example.com to the Production inventory"*
- *"Create a job template for Apache installation using the web-playbooks project"*
- *"Export all job templates as code"*
- *"Show cluster health"*
- *"List users with admin privileges"*

---

## Security & Settings

- **OAuth tokens** preferred over username/password.
- **Read-only mode**: set `AAP_MCP_READ_ONLY_MODE=true` to block all mutations.
- **Confirmation workflow**: destructive operations (delete/cancel) require a two-step confirmation token.
- **Audit logging**: all tool calls logged to structured JSONL with secrets masked.
- **Rate limiting**: configurable token-bucket limiter to avoid AAP API overload.
- **RBAC**: all operations respect the authenticated AAP user's permissions.
- **API Base Path**: set `AAP_API_BASE_PATH` (e.g. `/api/controller/v2`) if your controller API is mounted on a non-standard base path (default: `/api/v2`).

---

## Architecture

```
MCP Client (Claude/Cursor/etc)
        │
        │ MCP Protocol (stdio or streamable HTTP)
        ▼
  aap-mcp-server (FastMCP)
  ├── tools/           # 60+ tool implementations
  ├── resources/       # URI-addressable AAP data + API mapping
  ├── prompts/         # Pre-built operational workflow prompts
  └── utils/
      ├── api_client.py  # Shared HTTP client, pagination, rate limiting
      ├── auth.py        # OAuth token management
      ├── audit.py       # Structured audit logging
      └── config.py      # Pydantic settings from env vars
        │
        │ HTTPS REST API (/api/v2/)
        ▼
  Ansible Automation Platform Controller
```

---

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/unit/ -v

# Run integration tests (requires live AAP)
AAP_CONTROLLER_URL=https://... AAP_OAUTH_TOKEN=... pytest tests/integration/

# Lint
ruff check src/
black src/
```

---

## API → Tool Mapping

See the `aap://api-map` MCP resource for the complete mapping, or query it:
> *"Show me the API mapping for all tools"*
