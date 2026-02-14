# Pydantic AI Patterns

AgentOS agents are built on [Pydantic AI](https://ai.pydantic.dev/). This guide covers the patterns and conventions used throughout the framework.

---

## The `create_agent` Factory

All agents are created through the `create_agent` helper, which standardizes configuration:

```python
from agentos.core.agent_factory import create_agent, AgentOutput
from dataclasses import dataclass


agent = create_agent(
    name="task-agent",
    model="openai:gpt-4o",
    result_type=TaskAgentOutput,       # structured output schema
    system_prompt_file="prompts/task_system.md",
    deps_type=TaskAgentDeps,
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique agent identifier |
| `model` | `str` | LLM model string (e.g., `openai:gpt-4o`) |
| `result_type` | `type[AgentOutput]` | Pydantic model for structured output |
| `system_prompt_file` | `str` | Path to the markdown system prompt |
| `deps_type` | `type` | Dataclass type for dependency injection |

---

## AgentOutput Model

Every agent returns a structured `AgentOutput` (or subclass). This base class provides consistent fields across all verticals:

```python
from pydantic import BaseModel, Field
from typing import Optional


class AgentOutput(BaseModel):
    """Base output model for all AgentOS agents."""
    answer: str = Field(..., description="The agent's natural language response")
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence score between 0 and 1"
    )
    sources: list[str] = Field(
        default_factory=list,
        description="List of source references used"
    )
    reasoning: Optional[str] = Field(
        None, description="Chain-of-thought reasoning trace"
    )
```

### Extending AgentOutput

Add domain-specific fields by subclassing:

```python
class TaskAgentOutput(AgentOutput):
    tasks_affected: list[str] = Field(default_factory=list)
    action_taken: str = Field(default="", description="What the agent did")
    suggestions: list[str] = Field(default_factory=list)
```

The LLM is instructed to populate all fields. The `confidence` score is always present, enabling downstream gating.

---

## Dependency Injection with AgentDeps

Dependencies are passed to every tool call via a `deps` dataclass:

```python
from dataclasses import dataclass


@dataclass
class TaskAgentDeps:
    tenant_id: str          # multi-tenant isolation
    user_id: str            # current user context
    db_session: object      # async database session
    search_engine: object   # hybrid search instance (optional)
```

**Why dataclasses?** Pydantic AI requires deps to be a dataclass (not a Pydantic model). This is a framework constraint.

### Injecting at Runtime

```python
deps = TaskAgentDeps(
    tenant_id=request.headers["X-Tenant-ID"],
    user_id=current_user.id,
    db_session=db,
    search_engine=search,
)

result = await agent.run("Show my blocked tasks", deps=deps)
output: TaskAgentOutput = result.data
```

---

## Tool Registration

### Basic Tool

```python
@agent.tool
async def list_tasks(ctx) -> list[dict]:
    """List all tasks for the current tenant.

    Returns a list of task objects with id, title, status, and priority.
    """
    deps: TaskAgentDeps = ctx.deps
    tasks = await fetch_tasks(deps.db_session, tenant_id=deps.tenant_id)
    return [t.model_dump() for t in tasks]
```

**Rules:**
- First parameter is always `ctx` (the run context).
- Access deps via `ctx.deps`.
- The docstring becomes the tool description the LLM sees -- write it clearly.
- Return JSON-serializable data.

### Tool with Parameters

```python
@agent.tool
async def search_tasks(ctx, query: str, status: str = "") -> list[dict]:
    """Search tasks by keyword, optionally filtered by status.

    Args:
        query: Search keywords to match against task titles and descriptions.
        status: Filter by status (todo, in_progress, done, blocked). Empty for all.
    """
    deps: TaskAgentDeps = ctx.deps
    results = await deps.search_engine.search(
        query=query,
        tenant_id=deps.tenant_id,
        filters={"status": status} if status else {},
    )
    return results
