# RAG Pipeline -- Hybrid Search Guide

AgentOS includes a hybrid Retrieval-Augmented Generation (RAG) pipeline that combines sparse keyword search, dense vector search, and neural reranking. This guide covers the architecture and usage.

---

## Architecture Overview

```
Query
  |
  |---> BM25 Sparse Search ----------------+
  |                                         |
  |---> Dense Vector Search (embeddings) ---+--> RRF Fusion --> Reranker --> Results
  |                                         |
  +---> (Fallback: keyword match) ----------+
```

The pipeline runs three retrieval strategies in parallel, fuses results using Reciprocal Rank Fusion, then reranks using a neural cross-encoder. A three-tier fallback ensures results even when individual components fail.

---

## HybridSearchEngine

The central class that orchestrates the entire pipeline:

```python
from agentos.core.rag import HybridSearchEngine

engine = HybridSearchEngine(
    collection_name="task_documents",
    chroma_url="http://localhost:8100",
    embedding_model="text-embedding-3-small",
    reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
    bm25_weight=0.3,
    dense_weight=0.7,
    top_k=20,
    rerank_top_k=5,
)
```

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `collection_name` | required | Chroma collection to search |
| `chroma_url` | `http://localhost:8100` | ChromaDB endpoint |
| `embedding_model` | `text-embedding-3-small` | OpenAI embedding model |
| `reranker_model` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model |
| `bm25_weight` | `0.3` | Weight for sparse results in fusion |
| `dense_weight` | `0.7` | Weight for dense results in fusion |
| `top_k` | `20` | Candidates to retrieve before reranking |
| `rerank_top_k` | `5` | Final results after reranking |

---

## Indexing Documents

Before searching, ingest documents into the engine:

```python
await engine.index_documents(
    documents=[
        {
            "id": "doc-1",
            "text": "Task priorities should be reviewed weekly during standups.",
            "metadata": {
                "tenant_id": "acme-corp",
                "source": "team-handbook",
                "section": "processes",
            },
        },
        {
            "id": "doc-2",
            "text": "Critical tasks must be resolved within 24 hours of creation.",
            "metadata": {
                "tenant_id": "acme-corp",
                "source": "sla-policy",
                "section": "response-times",
            },
        },
    ]
)
```

This:
1. Generates embeddings via the configured model.
2. Stores vectors in ChromaDB.
3. Indexes text in the BM25 sparse index.

---

## Searching

### Basic Search

```python
results = await engine.search(
    query="How quickly should critical tasks be resolved?",
    tenant_id="acme-corp",
)
```

### Search with Filters

```python
results = await engine.search(
    query="weekly review process",
    tenant_id="acme-corp",
    filters={"source": "team-handbook"},
    top_k=10,
)
```

### Result Schema

```python
@dataclass
class SearchResult:
    id: str               # Document ID
    text: str             # Document content
    score: float          # Final relevance score (0-1)
    metadata: dict        # Original metadata
    retrieval_method: str  # "hybrid", "dense", "sparse", or "keyword"
```

---

## How It Works

### Stage 1: BM25 Sparse Search

BM25 (Best Matching 25) is a term-frequency-based ranking algorithm. It excels at exact keyword matching:

```python
# Internal -- you don't call this directly
sparse_results = await engine._bm25_search(query, tenant_id, top_k=20)
```

**Strengths:** Exact matches, rare terms, proper nouns.
**Weaknesses:** No semantic understanding, sensitive to vocabulary mismatch.

### Stage 2: Dense Vector Search

Embeds the query using the same model used for indexing, then performs cosine similarity search in ChromaDB:

```python
# Internal
dense_results = await engine._dense_search(query, tenant_id, top_k=20)
```

**Strengths:** Semantic similarity, paraphrases, conceptual matching.
**Weaknesses:** Can miss exact keyword matches, computationally heavier.

### Stage 3: Reciprocal Rank Fusion (RRF)

RRF merges the two ranked lists into a single ranking:

```
RRF_score(doc) = sum( 1 / (k + rank_i(doc)) )  for each retrieval method i
```

Where `k` is a constant (default 60) that controls how much weight is given to top-ranked results.

```python
# Internal
fused = engine._rrf_fuse(sparse_results, dense_results, k=60)
```

