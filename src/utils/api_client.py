"""
AAP API Client - shared HTTP utilities for all tool modules.

Features:
- Unified request/response handling
- Pagination support
- Rate limiting
- Actionable error messages
- Read-only mode enforcement
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

import httpx
from mcp.server.fastmcp import Context

logger = logging.getLogger(__name__)

AAP_API_BASE = "/api/v2"


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 120):
        self.requests_per_minute = requests_per_minute
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            window = 60.0
            # Remove timestamps older than window
            while self._timestamps and now - self._timestamps[0] > window:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.requests_per_minute:
                sleep_time = window - (now - self._timestamps[0])
                if sleep_time > 0:
                    logger.debug("Rate limit reached. Sleeping %.2fs", sleep_time)
                    await asyncio.sleep(sleep_time)

            self._timestamps.append(time.monotonic())


_rate_limiter = RateLimiter()


def get_client(ctx: Context) -> httpx.AsyncClient:
    """Extract the shared HTTP client from FastMCP lifespan context."""
    return ctx.request_context.lifespan_context["http_client"]


def get_settings(ctx: Context):
    """Extract settings from lifespan context."""
    return ctx.request_context.lifespan_context["settings"]


def get_audit_logger(ctx: Context):
    """Extract audit logger from lifespan context."""
    return ctx.request_context.lifespan_context["audit_logger"]


async def aap_get(
    ctx: Context,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Perform a GET request against the AAP Controller API."""
    client = get_client(ctx)
    settings = get_settings(ctx)
    api_base = settings.aap_api_base_path
    await _rate_limiter.acquire()
    url = f"{api_base}{path}"
    try:
        response = await client.get(url, params=params)
        _raise_for_status(response)
        return response.json()
    except httpx.HTTPStatusError as e:
        raise AAPAPIError.from_http_error(e) from e
    except httpx.TimeoutException:
        raise AAPAPIError(f"Request timed out: GET {url}")


async def aap_post(
    ctx: Context,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    operation_name: str = "create",
) -> Dict[str, Any]:
    """Perform a POST request. Blocked in read-only mode (unless it's a read-action like launch)."""
    _check_write_allowed(ctx, operation_name)
    client = get_client(ctx)
    settings = get_settings(ctx)
    api_base = settings.aap_api_base_path
    await _rate_limiter.acquire()
    url = f"{api_base}{path}"
    try:
        response = await client.post(url, json=data or {})
        _raise_for_status(response)
        # 204 No Content (e.g. disassociate actions) returns empty body
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()
    except httpx.HTTPStatusError as e:
        raise AAPAPIError.from_http_error(e) from e


