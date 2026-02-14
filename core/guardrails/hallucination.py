"""
AgentOS Hallucination Guardrails

4-layer defense against hallucination:
1. Grounded RAG only — responses must cite retrieved sources
2. Confidence thresholds — low confidence triggers review
3. In-domain checks — reject out-of-scope questions
4. Explicit "I don't know" — when evidence is missing
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from ..agents.base_agent import AgentOutput


class GuardrailResult(BaseModel):
    """Result of guardrail checks."""
    passed: bool
    checks_run: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)
    original_confidence: float
    adjusted_confidence: float
    action: str  # pass | flag_review | reject | idk


def check_grounding(output: AgentOutput, min_sources: int = 1) -> GuardrailResult:
    """Layer 1: Ensure response is grounded in sources."""
    passed = len(output.sources) >= min_sources
    return GuardrailResult(
        passed=passed,
        checks_run=["grounding"],
        checks_failed=[] if passed else ["grounding"],
        original_confidence=output.confidence,
        adjusted_confidence=output.confidence if passed else min(output.confidence, 0.3),
        action="pass" if passed else "flag_review",
    )


def check_confidence(output: AgentOutput, threshold: float = 0.7) -> GuardrailResult:
    """Layer 2: Confidence threshold gate."""
    passed = output.confidence >= threshold
    return GuardrailResult(
        passed=passed,
        checks_run=["confidence"],
        checks_failed=[] if passed else ["confidence"],
        original_confidence=output.confidence,
        adjusted_confidence=output.confidence,
        action="pass" if passed else "flag_review",
    )


def check_in_domain(
    query: str,
    allowed_domains: list[str],
    output: AgentOutput,
) -> GuardrailResult:
    """Layer 3: Reject out-of-scope questions."""
    query_lower = query.lower()
    in_domain = any(
        domain.lower() in query_lower
        for domain in allowed_domains
    )
    # Also pass if confidence is very high (agent is sure)
    if not in_domain and output.confidence > 0.9:
        in_domain = True

    return GuardrailResult(
        passed=in_domain,
        checks_run=["in_domain"],
        checks_failed=[] if in_domain else ["in_domain"],
        original_confidence=output.confidence,
        adjusted_confidence=output.confidence if in_domain else 0.0,
        action="pass" if in_domain else "reject",
    )


def apply_all_guardrails(
    query: str,
    output: AgentOutput,
    allowed_domains: list[str] = None,
    confidence_threshold: float = 0.7,
    min_sources: int = 1,
) -> tuple[AgentOutput, GuardrailResult]:
    """
    Run all guardrail layers. Returns modified output + result.
    """
    all_checks = []
    all_failed = []
    min_confidence = output.confidence
    action = "pass"

    # Layer 1: Grounding
    g1 = check_grounding(output, min_sources)
    all_checks.extend(g1.checks_run)
    all_failed.extend(g1.checks_failed)
    min_confidence = min(min_confidence, g1.adjusted_confidence)
    if g1.action != "pass":
        action = g1.action

    # Layer 2: Confidence
    g2 = check_confidence(output, confidence_threshold)
    all_checks.extend(g2.checks_run)
    all_failed.extend(g2.checks_failed)
    if g2.action != "pass" and action == "pass":
        action = g2.action

    # Layer 3: Domain check (if domains specified)
    if allowed_domains:
        g3 = check_in_domain(query, allowed_domains, output)
        all_checks.extend(g3.checks_run)
        all_failed.extend(g3.checks_failed)
        min_confidence = min(min_confidence, g3.adjusted_confidence)
        if g3.action == "reject":
            action = "reject"

    # Layer 4: Explicit IDK
    if action == "reject" or min_confidence == 0.0:
        action = "idk"
        output.response = (
            "I don't have enough information to answer this question confidently. "
            "This may be outside my current knowledge scope."
        )
        output.confidence = 0.0
        output.requires_review = True

    # Apply adjustments
    output.confidence = min_confidence
    if action == "flag_review":
        output.requires_review = True

    result = GuardrailResult(
        passed=action == "pass",
        checks_run=all_checks,
        checks_failed=all_failed,
        original_confidence=g1.original_confidence,
        adjusted_confidence=min_confidence,
        action=action,
    )

    return output, result
