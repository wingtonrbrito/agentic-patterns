"""
AgentOS Base Agent — Pydantic AI Foundation

Every agent in the framework inherits from this pattern:
- Type-safe outputs via Pydantic models
- Dependency injection for database, config, tools
- Built-in retry logic (replaces external workflow engines)
- Confidence scoring on all outputs
- Hallucination guardrails via grounded-only responses
"""
from __future__ import annotations
from pydantic_ai import Agent
from pydantic import BaseModel, Field
from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime
import uuid


class AgentOutput(BaseModel):
    """Standard output for all AgentOS agents."""
    response: str
    confidence: float = Field(ge=0.0, le=1.0, description="Output confidence score")
    sources: list[str] = Field(default_factory=list, description="Grounding sources")
    reasoning: Optional[str] = None
    requires_review: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)


@dataclass
class AgentDeps:
    """Shared dependencies injected into all agents."""
    tenant_id: str
    user_id: str
    db: Any = None          # Database connection
    redis: Any = None       # Cache/pub-sub
    vector_store: Any = None  # ChromaDB / pgvector
    config: dict = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}


def create_agent(
    name: str,
    system_prompt: str,
    result_type: type[BaseModel] = AgentOutput,
    model: str = "claude-sonnet-4-20250514",
    retries: int = 3,
    tools: list = None,
) -> Agent:
    """
    Factory function for creating AgentOS agents.

    Usage:
        agent = create_agent(
            name="research",
            system_prompt="You research topics thoroughly.",
            model="claude-sonnet-4-20250514",
        )
        result = await agent.run("Find info about X", deps=deps)
    """
    agent = Agent(
        model,
        result_type=result_type,
        system_prompt=system_prompt,
        deps_type=AgentDeps,
        retries=retries,
        name=name,
    )
    return agent


# --- Confidence Gating ---

def gate_confidence(output: AgentOutput, threshold: float = 0.7) -> AgentOutput:
    """
    Apply confidence gate to agent output.
    Low-confidence outputs are flagged for human review.
    """
    if output.confidence < threshold:
        output.requires_review = True
        output.metadata["gate_reason"] = f"Confidence {output.confidence:.2f} below threshold {threshold}"
    return output


def require_sources(output: AgentOutput, min_sources: int = 1) -> AgentOutput:
    """
    Ensure output is grounded in sources.
    Ungrounded outputs get flagged — prevents hallucination.
    """
    if len(output.sources) < min_sources:
        output.requires_review = True
        output.confidence = min(output.confidence, 0.5)
        output.metadata["gate_reason"] = f"Insufficient sources: {len(output.sources)} < {min_sources}"
    return output
