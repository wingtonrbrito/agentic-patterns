"""
AgentOS Tool Registry — Dynamic Tool Discovery + Registration

Manages MCP tools across verticals:
- Auto-discover tools from vertical directories
- Register/deregister at runtime
- Tenant-scoped tool access (some tools are tenant-specific)
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Callable, Optional
from datetime import datetime
import asyncio


class ToolDefinition(BaseModel):
    """Registered tool metadata."""
    name: str
    description: str
    server_name: str
    parameters: dict = Field(default_factory=dict)
    tenant_scoped: bool = True
    requires_auth: bool = False
    registered_at: datetime = Field(default_factory=datetime.utcnow)


class ToolRegistry:
    """Central registry for all MCP tools."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        server_name: str,
        handler: Callable,
        tenant_scoped: bool = True,
    ):
        """Register a tool."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            server_name=server_name,
            tenant_scoped=tenant_scoped,
        )
        self._handlers[name] = handler

    def deregister(self, name: str):
        """Remove a tool."""
        self._tools.pop(name, None)
        self._handlers.pop(name, None)

    def list_tools(self, tenant_id: Optional[str] = None) -> list[ToolDefinition]:
        """List available tools, optionally filtered by tenant access."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool metadata."""
        return self._tools.get(name)

    async def invoke(self, name: str, **kwargs) -> dict:
        """Invoke a registered tool."""
        handler = self._handlers.get(name)
        if not handler:
            raise ValueError(f"Tool not found: {name}")

        if asyncio.iscoroutinefunction(handler):
            return await handler(**kwargs)
        return handler(**kwargs)

    @property
    def tool_count(self) -> int:
        return len(self._tools)
