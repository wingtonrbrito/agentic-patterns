"""
AgentOS LLM Router — Multi-Model Selection

Routes to the best LLM based on task type, complexity, and cost constraints.
Supports Claude, GPT-4, Gemini with fallback chains.
"""
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class TaskType(str, Enum):
    REASONING = "reasoning"
    CLASSIFICATION = "classification"
    GENERATION = "generation"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    CODE = "code"


class Complexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LLMChoice(BaseModel):
    model: str
    reason: str
    estimated_cost_per_1k_tokens: float
    fallback: Optional[str] = None


# Model routing table
ROUTING_TABLE = {
    (TaskType.REASONING, Complexity.HIGH): LLMChoice(
        model="claude-sonnet-4-20250514",
        reason="Best reasoning quality",
        estimated_cost_per_1k_tokens=0.003,
        fallback="gpt-4o",
    ),
    (TaskType.REASONING, Complexity.MEDIUM): LLMChoice(
        model="claude-sonnet-4-20250514",
        reason="Good balance of quality and cost",
        estimated_cost_per_1k_tokens=0.003,
        fallback="gemini-2.0-flash",
    ),
    (TaskType.CLASSIFICATION, Complexity.LOW): LLMChoice(
        model="gpt-4o-mini",
        reason="Fast classification at low cost",
        estimated_cost_per_1k_tokens=0.00015,
        fallback="gemini-2.0-flash",
    ),
    (TaskType.GENERATION, Complexity.HIGH): LLMChoice(
        model="claude-sonnet-4-20250514",
        reason="Best generation quality",
        estimated_cost_per_1k_tokens=0.003,
    ),
    (TaskType.EXTRACTION, Complexity.LOW): LLMChoice(
        model="gemini-2.0-flash",
        reason="Fast extraction, low cost",
        estimated_cost_per_1k_tokens=0.0001,
    ),
    (TaskType.CODE, Complexity.HIGH): LLMChoice(
        model="claude-sonnet-4-20250514",
        reason="Best code generation",
        estimated_cost_per_1k_tokens=0.003,
    ),
}


def route_to_llm(
    task_type: TaskType,
    complexity: Complexity = Complexity.MEDIUM,
) -> LLMChoice:
    """Select the best LLM for the task."""
    key = (task_type, complexity)
    if key in ROUTING_TABLE:
        return ROUTING_TABLE[key]

    # Default fallback
    return LLMChoice(
        model="claude-sonnet-4-20250514",
        reason="Default model",
        estimated_cost_per_1k_tokens=0.003,
    )