RRF is robust -- it does not require score calibration between different retrieval systems. It simply uses rank positions.

### Stage 4: Reranking

The fused candidates are reranked using a neural cross-encoder:

```python
# Internal
reranked = await engine._rerank(query, fused_candidates, top_k=5)
```

AgentOS supports two reranking strategies:

| Reranker | Model | Speed | Quality |
|----------|-------|-------|---------|
| Cross-Encoder | `ms-marco-MiniLM-L-6-v2` | Fast | Good |
| ColBERT | `colbert-ir/colbertv2.0` | Medium | Better |

The cross-encoder processes `(query, document)` pairs and scores their relevance directly. ColBERT uses late interaction for token-level matching.

Configure the reranker:

```python
engine = HybridSearchEngine(
    # ...
    reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",  # default
    # reranker_model="colbert-ir/colbertv2.0",              # alternative
)
```

---

## Three-Tier Fallback

If components fail, the pipeline degrades gracefully:

| Tier | Condition | Behavior |
|------|-----------|----------|
| **Tier 1** | All systems healthy | Full hybrid: BM25 + dense + RRF + reranker |
| **Tier 2** | Reranker unavailable | BM25 + dense + RRF (skip reranking) |
| **Tier 3** | ChromaDB unavailable | BM25 only (sparse search) |
| **Emergency** | BM25 index unavailable | Basic keyword substring matching |

Each fallback is automatic and transparent. The `retrieval_method` field on results tells you which path was used:

```python
for result in results:
    if result.retrieval_method == "keyword":
        logger.warning("Running in degraded mode -- only keyword matching available")
```

---

## Tenant Isolation

All search operations are scoped to a `tenant_id`. This is enforced at every layer:

- **ChromaDB:** Uses metadata filters: `{"tenant_id": tenant_id}`
- **BM25 index:** Maintains per-tenant indices
- **Results:** Double-checked post-retrieval

```python
# Tenant A's documents are NEVER returned for Tenant B queries
results_a = await engine.search("tasks", tenant_id="tenant-a")
results_b = await engine.search("tasks", tenant_id="tenant-b")
# Completely separate result sets
```

---

## Integration with Agents

Agents use the search engine through their deps:

```python
@dataclass
class TaskAgentDeps:
    tenant_id: str
    search_engine: HybridSearchEngine


@agent.tool
async def search_knowledge_base(ctx, query: str) -> list[dict]:
    """Search the knowledge base for relevant documents."""
    deps: TaskAgentDeps = ctx.deps
    results = await deps.search_engine.search(
        query=query,
        tenant_id=deps.tenant_id,
        top_k=5,
    )
    return [
        {"text": r.text, "score": r.score, "source": r.metadata.get("source", "")}
        for r in results
    ]
```

This is how agents populate the `sources` field in `AgentOutput`.

---

## Performance Tuning

| Knob | Effect |
|------|--------|
| Increase `bm25_weight` | Better exact keyword matching |
| Increase `dense_weight` | Better semantic matching |
| Increase `top_k` | More candidates for reranker (slower, more thorough) |
| Decrease `rerank_top_k` | Fewer but higher-quality results |
| Use ColBERT reranker | Better quality, slightly slower |
| Batch indexing | Index documents in batches of 100+ for throughput |

---

## Testing

```python
import pytest
from agentos.core.rag import HybridSearchEngine


@pytest.mark.asyncio
async def test_hybrid_search_returns_results():
    engine = HybridSearchEngine(collection_name="test_docs")
    await engine.index_documents([
        {"id": "1", "text": "Task SLA is 24 hours", "metadata": {"tenant_id": "t1"}},
    ])
    results = await engine.search("SLA", tenant_id="t1")
    assert len(results) > 0
    assert results[0].score > 0.0


@pytest.mark.asyncio
async def test_tenant_isolation():
    engine = HybridSearchEngine(collection_name="test_isolation")
    await engine.index_documents([
        {"id": "1", "text": "Secret doc", "metadata": {"tenant_id": "a"}},
    ])
    results = await engine.search("Secret", tenant_id="b")
    assert len(results) == 0  # tenant b cannot see tenant a's docs
```
