"""Tenant isolation middleware using ContextVar.

Extracts the current tenant from the X-Tenant-ID request header (or falls
back to subdomain detection). The tenant ID is stored in a ContextVar so
that any downstream code — repositories, MCP tools, event handlers — can
call get_current_tenant() without needing explicit parameter passing.
"""

from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Context variable — thread/task-safe tenant state
# ---------------------------------------------------------------------------

_current_tenant: ContextVar[str] = ContextVar("current_tenant", default="default")


def get_current_tenant() -> str:
    """Return the tenant ID for the current request.

    Safe to call from any async context within the request lifecycle::

        tenant = get_current_tenant()
        items = await repo.list(tenant_id=tenant)
    """
    return _current_tenant.get()


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant from request headers or subdomain.

    Priority:
    1. X-Tenant-ID header (explicit)
    2. First subdomain segment (e.g., acme.agentos.app → "acme")
    3. Falls back to "default"
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Check header
        tenant_id = request.headers.get("X-Tenant-ID")

        # 2. Fall back to subdomain
        if not tenant_id:
            host = request.headers.get("host", "")
            parts = host.split(".")
            if len(parts) > 2:
                tenant_id = parts[0]

        # 3. Default
        token = _current_tenant.set(tenant_id or "default")
        try:
            response = await call_next(request)
            return response
        finally:
            _current_tenant.reset(token)
