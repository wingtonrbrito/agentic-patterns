"""Test LLM router."""
import pytest
from core.llm.router import route_to_llm, TaskType, Complexity, LLMChoice


def test_route_high_reasoning():
    choice = route_to_llm(TaskType.REASONING, Complexity.HIGH)
    assert "claude" in choice.model
    assert choice.fallback is not None


def test_route_low_classification():
    choice = route_to_llm(TaskType.CLASSIFICATION, Complexity.LOW)
    assert "mini" in choice.model or "flash" in choice.model


def test_route_default_fallback():
    choice = route_to_llm(TaskType.SUMMARIZATION, Complexity.LOW)
    assert choice.model is not None
    assert choice.reason == "Default model"


def test_route_returns_llm_choice():
    choice = route_to_llm(TaskType.CODE, Complexity.HIGH)
    assert isinstance(choice, LLMChoice)
    assert choice.estimated_cost_per_1k_tokens > 0
