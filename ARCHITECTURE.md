# AgentOS — Architecture

This document describes the internal architecture of AgentOS, covering design principles, the agent lifecycle, data pipelines, and extension points.

---

## Table of Contents

- [Design Principles](#design-principles)
- [Agent Lifecycle](#agent-lifecycle)
- [RAG Pipeline](#rag-pipeline)
- [Memory System](#memory-system)
- [Skill System](#skill-system)
- [Guardrail Pipeline](#guardrail-pipeline)
- [Adding a New Vertical](#adding-a-new-vertical)

---

## Design Principles

### 1. Tenant Isolation

Every vertical operates in a fully isolated namespace. Data, configuration, prompts, skills, and guardrails are scoped to the tenant. There is no cross-contamination between verticals — a fintech agent never sees healthcare data, and vice versa.

**Implementation:**
- Each vertical has its own database schema (or namespace prefix).
- Vector collections are namespaced per tenant.
- Redis cache keys are prefixed with the tenant identifier.
- Environment variables and secrets are scoped per deployment.

### 2. Progressive Disclosure

Agents should not be burdened with capabilities they do not need for a given task. Skills, tools, and context are loaded incrementally based on the complexity of the current interaction.

**Implementation:**
- Skills are organized into three levels (L0, L1, L2) and loaded on demand.
- System prompts are composed dynamically based on active skills.
- RAG context is injected only when retrieval is triggered by the intent classifier.

### 3. Grounded Responses

Every agent response must be traceable to a source. The system prioritizes verifiable, cited answers over creative generation. When the agent cannot ground its response, it must explicitly state uncertainty rather than hallucinate.

**Implementation:**
- The guardrail pipeline checks every response against retrieved source documents.
- Confidence scores are computed and must exceed a configurable threshold.
- A separate LLM-as-Judge performs final verification before delivery.
- Responses include source citations when RAG documents are used.

---

## Agent Lifecycle

Every user interaction follows a five-stage lifecycle:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  CREATE   │───▶│  ROUTE   │───▶│ EXECUTE  │───▶│  VERIFY  │───▶│ RESPOND  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### Stage 1: Create

The FastAPI gateway receives the user message and creates an execution context. This context includes tenant ID, session ID, user metadata, and conversation history. A unique trace ID is generated for OpenTelemetry instrumentation.

### Stage 2: Route

The **Intent Router** classifies the user message and determines which specialist agent should handle it. The router uses a lightweight LLM call with a constrained output schema (Pydantic model) to produce:

- `intent` — The classified user intent (e.g., `trade_execution`, `portfolio_query`).
- `confidence` — A float between 0 and 1.
- `specialist` — The target specialist agent identifier.
- `requires_rag` — Whether retrieval is needed.
- `skill_level` — The minimum skill level required (L0, L1, or L2).

If confidence is below the routing threshold, the supervisor handles the request directly with a clarification prompt.

### Stage 3: Execute

The selected specialist agent is instantiated with:

1. **System prompt** — Composed from base prompt + active skill instructions.
2. **Tools** — MCP tools registered for this specialist.
3. **Context** — RAG results (if `requires_rag` is true), memory (episodic + semantic), and conversation history.

The specialist executes using Pydantic AI’s agent runner, which handles tool calling loops, structured output parsing, and retry logic.

### Stage 4: Verify

The specialist’s response passes through the four-layer guardrail pipeline (see [Guardrail Pipeline](#guardrail-pipeline)). If any layer rejects the response:

- The rejection reason is logged.
- The specialist is re-invoked with the rejection feedback appended to its context.
- A maximum of 2 retry attempts are allowed before falling back to a safe “I don’t know” response.

### Stage 5: Respond

The verified response is returned to the user through the FastAPI gateway. The following metadata is attached:

- Source citations (if RAG was used).
- Confidence score.
- Trace ID (for debugging and observability).
- Memory updates are flushed asynchronously (episodic turn, semantic extractions).

---

## RAG Pipeline

The Retrieval-Augmented Generation pipeline transforms raw documents into grounded context for agent responses.

### Ingestion Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  INGEST  │───▶│  CHUNK   │───▶│  EMBED   │───▶│  SEARCH  │───▶│ RERANK   │───▶│   FUSE   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### Stage 1: Ingest

Documents are loaded from configured sources (files, URLs, databases, APIs). Each document is tagged with metadata: source, tenant, document type, timestamp, and version.

Supported formats: PDF, Markdown, HTML, plain text, DOCX, CSV.

### Stage 2: Chunk

Documents are split into chunks using a configurable strategy:

| Strategy         | Use Case                     | Default Size |
|------------------|------------------------------|--------------|
| Recursive        | General-purpose text         | 512 tokens   |
| Semantic         | Long-form documents          | Variable     |
| Sentence-window  | FAQ / Q&A style content      | 3 sentences  |
| Markdown-header  | Structured documentation     | Per section  |

Each chunk retains a reference to its parent document and positional metadata for context windowing.

### Stage 3: Embed

Chunks are embedded using a configurable embedding model. The default is `text-embedding-3-small` (OpenAI) with 1536 dimensions. Embeddings are stored in pgvector or ChromaDB, indexed for approximate nearest neighbor search (HNSW).

A parallel BM25 index is built over the raw chunk text for sparse retrieval.

### Stage 4: Search

At query time, two parallel searches execute:

- **Dense search** — Cosine similarity over the vector index. Returns top-k candidates.
- **Sparse search** — BM25 scoring over the text index. Returns top-k candidates.

Both searches are scoped to the tenant namespace and filtered by any metadata constraints (e.g., document type, recency).

### Stage 5: Rerank

Candidates from both searches are passed through a cross-encoder reranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) that scores each query-document pair. This produces a more accurate relevance ranking than either retrieval method alone.

### Stage 6: Fuse

The final context is assembled using **Reciprocal Rank Fusion (RRF)**:

```
RRF_score(d) = Σ  1 / (k + rank_i(d))
```

Where `k` is a constant (default: 60) and `rank_i(d)` is the rank of document `d` in retrieval method `i`. The top-N fused results are injected into the agent’s context window with source citations.

---

## Memory System

AgentOS implements a three-layer memory architecture that gives agents persistent, contextual recall across interactions.

### Layer 1: Episodic Memory

**Purpose:** Short-term recall of recent interactions.

- Stores raw conversation turns (user messages + agent responses).
- Windowed to the last N turns (configurable, default: 20).
- Used for in-context conversation continuity.
- Storage: Redis (fast access, TTL-based expiry).

### Layer 2: Semantic Memory

**Purpose:** Long-term factual knowledge extracted from interactions.

- After each interaction, key facts, entities, and relationships are extracted using an LLM.
- Extracted facts are embedded and stored in the vector database.
- Retrieved via semantic similarity when relevant to a new query.
- Storage: pgvector / ChromaDB (persistent, searchable).

**Extraction schema:**

```
- subject: str        # The entity or concept
- predicate: str      # The relationship or attribute
- object: str         # The value or related entity
- confidence: float   # Extraction confidence (0-1)
- source_turn: int    # The conversation turn it was extracted from
- timestamp: datetime # When it was extracted
```

### Layer 3: Procedural Memory

**Purpose:** Learned workflows and decision patterns.

- Captures successful multi-step interactions as reusable “procedures.”
- When a similar task is detected, the procedure is loaded as a guide for the agent.
- Procedures are stored as structured YAML with step sequences and decision points.
- Storage: PostgreSQL (structured, versioned).

**Example procedure:**

```yaml
procedure: execute_market_order
trigger: "user wants to buy/sell a stock at market price"
steps:
  - validate_ticker_symbol
  - check_market_hours
  - verify_account_balance
  - confirm_order_with_user
  - execute_via_broker_api
  - confirm_execution
guards:
  - max_order_value: 100000
  - require_explicit_confirmation: true
```

### Memory Relevance Decay

All memory layers implement time-based relevance decay. Older memories receive lower retrieval scores, ensuring recent context is prioritized. The decay function is configurable per vertical:

```
relevance(t) = base_score * e^(-λ * age_hours)
```

Where `λ` is the decay rate (default: 0.01 for semantic, 0.1 for episodic).

---

## Skill System

Skills define what an agent can do. They are organized into three progressive levels.

### Level 0: Core Skills (Always Loaded)

Core skills are loaded for every interaction regardless of intent. They define the agent’s identity, safety boundaries, and basic routing behavior.

**Examples:**
- Identity and persona instructions.
- Safety and refusal guidelines.
- Output formatting rules.
- Conversation management (greetings, clarifications, handoffs).

### Level 1: Domain Skills (Loaded Per Vertical)

Domain skills are loaded when a vertical is activated. They provide the foundational domain knowledge and capabilities.

**Examples (fintech vertical):**
- Market terminology and concepts.
- Regulatory compliance rules (e.g., KYC, AML).
- Standard financial calculations.
- Ticker symbol resolution.

### Level 2: Specialist Skills (Loaded On-Demand)

Specialist skills are loaded only when a specific task type is detected by the intent router. They provide deep, narrow expertise.

**Examples (fintech vertical):**
- Options pricing models (loaded for options queries).
- Technical analysis patterns (loaded for chart analysis).
- Tax-loss harvesting strategies (loaded for tax optimization).
- Portfolio rebalancing algorithms (loaded for allocation requests).

### Skill Manifest Format

Each skill is defined in a YAML manifest:

```yaml
skill:
  id: "fintech.options_pricing"
  name: "Options Pricing Specialist"
  level: L2
  trigger_intents:
    - options_query
    - options_pricing
    - greeks_calculation
  prompt_file: "skills/l2/options_pricing.md"
  tools:
    - calculate_black_scholes
    - compute_greeks
    - options_chain_lookup
  rag_collections:
    - options_knowledge_base
  guardrails:
    - no_investment_advice_disclaimer
```

---

## Guardrail Pipeline

Every agent response passes through a four-layer guardrail pipeline before reaching the user. Each layer can **pass**, **flag** (pass with warning), or **reject** the response.

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  CONFIDENCE  │──▶│  GROUNDING   │──▶│   DOMAIN     │──▶│ LLM-AS-JUDGE │
│    GATE      │   │    CHECK     │   │  VALIDATOR   │   │  VERIFIER    │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### Layer 1: Confidence Gate

Checks the model’s self-reported confidence and token-level log probabilities. If the average confidence falls below the threshold (configurable per vertical, default: 0.7), the response is rejected.

**Configuration:**
```yaml
confidence_gate:
  threshold: 0.7
  metric: "mean_logprob"
  action_on_fail: "reject"
```

### Layer 2: Grounding Check

Verifies that factual claims in the response are supported by retrieved source documents. Uses semantic similarity between response sentences and RAG context chunks. Claims with no supporting evidence above the similarity threshold are flagged.

**Configuration:**
```yaml
grounding_check:
  similarity_threshold: 0.75
  min_grounded_ratio: 0.8
  action_on_fail: "flag"
```

### Layer 3: Domain Validator

Applies vertical-specific business rules. These are deterministic checks that enforce regulatory, safety, or business constraints.

**Examples:**
- **Healthcare:** No dosage recommendations without citing a clinical source.
- **Fintech:** All trade confirmations must include a risk disclaimer.
- **Education:** Grade calculations must show step-by-step workings.

**Configuration:**
```yaml
domain_rules:
  - rule: "response must not contain specific investment advice"
    pattern: "(you should buy|I recommend purchasing|guaranteed returns)"
    action: "reject"
  - rule: "trade responses must include disclaimer"
    check: "contains_disclaimer"
    action: "flag"
```

### Layer 4: LLM-as-Judge Verifier

A separate LLM instance evaluates the response for:

- **Accuracy** — Are the facts correct based on the provided context?
- **Completeness** — Does the response address the user’s question fully?
- **Safety** — Does the response comply with safety guidelines?
- **Consistency** — Is the response consistent with previous turns?

The judge returns a structured verdict:

```json
{
  "verdict": "pass",
  "accuracy_score": 0.92,
  "completeness_score": 0.88,
  "safety_score": 1.0,
  "consistency_score": 0.95,
  "issues": [],
  "reasoning": "Response accurately reflects retrieved documents..."
}
```

If the overall verdict is “fail,” the response is rejected and the specialist is retried with the judge’s feedback.

---

## Adding a New Vertical

Follow these steps to create a production-ready vertical for a new domain.

### Step 1: Scaffold the Directory

```
verticals/
└── my-vertical/
    ├── config.yaml
    ├── prompts/
    │   ├── system.md
    │   └── specialists/
    │       ├── analyst.md
    │       └── advisor.md
    ├── skills/
    │   ├── l0_core.yaml
    │   ├── l1_domain.yaml
    │   └── l2_specialist/
    │       ├── analysis.yaml
    │       └── advisory.yaml
    ├── mcp_servers/
    │   └── tools.py
    ├── rag/
    │   ├── sources.yaml
    │   └── chunking.yaml
    ├── guardrails/
    │   └── rules.yaml
    └── tests/
        ├── test_routing.py
        ├── test_guardrails.py
        └── test_e2e.py
```

### Step 2: Define Configuration

Create `config.yaml` with your vertical’s settings:

```yaml
vertical:
  id: "my-vertical"
  name: "My Vertical"
  version: "1.0.0"

llm:
  primary: "claude-sonnet-4-20250514"
  judge: "claude-sonnet-4-20250514"
  embedding: "text-embedding-3-small"

agents:
  supervisor:
    prompt: "prompts/system.md"
    max_retries: 2
  specialists:
    - id: "analyst"
      prompt: "prompts/specialists/analyst.md"
      intents: ["analysis_request", "data_query"]
    - id: "advisor"
      prompt: "prompts/specialists/advisor.md"
      intents: ["advice_request", "recommendation"]

guardrails:
  confidence_threshold: 0.75
  grounding_threshold: 0.8
  max_judge_retries: 1

memory:
  episodic_window: 20
  semantic_decay_rate: 0.01
  procedural_enabled: true
```

### Step 3: Write Prompts

Create detailed system prompts for the supervisor and each specialist. Include:

- Role definition and persona.
- Domain-specific terminology and constraints.
- Output format expectations.
- Safety boundaries.

### Step 4: Register Skills

Define skill manifests at each level. Start with L0 (core behaviors), then L1 (domain knowledge), then L2 (specialist capabilities). Each skill manifest references a prompt file and a set of tools.

### Step 5: Implement MCP Tools

Create FastMCP tool functions in `mcp_servers/tools.py`:

```python
from fastmcp import FastMCP

mcp = FastMCP("my-vertical")

@mcp.tool()
async def lookup_data(query: str, filters: dict | None = None) -> dict:
    """Look up domain-specific data based on a query."""
    # Implementation here
    ...

@mcp.tool()
async def execute_action(action_type: str, params: dict) -> dict:
    """Execute a domain-specific action."""
    # Implementation here
    ...
```

### Step 6: Configure RAG Sources

Define your knowledge base sources and chunking strategy in `rag/sources.yaml`:

```yaml
sources:
  - name: "domain_knowledge_base"
    type: "directory"
    path: "data/knowledge/"
    formats: ["md", "pdf", "txt"]
    chunking:
      strategy: "recursive"
      chunk_size: 512
      chunk_overlap: 50

  - name: "faq_database"
    type: "csv"
    path: "data/faq.csv"
    chunking:
      strategy: "sentence_window"
      window_size: 3
```

### Step 7: Set Guardrail Rules

Define domain-specific validation rules in `guardrails/rules.yaml`. Include both pattern-based rules and semantic checks.

### Step 8: Write Tests

Create tests that validate:

- Intent routing accuracy.
- Guardrail enforcement.
- End-to-end conversation flows.
- Tool invocation correctness.
- RAG retrieval relevance.

### Step 9: Deploy

```bash
# Set environment variables
export VERTICAL=my-vertical

# Launch
docker-compose up
```

The vertical will be registered automatically on startup and accessible through the API gateway at `/v1/my-vertical/chat`.

---

*This document is maintained alongside the codebase. For questions or contributions, open an issue or pull request.*