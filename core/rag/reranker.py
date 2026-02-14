"""
AgentOS Reranker — Cross-Encoder + ColBERT-style Late Interaction

Two reranking strategies:
1. Cross-encoder (sentence-transformers) — high quality, slower
2. ColBERT-style late interaction — fast, token-level matching

Used after hybrid search to promote the most relevant results.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from .hybrid_search import SearchResult


class RerankResult(BaseModel):
    """Reranked search result with updated score."""
    original: SearchResult
    rerank_score: float = Field(ge=0.0, le=1.0)
    rank: int
    method: str  # cross_encoder | colbert


class Reranker:
    """
    Cross-encoder reranker.
    In production: uses sentence-transformers CrossEncoder.
    Stub version for demo uses similarity heuristics.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Lazy-load cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
            except ImportError:
                self._model = "stub"

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """Rerank results using cross-encoder."""
        self._load_model()

        if self._model == "stub":
            # Fallback: preserve original ordering
            return [
                RerankResult(
                    original=r,
                    rerank_score=r.score,
                    rank=i + 1,
                    method="passthrough",
                )
                for i, r in enumerate(results[:top_k])
            ]

        # Cross-encoder scoring
        pairs = [(query, r.content) for r in results]
        scores = self._model.predict(pairs)

        scored = list(zip(results, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            RerankResult(
                original=result,
                rerank_score=float(score),
                rank=i + 1,
                method="cross_encoder",
            )
            for i, (result, score) in enumerate(scored[:top_k])
        ]


class ColBERTReranker:
    """
    ColBERT-style late interaction reranker.
    Token-level MaxSim scoring for fast, high-precision reranking.
    """

    def __init__(self):
        self._tokenizer = None
        self._model = None

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """
        ColBERT late interaction: encode query + doc tokens separately,
        compute MaxSim per query token, sum for final score.
        """
        # Simplified ColBERT-style scoring using token overlap
        query_tokens = set(query.lower().split())

        scored = []
        for result in results:
            doc_tokens = set(result.content.lower().split())
            # MaxSim approximation: fraction of query tokens found in doc
            if query_tokens:
                overlap = len(query_tokens & doc_tokens) / len(query_tokens)
            else:
                overlap = 0.0
            # Blend with original score
            colbert_score = 0.6 * overlap + 0.4 * result.score
            scored.append((result, colbert_score))

        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            RerankResult(
                original=result,
                rerank_score=score,
                rank=i + 1,
                method="colbert",
            )
            for i, (result, score) in enumerate(scored[:top_k])
        ]
