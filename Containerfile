# AAP MCP Server - Containerfile (Podman / OpenShift compatible)
# Uses UBI9 minimal base for RHEL compatibility

# ── Build stage ──────────────────────────────────────────────────────────────
FROM registry.access.redhat.com/ubi9/python-311 AS builder

USER root
WORKDIR /build

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY src/ ./src/

# ── Production stage ──────────────────────────────────────────────────────────
FROM registry.access.redhat.com/ubi9/python-311 AS production

USER root

WORKDIR /app

# Copy packages and source from builder
COPY --from=builder /install /usr/local
COPY --from=builder /build/src ./src/

# Audit log directory (OpenShift may mount this as a PVC)
RUN mkdir -p /var/log/aap-mcp && chmod 0755 /var/log/aap-mcp

# OpenShift runs with arbitrary UID in root group
RUN chown -R 1001:0 /app /var/log/aap-mcp && chmod -R g=u /app /var/log/aap-mcp

USER 1001

EXPOSE 8000

LABEL name="aap-mcp-server" \
      version="1.0.0" \
      description="Enterprise MCP Server for Ansible Automation Platform" \
      maintainer="NESA OCP Operational Support"

ENV MCP_TRANSPORT=streamable_http \
    PYTHONUNBUFFERED=1 \
    MCP_PORT=8000 \
    MCP_HOST=0.0.0.0

ENTRYPOINT ["python", "-c", "from src.server import main; main()"]
