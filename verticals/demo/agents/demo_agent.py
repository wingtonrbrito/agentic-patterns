"""Demo Agent — Task Management with all AgentOS patterns."""
from pydantic_ai import Agent
from pydantic import BaseModel, Field
from typing import Optional
from core.agents.base_agent import AgentOutput, AgentDeps, create_agent, gate_confidence


class TaskAgentOutput(AgentOutput):
    """Extended output for task operations."""
    action_taken: Optional[str] = None  # created | updated | searched | none
    task_id: Optional[str] = None
    tasks_found: int = 0


# Create the task management agent
task_agent = create_agent(
    name="task_manager",
    system_prompt="""You are a task management assistant. Help users organize their work.

When creating tasks, extract all relevant fields from the user's message.
When searching, use appropriate filters.
When updating, confirm changes before applying.

Always be concise and action-oriented.""",
    result_type=TaskAgentOutput,
)


# Register MCP tools as agent tools
@task_agent.tool
async def create_new_task(ctx, title: str, description: str = "", priority: str = "medium") -> str:
    """Create a new task for the user."""
    from ..mcp_servers.demo_server import create_task
    result = create_task(
        tenant_id=ctx.deps.tenant_id,
        title=title,
        description=description,
        priority=priority,
    )
    return f"Created task: {result['title']} (ID: {result['id']}, Priority: {result['priority']})"


@task_agent.tool
async def find_tasks(ctx, query: str = "", status: str = None, priority: str = None) -> str:
    """Search for tasks matching criteria."""
    from ..mcp_servers.demo_server import search_tasks
    result = search_tasks(
        tenant_id=ctx.deps.tenant_id,
        query=query,
        status=status,
        priority=priority,
    )
    tasks = result["tasks"]
    if not tasks:
        return "No tasks found matching your criteria."
    summary = "\n".join(
        f"- [{t['priority']}] {t['title']} ({t['status']})"
        for t in tasks[:5]
    )
    return f"Found {result['total']} tasks:\n{summary}"
