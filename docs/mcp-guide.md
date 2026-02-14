# MCP Server Guide

AgentOS uses the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) via [FastMCP](https://github.com/jlowin/fastmcp) to expose tools and resources that agents can call. Each vertical defines its own MCP server.

---

## What Is an MCP Server?

An MCP server is a structured tool registry. It provides:

- **Tools** -- Functions the LLM can invoke (with typed inputs and outputs).
- **Resources** -- Read-only data endpoints the LLM can fetch for context.

Agents discover available tools at runtime via the MCP protocol, enabling dynamic capability resolution.

---

## The `create_mcp_server` Factory

All MCP servers are created through a shared factory:

```python
from agentos.core.mcp_factory import create_mcp_server

mcp = create_mcp_server(
    name="task-management",
    description="Tools for creating and managing tasks",
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique server identifier (kebab-case) |
| `description` | `str` | Human-readable description (shown in tool discovery) |

The factory returns a configured `FastMCP` instance with standard middleware (logging, error handling, tenant validation) already attached.

---

## Defining Tools

### Basic Tool

```python
@mcp.tool()
async def create_task(title: str, description: str = "",
                      priority: str = "medium") -> dict:
    """Create a new task.

    Args:
        title: The task title (required).
        description: Optional detailed description.
        priority: One of: low, medium, high, critical. Defaults to medium.

    Returns:
        The created task with its generated ID.
    """
    task_id = generate_id()
    task = {
        "id": task_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "todo",
    }
    await save_to_db(task)
    return task
```

**Important:** The docstring is the tool's documentation. The LLM reads it to decide when and how to call the tool. Write clear descriptions and document every parameter.

### Input Validation

Use Python type hints and defaults. FastMCP auto-generates the JSON Schema:

```python
@mcp.tool()
async def list_tasks(
    tenant_id: str,
    status: str = "",
    priority: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List tasks with optional filters.

    Args:
        tenant_id: Tenant identifier (required for isolation).
        status: Filter by status. Empty string means all statuses.
        priority: Filter by priority. Empty string means all priorities.
        limit: Maximum number of results (1-200). Defaults to 50.
        offset: Pagination offset. Defaults to 0.
    """
    # Implementation
    ...
```

The generated schema looks like:

```json
{
  "name": "list_tasks",
  "description": "List tasks with optional filters.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "tenant_id": { "type": "string" },
      "status": { "type": "string", "default": "" },
      "priority": { "type": "string", "default": "" },
      "limit": { "type": "integer", "default": 50 },
      "offset": { "type": "integer", "default": 0 }
    },
    "required": ["tenant_id"]
  }
}
```

### Returning Errors

Return error information in the response body rather than raising exceptions:

```python
@mcp.tool()
async def update_task_status(task_id: str, new_status: str,
                             tenant_id: str = "") -> dict:
    """Update the status of a task."""
    valid_statuses = {"todo", "in_progress", "done", "blocked"}
    if new_status not in valid_statuses:
        return {"error": f"Invalid status '{new_status}'. Must be one of: {valid_statuses}"}

    task = await get_task(task_id, tenant_id)
    if not task:
        return {"error": f"Task '{task_id}' not found for this tenant"}

    task["status"] = new_status
    await save_to_db(task)
    return {"task_id": task_id, "status": new_status, "updated": True}
```

---

## Defining Resources

Resources are read-only data endpoints. They use URI templates:

```python
@mcp.resource("task://summary/{tenant_id}")
async def task_summary(tenant_id: str) -> str:
    """Return a plain-text summary of task statistics for the tenant."""
    stats = await get_task_stats(tenant_id)
    return (
        f"Total tasks: {stats['total']}\n"
        f"To Do: {stats['todo']}\n"
        f"In Progress: {stats['in_progress']}\n"
        f"Done: {stats['done']}\n"
        f"Blocked: {stats['blocked']}"
    )


@mcp.resource("task://detail/{tenant_id}/{task_id}")
async def task_detail(tenant_id: str, task_id: str) -> str:
    """Fetch the full detail of a single task as formatted text."""
    task = await get_task(task_id, tenant_id)
    if not task:
        return f"Task {task_id} not found."
    return f"Title: {task['title']}\nStatus: {task['status']}\nPriority: {task['priority']}"
```

**Resources vs. Tools:**
- Use **tools** when the action has side effects (create, update, delete).
- Use **resources** for read-only data retrieval that enriches context.

---

## Tenant Scoping

Every tool that accesses data **must** include a `tenant_id` parameter. This is the primary isolation mechanism in AgentOS:

```python
@mcp.tool()
async def delete_task(task_id: str, tenant_id: str) -> dict:
    """Delete a task. Scoped to the tenant."""
    deleted = await delete_from_db(task_id, tenant_id=tenant_id)
    if not deleted:
        return {"error": "Task not found or access denied"}
    return {"task_id": task_id, "deleted": True}
```

The framework middleware validates that `tenant_id` is present on every tool invocation. Missing tenant IDs are rejected before the tool function executes.

---

## Tool Registry

AgentOS maintains a central tool registry. When the app starts, it discovers all MCP servers and indexes their tools:

```python
from agentos.core.mcp_factory import get_tool_registry

registry = get_tool_registry()

# List all tools across all verticals
all_tools = registry.list_tools()

# Get tools for a specific vertical
task_tools = registry.list_tools(server="task-management")

# Look up a specific tool
tool = registry.get_tool("create_task")
```

This registry powers the `/api/v1/tools` endpoint and agent tool discovery.

---

## Health Check Pattern

Every MCP server should expose a health check tool:

```python
@mcp.tool()
async def health_check() -> dict:
    """Check the health of the task management tool server."""
    checks = {
        "database": await check_db_connection(),
        "server": "healthy",
    }
    all_healthy = all(v == "healthy" or v == "connected" for v in checks.values())
    return {
        "server": "task-management",
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
    }
```

The framework aggregates health checks from all MCP servers into the global `/health` endpoint.

---

## Connecting MCP to Agents

Agents automatically connect to their vertical's MCP server. You can also explicitly connect:

```python
from agentos.core.agent_factory import create_agent

agent = create_agent(
    name="task-agent",
    model="openai:gpt-4o",
    result_type=TaskAgentOutput,
    system_prompt_file="prompts/task_system.md",
    deps_type=TaskAgentDeps,
    mcp_servers=["task-management"],  # explicit MCP server binding
)
```

The agent will see all tools from the specified MCP servers.

---

## Testing MCP Tools

```python
import pytest


@pytest.mark.asyncio
async def test_create_task_tool():
    result = await create_task(
        title="Write tests",
        description="Unit tests for MCP tools",
        priority="high",
    )
    assert "id" in result
    assert result["status"] == "todo"


@pytest.mark.asyncio
async def test_invalid_status_returns_error():
    result = await update_task_status(
        task_id="task-1",
        new_status="invalid",
        tenant_id="test",
    )
    assert "error" in result
```

---

## Summary

| Concept | Pattern |
|---------|---------|
| Create server | `create_mcp_server(name, description)` |
| Define tool | `@mcp.tool()` with typed params and docstring |
| Define resource | `@mcp.resource(uri_template)` for read-only data |
| Tenant isolation | Always require `tenant_id` parameter |
| Error handling | Return `{"error": "..."}` dicts |
| Health checks | Dedicated `health_check` tool per server |
| Discovery | Central tool registry, auto-indexed at startup |
