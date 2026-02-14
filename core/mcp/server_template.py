"""
AgentOS MCP Server Template — FastMCP Pattern

Every MCP server in the framework follows this pattern:
- FastMCP decorators for clean tool definition
- Typed parameters and return values
- Tenant-scoped operations
- Error handling with structured responses
"""
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


def create_mcp_server(
    name: str,
    description: str = "",
) -> FastMCP:
    """Factory for creating MCP servers with standard config."""
    mcp = FastMCP(name)

    # Register health check tool (all servers get this)
    @mcp.tool()
    def health_check() -> dict:
        """Check if this MCP server is operational."""
        return {
            "server": name,
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return mcp


# --- Example Usage ---
# This shows the pattern. Verticals copy this and add domain tools.

example_server = create_mcp_server("example", "Example MCP server")


@example_server.tool()
def search_items(
    query: str,
    tenant_id: str,
    limit: int = 10,
) -> dict:
    """Search items with tenant scoping."""
    return {
        "results": [],
        "count": 0,
        "tenant_id": tenant_id,
        "query": query,
    }


@example_server.tool()
def get_item(
    item_id: str,
    tenant_id: str,
) -> dict:
    """Get a single item by ID. Tenant-scoped."""
    return {
        "id": item_id,
        "tenant_id": tenant_id,
        "data": {},
    }


@example_server.resource("data://items/{item_id}")
def item_resource(item_id: str) -> str:
    """Expose item data as an MCP resource."""
    return f'{{"id": "{item_id}", "data": {{}}}}'
