# Creating Verticals

A **vertical** is a self-contained domain module in AgentOS. Each vertical encapsulates its own models, MCP tools, AI agents, prompts, and tests. This guide walks through building one from scratch using the task management demo as a reference.

---

## Directory Structure

Every vertical follows a consistent layout:

```
agentos/verticals/task_management/
├── __init__.py
├── models/
│   ├── __init__.py
│   └── task.py              # Pydantic data models
├── mcp_servers/
│   ├── __init__.py
│   └── task_tools.py        # FastMCP tool server
├── agents/
│   ├── __init__.py
│   └── task_agent.py        # Pydantic AI agent
├── prompts/
│   └── task_system.md       # System prompt template
├── skills/
│   └── SKILL.md             # Skill manifest
├── routes.py                # FastAPI router
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_tools.py
    └── test_agent.py
```

---

## Step 1: Define Your Models

Models are Pydantic `BaseModel` classes that define the data contracts for your vertical.

```python
# agentos/verticals/task_management/models/task.py
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Optional


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class Task(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    assignee: Optional[str] = None
    tenant_id: str = Field(..., description="Tenant isolation key")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskCreate(BaseModel):
    """Input schema for creating a task."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee: Optional[str] = None


class TaskSummary(BaseModel):
    """Output schema for task summaries."""
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue_count: int = 0
```

**Guidelines:**
- Always include `tenant_id` on root entities for multi-tenant isolation.
- Separate input schemas (`TaskCreate`) from stored models (`Task`).
- Use `Field(...)` with descriptions -- these become tool parameter docs.

---

## Step 2: Create the MCP Server

The MCP server exposes tools that agents (and external clients) can call.

```python
# agentos/verticals/task_management/mcp_servers/task_tools.py
from agentos.core.mcp_factory import create_mcp_server
from ..models.task import Task, TaskCreate, TaskPriority

mcp = create_mcp_server("task-management", description="Task management tools")


@mcp.tool()
async def create_task(title: str, description: str = "", priority: str = "medium",
                      tenant_id: str = "") -> dict:
    """Create a new task in the system."""
    task = TaskCreate(title=title, description=description,
                      priority=TaskPriority(priority))
    # persist via repository layer
    return {"task_id": "generated-id", "status": "created"}


@mcp.tool()
async def list_tasks(tenant_id: str, status: str = "", limit: int = 50) -> list[dict]:
    """List tasks for a tenant, optionally filtered by status."""
    # query repository
    return []


@mcp.tool()
async def update_task_status(task_id: str, new_status: str,
                             tenant_id: str = "") -> dict:
    """Update the status of an existing task."""
    return {"task_id": task_id, "status": new_status}


@mcp.resource("task://summary/{tenant_id}")
async def task_summary(tenant_id: str) -> str:
    """Return a plain-text summary of all tasks for the tenant."""
    return f"Task summary for tenant {tenant_id}: 0 tasks"
```

See [MCP Guide](./mcp-guide.md) for details on the `create_mcp_server` factory.

---

## Step 3: Build the Agent

Agents use Pydantic AI to combine an LLM with your MCP tools and structured output.

```python
# agentos/verticals/task_management/agents/task_agent.py
from dataclasses import dataclass
from pydantic import BaseModel, Field
from agentos.core.agent_factory import create_agent, AgentOutput


@dataclass
class TaskAgentDeps:
    tenant_id: str
    user_id: str
    db_session: object  # your async DB session


class TaskAgentOutput(AgentOutput):
    """Structured output for the task agent."""
    tasks_affected: list[str] = Field(default_factory=list)
    action_taken: str = ""


agent = create_agent(
    "task-agent",
    model="openai:gpt-4o",
    result_type=TaskAgentOutput,
    system_prompt_file="agentos/verticals/task_management/prompts/task_system.md",
    deps_type=TaskAgentDeps,
)


@agent.tool
async def get_my_tasks(ctx) -> list[dict]:
    """Retrieve all tasks assigned to the current user."""
    deps: TaskAgentDeps = ctx.deps
    # query using deps.db_session filtered by deps.tenant_id
    return []
```

See [Pydantic AI Patterns](./pydantic-ai-patterns.md) for advanced patterns.

---

## Step 4: Register Routes

Expose your vertical through FastAPI routes:

```python
# agentos/verticals/task_management/routes.py
from fastapi import APIRouter, Depends
from .agents.task_agent import agent, TaskAgentDeps, TaskAgentOutput

router = APIRouter(prefix="/api/v1/tasks", tags=["task-management"])


@router.post("/chat", response_model=TaskAgentOutput)
async def chat(message: str, tenant_id: str = "default"):
    deps = TaskAgentDeps(tenant_id=tenant_id, user_id="demo", db_session=None)
    result = await agent.run(message, deps=deps)
    return result.data


@router.get("/health")
async def health():
    return {"vertical": "task-management", "status": "healthy"}
```

Then register the router in your app entrypoint:

```python
# In agentos/main.py
from agentos.verticals.task_management.routes import router as task_router
app.include_router(task_router)
```

---

## Step 5: Write the SKILL.md

The `SKILL.md` file is a structured manifest describing what your vertical can do. Agents and orchestrators read it to decide which vertical to route queries to.

```markdown
# Task Management

## Description
Manages tasks, assignments, priorities, and status tracking.

## Capabilities
- Create, update, and delete tasks
- List and filter tasks by status or priority
- Assign tasks to team members
- Summarize task backlogs

## Tools
- `create_task` -- Create a new task
- `list_tasks` -- List tasks with optional filters
- `update_task_status` -- Change task status

## Trigger Phrases
- "create a task"
- "show my tasks"
- "what's the status of..."
- "assign this to..."
```

---

## Step 6: Add Tests

```python
# agentos/verticals/task_management/tests/test_models.py
from ..models.task import Task, TaskCreate, TaskPriority

def test_task_create_validation():
    task = TaskCreate(title="Write docs", priority=TaskPriority.HIGH)
    assert task.title == "Write docs"
    assert task.priority == TaskPriority.HIGH

def test_task_requires_title():
    import pytest
    with pytest.raises(Exception):
        TaskCreate(title="")
```

```python
# agentos/verticals/task_management/tests/test_agent.py
import pytest
from ..agents.task_agent import agent, TaskAgentDeps

@pytest.mark.asyncio
async def test_agent_responds():
    deps = TaskAgentDeps(tenant_id="test", user_id="tester", db_session=None)
    result = await agent.run("List my tasks", deps=deps)
    assert result.data.confidence >= 0.0
```

---

## Checklist

- [ ] Models defined with Pydantic, including `tenant_id`
- [ ] MCP server created with `create_mcp_server`
- [ ] Agent created with `create_agent` and structured output
- [ ] Routes registered in `main.py`
- [ ] `SKILL.md` written with capabilities and trigger phrases
- [ ] Tests cover models, tools, and agent invocation
- [ ] System prompt stored in `prompts/` directory
