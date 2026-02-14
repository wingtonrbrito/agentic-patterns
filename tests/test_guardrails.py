"""Test hallucination guardrails."""
import pytest
from core.agents.base_agent import AgentOutput
from core.guardrails.hallucination import (
    check_grounding, check_confidence, check_in_domain, apply_all_guardrails
)


def test_grounding_passes_with_sources():
    output = AgentOutput(response="test", confidence=0.9, sources=["doc1"])
    result = check_grounding(output)
    assert result.passed


def test_grounding_fails_without_sources():
    output = AgentOutput(response="test", confidence=0.9, sources=[])
    result = check_grounding(output)
    assert not result.passed


def test_confidence_gate():
    high = AgentOutput(response="test", confidence=0.9)
    low = AgentOutput(response="test", confidence=0.3)
    assert check_confidence(high).passed
    assert not check_confidence(low).passed


def test_in_domain_check():
    output = AgentOutput(response="test", confidence=0.5)
    result = check_in_domain("task management tips", ["task", "project"], output)
    assert result.passed

    result2 = check_in_domain("weather forecast", ["task", "project"], output)
    assert not result2.passed


def test_in_domain_high_confidence_bypass():
    output = AgentOutput(response="test", confidence=0.95)
    result = check_in_domain("unrelated query", ["task"], output)
    assert result.passed  # High confidence bypasses domain check


def test_full_guardrails_idk():
    output = AgentOutput(response="made up answer", confidence=0.3, sources=[])
    modified, result = apply_all_guardrails(
        query="unrelated question",
        output=output,
        allowed_domains=["task"],
        confidence_threshold=0.7,
    )
    assert result.action == "idk"
    assert "don't have enough information" in modified.response


def test_full_guardrails_pass():
    output = AgentOutput(response="grounded answer", confidence=0.9, sources=["doc1"])
    modified, result = apply_all_guardrails(
        query="task management help",
        output=output,
        allowed_domains=["task"],
        confidence_threshold=0.7,
    )
    assert result.passed
    assert result.action == "pass"


def test_full_guardrails_flag_review():
    output = AgentOutput(response="ok answer", confidence=0.5, sources=["doc1"])
    modified, result = apply_all_guardrails(
        query="task help",
        output=output,
        allowed_domains=["task"],
        confidence_threshold=0.7,
    )
    assert result.action == "flag_review"
    assert modified.requires_review


def test_grounding_adjusts_confidence():
    output = AgentOutput(response="test", confidence=0.9, sources=[])
    result = check_grounding(output)
    assert result.adjusted_confidence <= 0.3
