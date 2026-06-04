"""
Structured audit logging for AAP MCP Server.
Logs all tool invocations, their parameters (with secrets masked), and outcomes.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MASKED_FIELDS = {"password", "ssh_key_data", "become_password", "vault_password", "token", "secret"}


def _mask_secrets(data: Any, depth: int = 0) -> Any:
    """Recursively mask sensitive fields in dicts."""
    if depth > 5:
        return data
    if isinstance(data, dict):
        return {
            k: "***MASKED***" if k.lower() in MASKED_FIELDS else _mask_secrets(v, depth + 1)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_secrets(i, depth + 1) for i in data]
    return data


class AuditLogger:
    """Writes structured JSON audit events."""

    def __init__(self, log_file: Optional[str] = None, structured: bool = True):
        self.log_file = log_file
        self.structured = structured
        self._file_handle = None

        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            try:
                self._file_handle = open(log_file, "a", encoding="utf-8", buffering=1)
            except OSError as e:
                logger.warning("Could not open audit log file %s: %s", log_file, e)

    def log(
        self,
        tool_name: str,
        params: Dict[str, Any],
        outcome: str,
        user_context: Optional[str] = None,
        error: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        """Record an audit event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "params": _mask_secrets(params),
            "outcome": outcome,  # "success" | "failure" | "denied" | "confirmed"
            "user_context": user_context,
            "resource_id": resource_id,
        }
        if error:
            event["error"] = error

        line = json.dumps(event)
        logger.info("AUDIT: %s", line)

        if self._file_handle:
            try:
                self._file_handle.write(line + "\n")
            except OSError as e:
                logger.warning("Failed to write audit log: %s", e)

    def __del__(self):
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
