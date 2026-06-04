# AAP MCP Server - Dockerfile
# Multi-stage build for minimal production image

# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --upgrade pip hatchling

# Copy dependency files first for layer caching
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Copy source
COPY src/ ./src/

# ── Production stage ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS production

# Security: run as non-root
RUN groupadd -r aap-mcp && useradd -r -g aap-mcp -d /app aap-mcp

WORKDIR /app

# Copy installed packages and source
COPY --from=builder /install /usr/local
COPY --from=builder /build/src ./src/

# Create audit log directory
RUN mkdir -p /var/log/aap-mcp && chown aap-mcp:aap-mcp /var/log/aap-mcp

USER aap-mcp

# Expose MCP streamable HTTP port
EXPOSE 8000

# Health check — only relevant for streamable_http transport
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/health', timeout=5); r.raise_for_status()" || exit 1

ENV MCP_TRANSPORT=streamable_http
ENV MCP_PORT=8000
ENV MCP_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Use python -c to invoke main() — avoids relative-import issues with -m
ENTRYPOINT ["python", "-c", "from src.server import main; main()"]