async def aap_patch(
    ctx: Context,
    path: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Perform a PATCH request."""
    _check_write_allowed(ctx, "update")
    client = get_client(ctx)
    settings = get_settings(ctx)
    api_base = settings.aap_api_base_path
    await _rate_limiter.acquire()
    url = f"{api_base}{path}"
    try:
        response = await client.patch(url, json=data)
        _raise_for_status(response)
        return response.json()
    except httpx.HTTPStatusError as e:
        raise AAPAPIError.from_http_error(e) from e


async def aap_put(
    ctx: Context,
    path: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Perform a PUT request."""
    _check_write_allowed(ctx, "update")
    client = get_client(ctx)
    settings = get_settings(ctx)
    api_base = settings.aap_api_base_path
    await _rate_limiter.acquire()
    url = f"{api_base}{path}"
    try:
        response = await client.put(url, json=data)
        _raise_for_status(response)
        return response.json()
    except httpx.HTTPStatusError as e:
        raise AAPAPIError.from_http_error(e) from e


async def aap_delete(
    ctx: Context,
    path: str,
) -> bool:
    """Perform a DELETE request."""
    _check_write_allowed(ctx, "delete")
    client = get_client(ctx)
    settings = get_settings(ctx)
    api_base = settings.aap_api_base_path
    await _rate_limiter.acquire()
    url = f"{api_base}{path}"
    try:
        response = await client.delete(url)
        _raise_for_status(response)
        return True
    except httpx.HTTPStatusError as e:
        raise AAPAPIError.from_http_error(e) from e


async def aap_list_all(
    ctx: Context,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    page_size: int = 50,
) -> Tuple[List[Dict], int]:
    """Fetch all pages of a list endpoint. Returns (items, total_count)."""
    all_items: List[Dict] = []
    settings = get_settings(ctx)
    api_base = settings.aap_api_base_path
    next_url: Optional[str] = f"{api_base}{path}"
    query_params = {**(params or {}), "page_size": page_size}
    total = 0

    client = get_client(ctx)
    while next_url:
        await _rate_limiter.acquire()
        try:
            response = await client.get(next_url, params=query_params if not next_url.startswith("http") else None)
            _raise_for_status(response)
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise AAPAPIError.from_http_error(e) from e

        total = data.get("count", 0)
        all_items.extend(data.get("results", []))
        next_url = data.get("next")
        query_params = None  # params already encoded in next URL

    return all_items, total


def _check_write_allowed(ctx: Context, operation: str):
    """Raise if server is in read-only mode."""
    settings = get_settings(ctx)
    if settings.read_only_mode:
        raise AAPAPIError(
            f"Operation '{operation}' is blocked: server is running in READ-ONLY mode. "
            "Set AAP_MCP_READ_ONLY_MODE=false to enable write operations."
        )


def _raise_for_status(response: httpx.Response):
    """Raise AAPAPIError with context for non-2xx responses."""
    if response.is_success:
        return
    try:
        body = response.json()
        detail = body.get("detail") or body.get("__all__") or json.dumps(body)
    except Exception:
        detail = response.text[:500]
    raise httpx.HTTPStatusError(
        message=f"HTTP {response.status_code}: {detail}",
        request=response.request,
        response=response,
    )


def format_job_status(job: Dict) -> str:
    """Return emoji-annotated status string for a job."""
    status = job.get("status", "unknown")
    icons = {
        "successful": "✅",
        "failed": "❌",
        "running": "🔄",
        "pending": "⏳",
        "waiting": "⏳",
        "canceled": "🚫",
        "error": "💥",
    }
    return f"{icons.get(status, '❓')} {status}"


def paginate_params(page: int = 1, page_size: int = 20) -> Dict[str, int]:
    """Build pagination query params."""
    return {"page": page, "page_size": page_size}


CONFIRMATION_TOKENS: Dict[str, str] = {}


def require_confirmation_token(operation_id: str, description: str) -> str:
    """
    Generate a confirmation token for a destructive operation.
    Returns a message asking the user to confirm with the token.
    """
    import uuid
    token = str(uuid.uuid4())[:8].upper()
    CONFIRMATION_TOKENS[token] = operation_id
    return (
        f"⚠️  DESTRUCTIVE OPERATION: {description}\n\n"
        f"To confirm, call this tool again with confirmation_token='{token}'\n"
        f"This token expires after one use."
    )


def validate_confirmation_token(token: str, operation_id: str) -> bool:
    """Validate and consume a confirmation token."""
    if token and CONFIRMATION_TOKENS.get(token) == operation_id:
        del CONFIRMATION_TOKENS[token]
        return True
    return False


class AAPAPIError(Exception):
    """Structured error from AAP API calls."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message)

    @classmethod
    def from_http_error(cls, e: httpx.HTTPStatusError) -> "AAPAPIError":
        code = e.response.status_code
        try:
            body = e.response.json()
            detail = body.get("detail") or body.get("__all__") or str(body)
        except Exception:
            detail = e.response.text[:300]

        messages = {
            400: f"Bad request: {detail}. Check your input parameters.",
            401: "Authentication failed. Check AAP_OAUTH_TOKEN or credentials.",
            403: f"Permission denied: {detail}. Your AAP user lacks the required role.",
            404: f"Resource not found: {detail}. Verify the ID or name exists.",
            405: "Method not allowed on this endpoint.",
            409: f"Conflict: {detail}. Resource may already exist.",
            429: "Rate limited by AAP Controller. Slow down requests.",
            500: f"AAP Controller internal error: {detail}",
            503: "AAP Controller unavailable. Check cluster health.",
        }
        msg = messages.get(code, f"HTTP {code}: {detail}")
        return cls(msg, status_code=code)