```

### Tool Error Handling

```python
@agent.tool
async def assign_task(ctx, task_id: str, assignee: str) -> dict:
    """Assign a task to a team member."""
    deps: TaskAgentDeps = ctx.deps
    task = await get_task(deps.db_session, task_id, deps.tenant_id)
    if not task:
        return {"error": f"Task {task_id} not found"}
    task.assignee = assignee
    await save_task(deps.db_session, task)
    return {"task_id": task_id, "assignee": assignee, "status": "assigned"}
```

Return error dicts rather than raising exceptions -- this lets the LLM interpret the error and respond gracefully.

---

## Confidence Scoring

The `confidence` field on `AgentOutput` is populated by the LLM. To enforce quality, use gating functions:

### `gate_confidence`

Reject low-confidence responses:

```python
from agentos.core.agent_factory import gate_confidence

result = await agent.run("Summarize all critical tasks", deps=deps)
output = gate_confidence(result.data, threshold=0.7)
# Raises LowConfidenceError if output.confidence < 0.7
```

### `require_sources`

Ensure the agent cited its sources:

```python
from agentos.core.agent_factory import require_sources

output = require_sources(result.data, min_sources=1)
# Raises MissingSourcesError if len(output.sources) < 1
```

### Combined Gating

```python
output = result.data
output = gate_confidence(output, threshold=0.7)
output = require_sources(output, min_sources=1)
# Both checks pass -- safe to return to the user
```

---

## System Prompts

System prompts are stored as Markdown files:

```markdown
<!-- prompts/task_system.md -->
# Task Management Agent

You are a task management assistant. You help users create, organize,
and track their tasks.

## Rules
- Always scope queries to the current tenant.
- When creating tasks, confirm the title and priority with the user.
- If a request is ambiguous, ask for clarification.
- Provide your confidence score honestly -- lower is fine when uncertain.

## Output Format
Return structured JSON matching the TaskAgentOutput schema.
Always include your reasoning in the `reasoning` field.
```

Prompts support Jinja2 template variables if needed:

```markdown
You are assisting tenant {{ tenant_id }} with their tasks.
```

---

## Supervisor Pattern

For complex verticals, a **supervisor agent** orchestrates multiple specialist agents:

```python
supervisor = create_agent(
    name="task-supervisor",
    model="openai:gpt-4o",
    result_type=SupervisorOutput,
    system_prompt_file="prompts/supervisor.md",
    deps_type=SupervisorDeps,
)


@supervisor.tool
async def delegate_to_search(ctx, query: str) -> dict:
    """Delegate a search query to the search specialist agent."""
    result = await search_agent.run(query, deps=ctx.deps)
    return result.data.model_dump()


@supervisor.tool
async def delegate_to_writer(ctx, instruction: str) -> dict:
    """Delegate a task creation request to the writer agent."""
    result = await writer_agent.run(instruction, deps=ctx.deps)
    return result.data.model_dump()
```

The supervisor reads the user's intent, delegates to the right specialist, and synthesizes the final response. This is useful when a single prompt would be too overloaded.

---

## Testing Agents

```python
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_task_agent_returns_structured_output():
    deps = TaskAgentDeps(
        tenant_id="test-tenant",
        user_id="test-user",
        db_session=AsyncMock(),
        search_engine=AsyncMock(),
    )
    result = await agent.run("What tasks are blocked?", deps=deps)
    output = result.data

    assert isinstance(output, TaskAgentOutput)
    assert 0.0 <= output.confidence <= 1.0
    assert output.answer  # non-empty response
```

---

## Quick Reference

| Pattern | When to Use |
|---------|-------------|
| `create_agent` | Always -- standardized agent creation |
| `AgentOutput` subclass | Always -- structured, typed responses |
| `AgentDeps` dataclass | Always -- dependency injection |
| `@agent.tool` | Giving the agent callable capabilities |
| `gate_confidence` | Enforcing response quality thresholds |
| `require_sources` | Ensuring citations in RAG scenarios |
| Supervisor pattern | Multi-step or multi-specialist workflows |
