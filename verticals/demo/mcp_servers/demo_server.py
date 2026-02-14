"""Demo MCP Server — Task Management Tools."""
from fastmcp import FastMCP
from datetime import datetime
from typing import Optional
from ..models.schemas import Task, TaskCreate, TaskUpdate, Priority, TaskStatus
import uuid

mcp = FastMCP("task-manager")

# In-memory store (replace with DB in production)
_tasks: dict[str, Task] = {}


@mcp.tool()
def create_task(
    tenant_id: str,
    title: str,
    description: str = "",
    priority: str = "medium",
    assignee: str = None,
    tags: list[str] = None,
    deadline: str = None,
) -> dict:
    """Create a new task."""
    task = Task(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        title=title,
        description=description,
        priority=Priority(priority),
        assignee=assignee,
        tags=tags or [],
        deadline=datetime.fromisoformat(deadline) if deadline else None,
    )
    _tasks[task.id] = task
    return task.model_dump(mode="json")


@mcp.tool()
def get_task(task_id: str, tenant_id: str) -> dict:
    """Get a task by ID. Tenant-scoped."""
    task = _tasks.get(task_id)
    if not task or task.tenant_id != tenant_id:
        return {"error": "Task not found"}
    return task.model_dump(mode="json")


@mcp.tool()
def search_tasks(
    tenant_id: str,
    query: str = "",
    status: str = None,
    priority: str = None,
    assignee: str = None,
    limit: int = 10,
) -> dict:
    """Search tasks with filters. Tenant-scoped."""
    results = [t for t in _tasks.values() if t.tenant_id == tenant_id]

    if query:
        q = query.lower()
        results = [t for t in results if q in t.title.lower() or q in t.description.lower()]
    if status:
        results = [t for t in results if t.status.value == status]
    if priority:
        results = [t for t in results if t.priority.value == priority]
    if assignee:
        results = [t for t in results if t.assignee == assignee]

    results.sort(key=lambda t: t.created_at, reverse=True)
    return {"tasks": [t.model_dump(mode="json") for t in results[:limit]], "total": len(results)}


@mcp.tool()
def update_task(
    task_id: str,
    tenant_id: str,
    title: str = None,
    description: str = None,
    priority: str = None,
    status: str = None,
    assignee: str = None,
) -> dict:
    """Update a task. Tenant-scoped."""
    task = _tasks.get(task_id)
    if not task or task.tenant_id != tenant_id:
        return {"error": "Task not found"}

    if title:
        task.title = title
    if description:
        task.description = description
    if priority:
        task.priority = Priority(priority)
    if status:
        task.status = TaskStatus(status)
    if assignee is not None:
        task.assignee = assignee
    task.updated_at = datetime.utcnow()

    return task.model_dump(mode="json")
