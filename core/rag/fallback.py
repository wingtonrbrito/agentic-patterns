"""
AgentOS Three-Tier Fallback

Tier 1: RAG retrieval (highest confidence)
Tier 2: LLM with context (medium confidence)
Tier 3: Explicit "I don't know" (zero hallucination)

Never hallucinate. Always be honest about confidence.
"""
from __future__ import annotations
from pydantic_ai import Agent
from ..agents.base_agent import AgentOutput, AgentDeps


async def answer_with_fallback(
    query: str,
    deps: AgentDeps,
    search_engine=None,
    agent: Agent = None,
    rag_threshold: float = 0.7,
    llm_threshold: float = 0.5,
) -> AgentOutput:
    """
    Three-tier answer strategy. Falls back gracefully.
    """

    # Tier 1: RAG retrieval
    if search_engine:
        search_result = await search_engine.search(
            query=query,
            tenant_id=deps.tenant_id,
            top_k=5,
        )
        if search_result.results and search_result.results[0].score > rag_threshold:
            top_results = search_result.results[:3]
            context = "\n\n".join(r.content for r in top_results)
            sources = [r.id for r in top_results]

            if agent:
                result = await agent.run(
                    f"Answer based on this context:\n\n{context}\n\nQuestion: {query}",
                    deps=deps,
                )
                output = result.data
                output.sources = sources
                return output

            return AgentOutput(
                response=context,
                confidence=top_results[0].score,
                sources=sources,
            )

    # Tier 2: Direct LLM (lower confidence — no grounding)
    if agent:
        result = await agent.run(query, deps=deps)
        output = result.data
        if output.confidence > llm_threshold:
            output.metadata["tier"] = "llm_direct"
            return output

    # Tier 3: Explicit "I don't know"
    return AgentOutput(
        response="I don't have enough information to answer this question confidently. "
                 "Could you provide more context or rephrase your question?",
        confidence=0.0,
        sources=[],
        requires_review=True,
        metadata={"tier": "fallback", "reason": "No confident answer available"},
    )
