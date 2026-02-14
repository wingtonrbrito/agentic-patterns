"""
AgentOS Hybrid Search — Dense + Sparse + Fusion

Three-stage retrieval:
1. Dense search (sentence-transformers embeddings via ChromaDB/pgvector)
2. Sparse search (BM25 for exact terminology)
3. Reciprocal Rank Fusion (RRF) to combine results

Tenant-aware: all searches scoped by tenant_id metadata filter.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from rank_bm25 import BM25Okapi
import numpy as np


class SearchResult(BaseModel):
    """Single search result with score and metadata."""
    id: str
    content: str
    score: float
    source: str  # dense | sparse | fused
    metadata: dict = Field(default_factory=dict)


class HybridSearchResult(BaseModel):
    """Combined search results with fusion scores."""
    query: str
    results: list[SearchResult]
    dense_count: int
    sparse_count: int
    fused_count: int
    tenant_id: str


class HybridSearchEngine:
    """
    Hybrid search combining dense embeddings + BM25 sparse retrieval.
    Results fused using Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        vector_store=None,
        k: int = 60,  # RRF constant
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
    ):
        self.vector_store = vector_store
        self.k = k
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self._bm25_index: Optional[BM25Okapi] = None
        self._corpus: list[dict] = []

    def index_documents(self, documents: list[dict]):
        """Build BM25 index from documents."""
        self._corpus = documents
        tokenized = [doc["content"].lower().split() for doc in documents]
        self._bm25_index = BM25Okapi(tokenized)

    async def search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10,
    ) -> HybridSearchResult:
        """Execute hybrid search: dense + sparse + RRF fusion."""

        # Stage 1: Dense search (vector similarity)
        dense_results = await self._dense_search(query, tenant_id, top_k=top_k * 2)

        # Stage 2: Sparse search (BM25)
        sparse_results = self._sparse_search(query, tenant_id, top_k=top_k * 2)

        # Stage 3: Reciprocal Rank Fusion
        fused = self._rrf_fusion(dense_results, sparse_results, top_k=top_k)

        return HybridSearchResult(
            query=query,
            results=fused,
            dense_count=len(dense_results),
            sparse_count=len(sparse_results),
            fused_count=len(fused),
            tenant_id=tenant_id,
        )

    async def _dense_search(
        self, query: str, tenant_id: str, top_k: int
    ) -> list[SearchResult]:
        """Dense vector search via ChromaDB/pgvector."""
        if not self.vector_store:
            return []

        results = self.vector_store.query(
            query_texts=[query],
            n_results=top_k,
            where={"tenant_id": tenant_id},
        )

        search_results = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                search_results.append(SearchResult(
                    id=results["ids"][0][i] if results.get("ids") else f"dense-{i}",
                    content=doc,
                    score=1.0 - (results["distances"][0][i] if results.get("distances") else 0),
                    source="dense",
                    metadata=results["metadatas"][0][i] if results.get("metadatas") else {},
                ))
        return search_results

    def _sparse_search(
        self, query: str, tenant_id: str, top_k: int
    ) -> list[SearchResult]:
        """BM25 sparse search."""
        if not self._bm25_index or not self._corpus:
            return []

        tokenized_query = query.lower().split()
        scores = self._bm25_index.get_scores(tokenized_query)

        # Filter by tenant
        scored_docs = [
            (i, score, doc)
            for i, (score, doc) in enumerate(zip(scores, self._corpus))
            if doc.get("metadata", {}).get("tenant_id") == tenant_id
        ]

        # Sort by score descending
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        return [
            SearchResult(
                id=doc.get("id", f"sparse-{i}"),
                content=doc["content"],
                score=float(score),
                source="sparse",
                metadata=doc.get("metadata", {}),
            )
            for i, score, doc in scored_docs[:top_k]
        ]

    def _rrf_fusion(
        self,
        dense: list[SearchResult],
        sparse: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion combining dense + sparse results."""
        scores: dict[str, float] = {}
        content_map: dict[str, SearchResult] = {}

        # Score dense results
        for rank, result in enumerate(dense):
            rrf_score = self.dense_weight * (1.0 / (self.k + rank + 1))
            scores[result.id] = scores.get(result.id, 0) + rrf_score
            content_map[result.id] = result

        # Score sparse results
        for rank, result in enumerate(sparse):
            rrf_score = self.sparse_weight * (1.0 / (self.k + rank + 1))
            scores[result.id] = scores.get(result.id, 0) + rrf_score
            if result.id not in content_map:
                content_map[result.id] = result

        # Sort by fused score
        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

        return [
            SearchResult(
                id=doc_id,
                content=content_map[doc_id].content,
                score=scores[doc_id],
                source="fused",
                metadata=content_map[doc_id].metadata,
            )
            for doc_id in sorted_ids[:top_k]
        ]
