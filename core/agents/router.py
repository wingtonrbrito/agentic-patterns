"""
AgentOS Router — Intent Classification + Agent Selection

Two-tier routing:
1. Keyword fast-path (zero LLM calls for obvious intents)
2. LLM classification (for ambiguous queries)

Supports dynamic agent registration — verticals register their agents at startup.
"""
from __future__ import annotations
from pydantic_ai import Agent
from pydantic import BaseModel, Field
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field
import re


class RouteResult(BaseModel):
    """Result of intent classification."""
    agent_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    intent: str
    extracted_entities: dict = Field(default_factory=dict)
    routing_method: str = "keyword"  # keyword | llm


@dataclass
class AgentRoute:
    """Registered agent with trigger patterns."""
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)  # regex patterns
    handler: Optional[Callable] = None
    priority: int = 0  # higher = checked first


class AgentRouter:
    """Routes queries to the best agent."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.routes: list[AgentRoute] = []
        self.model = model
        self._llm_router = None

    def register(self, route: AgentRoute):
        """Register an agent route."""
        self.routes.append(route)
        self.routes.sort(key=lambda r: r.priority, reverse=True)

    def keyword_match(self, query: str) -> Optional[RouteResult]:
        """Fast-path: keyword matching (no LLM call)."""
        query_lower = query.lower()
        for route in self.routes:
            # Check keywords
            for keyword in route.keywords:
                if keyword.lower() in query_lower:
                    return RouteResult(
                        agent_name=route.name,
                        confidence=0.9,
                        intent=f"keyword_match:{keyword}",
                        routing_method="keyword",
                    )
            # Check regex patterns
            for pattern in route.patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return RouteResult(
                        agent_name=route.name,
                        confidence=0.85,
                        intent=f"pattern_match:{pattern}",
                        routing_method="keyword",
                    )
        return None

    async def route(self, query: str, deps=None) -> RouteResult:
        """Route a query: try keyword fast-path, fall back to LLM."""
        # Tier 1: Keyword fast-path
        result = self.keyword_match(query)
        if result and result.confidence > 0.8:
            return result

        # Tier 2: LLM classification
        if not self._llm_router:
            self._llm_router = Agent(
                self.model,
                result_type=RouteResult,
                system_prompt=self._build_routing_prompt(),
                retries=2,
            )

        llm_result = await self._llm_router.run(query, deps=deps)
        return llm_result.data

    def _build_routing_prompt(self) -> str:
        """Build routing prompt from registered agents."""
        agents_desc = "\n".join(
            f"- **{r.name}**: {r.description}" for r in self.routes
        )
        return f"""You are an intent classifier. Route the user query to the best agent.

Available agents:
{agents_desc}

Respond with the agent_name, your confidence (0-1), and the detected intent."""
