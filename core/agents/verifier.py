"""
AgentOS Verifier — LLM-as-Judge Output Validation

Validates agent outputs for:
- Factual grounding (are claims supported by sources?)
- Hallucination detection (did the agent make things up?)
- Completeness (did the agent address the full query?)
- Safety (is the output appropriate?)
"""
from __future__ import annotations
from pydantic_ai import Agent
from pydantic import BaseModel, Field
from .base_agent import AgentDeps


class VerificationResult(BaseModel):
    """Result of output verification."""
    is_valid: bool
    overall_score: float = Field(ge=0.0, le=1.0)
    grounding_score: float = Field(ge=0.0, le=1.0, description="Are claims supported?")
    completeness_score: float = Field(ge=0.0, le=1.0, description="Was the query fully addressed?")
    safety_score: float = Field(ge=0.0, le=1.0, description="Is output appropriate?")
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


VERIFIER_PROMPT = """You are a quality assurance judge for AI agent outputs.

Given an original query, the agent's response, and the sources used, evaluate:

1. **Grounding** (0-1): Are all claims in the response supported by the provided sources?
   - 1.0 = every claim has a source
   - 0.5 = some claims are unsupported
   - 0.0 = response is mostly fabricated

2. **Completeness** (0-1): Does the response fully address the query?
   - 1.0 = query fully answered
   - 0.5 = partially answered
   - 0.0 = query not addressed

3. **Safety** (0-1): Is the output appropriate and harmless?
   - 1.0 = completely safe
   - 0.0 = contains harmful or inappropriate content

Set is_valid=True if overall_score >= 0.7 and no critical issues found."""


verifier_agent = Agent(
    "claude-sonnet-4-20250514",
    result_type=VerificationResult,
    system_prompt=VERIFIER_PROMPT,
    deps_type=AgentDeps,
    retries=2,
    name="verifier",
)


async def verify_output(
    query: str,
    response: str,
    sources: list[str],
    deps: AgentDeps,
) -> VerificationResult:
    """Verify an agent's output using LLM-as-Judge."""
    verification_input = f"""
Original Query: {query}

Agent Response: {response}

Sources Used: {chr(10).join(f'- {s}' for s in sources) if sources else 'No sources provided'}

Evaluate the response quality."""

    result = await verifier_agent.run(verification_input, deps=deps)
    return result.data
