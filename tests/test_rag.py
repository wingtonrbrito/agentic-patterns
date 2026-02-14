"""Test RAG pipeline components."""
import pytest
from core.rag.hybrid_search import HybridSearchEngine, SearchResult


def test_rrf_fusion():
    engine = HybridSearchEngine()

    dense = [
        SearchResult(id="1", content="doc one", score=0.9, source="dense"),
        SearchResult(id="2", content="doc two", score=0.8, source="dense"),
    ]
    sparse = [
        SearchResult(id="2", content="doc two", score=5.0, source="sparse"),
        SearchResult(id="3", content="doc three", score=4.0, source="sparse"),
    ]

    fused = engine._rrf_fusion(dense, sparse, top_k=3)
    assert len(fused) == 3
    # Doc 2 should rank highest (appears in both)
    assert fused[0].id == "2"
    assert fused[0].source == "fused"


def test_bm25_indexing():
    engine = HybridSearchEngine()
    docs = [
        {"id": "1", "content": "pricing rate loan amount", "metadata": {"tenant_id": "T1"}},
        {"id": "2", "content": "weather forecast sunny", "metadata": {"tenant_id": "T1"}},
    ]
    engine.index_documents(docs)
    results = engine._sparse_search("loan rate pricing", "T1", top_k=2)
    assert len(results) > 0
    assert results[0].id == "1"


def test_bm25_tenant_filtering():
    engine = HybridSearchEngine()
    docs = [
        {"id": "1", "content": "important document", "metadata": {"tenant_id": "T1"}},
        {"id": "2", "content": "important document", "metadata": {"tenant_id": "T2"}},
    ]
    engine.index_documents(docs)
    results = engine._sparse_search("important document", "T1", top_k=10)
    assert all(r.metadata.get("tenant_id") == "T1" for r in results)


def test_rrf_score_ordering():
    engine = HybridSearchEngine()
    dense = [
        SearchResult(id="a", content="alpha", score=0.9, source="dense"),
        SearchResult(id="b", content="beta", score=0.5, source="dense"),
    ]
    sparse = [
        SearchResult(id="b", content="beta", score=3.0, source="sparse"),
        SearchResult(id="c", content="gamma", score=1.0, source="sparse"),
    ]
    fused = engine._rrf_fusion(dense, sparse, top_k=5)
    # Scores should be descending
    for i in range(len(fused) - 1):
        assert fused[i].score >= fused[i + 1].score


def test_empty_search():
    engine = HybridSearchEngine()
    results = engine._sparse_search("query", "T1", top_k=10)
    assert results == []
