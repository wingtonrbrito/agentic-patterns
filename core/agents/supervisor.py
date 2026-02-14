"""
AgentOS Supervisor — Multi-Agent Workflow Orchestration

Orchestrates complex multi-step tasks by composing agents.
Uses Pydantic AI's built-in patterns instead of external workflow engines.

Pattern: Supervisor agent has tools that delegate to specialist agents.
The supervisor decides which agents to call, in what order, and how to
synthesize their outputs into a final result.
"""
from __future__ import annotations
from pydantic_ai import Agent
from pydantic import BaseModel, Field
from typing import Optional
from .base_agent import AgentDeps, AgentOutput, gate_confidence
from .verifier import verify_output


class WorkflowStep(BaseModel):
    """Single step in a supervised workflow."""
    step_number: int
    agent_name: str
    input_summary: str
    output_summary: str
    confidence: float
    duration_ms: Optional[int] = None


class SupervisorResult(BaseModel):
    """Result of a supervised multi-agent workflow."""
    final_response: str
    confidence: float = Field(ge=0.0, le=1.0)
    steps_completed: list[WorkflowStep] = Field(default_factory=list)
    total_steps: int = 0
    verified: bool = False
    verification_score: Optional[float] = None
    sources: list[str] = Field(default_factory=list)


def create_supervisor(
    name: str,
    specialist_agents: dict[str, Agent],
    system_prompt: str = None,
    model: str = "claude-sonnet-4-20250514",
    verify_output_flag: bool = True,
) -> Agent:
    """
    Create a supervisor agent that orchestrates specialist agents.

    Args:
        name: Supervisor name
        specialist_agents: Dict of name -> Agent for specialists
        system_prompt: Override default supervisor prompt
        model: LLM model to use
        verify_output_flag: Whether to verify final output
    """
    if not system_prompt:
        agent_list = "\n".join(
            f"- {name}: Use for {name}-related tasks"
            for name in specialist_agents
        )
        system_prompt = f"""You are a workflow supervisor. You orchestrate tasks by delegating to specialist agents.

Available specialists:
{agent_list}

For each task:
1. Break it into steps
2. Delegate each step to the right specialist
3. Synthesize results into a coherent final response
4. Ensure all claims are grounded in specialist outputs"""

    supervisor = Agent(
        model,
        result_type=SupervisorResult,
        system_prompt=system_prompt,
        deps_type=AgentDeps,
        retries=3,
        name=name,
    )

    # Register specialist agents as tools
    for agent_name, specialist in specialist_agents.items():
        _register_specialist_tool(supervisor, agent_name, specialist)

    return supervisor


def _register_specialist_tool(
    supervisor: Agent,
    specialist_name: str,
    specialist: Agent,
):
    """Register a specialist agent as a tool on the supervisor."""

    @supervisor.tool(name=f"delegate_to_{specialist_name}")
    async def delegate(ctx, task: str) -> str:
        """Delegate a task to a specialist agent."""
        result = await specialist.run(task, deps=ctx.deps)
        output = result.data
        if hasattr(output, 'response'):
            return f"[{specialist_name}] {output.response} (confidence: {output.confidence:.2f})"
        return f"[{specialist_name}] {str(output)}"
