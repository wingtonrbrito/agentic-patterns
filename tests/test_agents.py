"""Test core agent patterns."""
import pytest
from core.agents.base_agent import AgentOutput, AgentDeps, gate_confidence, require_sources
from core.agents.router import AgentRouter, AgentRoute


def test_agent_output_defaults():
    output = AgentOutput(response="test", confidence=0.8)
    assert output.response == "test"
    assert output.confidence == 0.8
    assert output.sources == []
    assert not output.requires_review


def test_confidence_gate_passes():
    output = AgentOutput(response="test", confidence=0.9)
    gated = gate_confidence(output, threshold=0.7)
    assert not gated.requires_review


def test_confidence_gate_flags():
    output = AgentOutput(response="test", confidence=0.5)
    gated = gate_confidence(output, threshold=0.7)
    assert gated.requires_review


def test_require_sources_passes():
    output = AgentOutput(response="test", confidence=0.9, sources=["doc1"])
    checked = require_sources(output, min_sources=1)
    assert not checked.requires_review


def test_require_sources_flags():
    output = AgentOutput(response="test", confidence=0.9, sources=[])
    checked = require_sources(output, min_sources=1)
    assert checked.requires_review
    assert checked.confidence <= 0.5


def test_router_keyword_match():
    router = AgentRouter()
    router.register(AgentRoute(
        name="task",
        description="Task management",
        keywords=["task", "todo", "assign"],
    ))
    result = router.keyword_match("Create a new task for me")
    assert result is not None
    assert result.agent_name == "task"
    assert result.routing_method == "keyword"


def test_router_no_match():
    router = AgentRouter()
    router.register(AgentRoute(
        name="task",
        description="Task management",
        keywords=["task"],
    ))
    result = router.keyword_match("What is the weather?")
    assert result is None


def test_router_regex_match():
    router = AgentRouter()
    router.register(AgentRoute(
        name="search",
        description="Search engine",
        patterns=[r"find\s+\w+", r"search\s+for"],
    ))
    result = router.keyword_match("find documents about AI")
    assert result is not None
    assert result.agent_name == "search"


def test_router_priority_ordering():
    router = AgentRouter()
    router.register(AgentRoute(name="low", description="Low", keywords=["help"], priority=1))
    router.register(AgentRoute(name="high", description="High", keywords=["help"], priority=10))
    result = router.keyword_match("I need help")
    assert result.agent_name == "high"


def test_agent_deps_defaults():
    deps = AgentDeps(tenant_id="T1", user_id="U1")
    assert deps.tenant_id == "T1"
    assert deps.config == {}
    assert deps.db is None


def test_agent_output_trace_id_unique():
    o1 = AgentOutput(response="a", confidence=0.5)
    o2 = AgentOutput(response="b", confidence=0.5)
    assert o1.trace_id != o2.trace_id
