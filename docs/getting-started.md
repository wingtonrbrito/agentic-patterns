# Getting Started with AgentOS

## Prerequisites

| Requirement | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Runtime |
| Docker | 24+ | Container orchestration |
| Docker Compose | v2+ | Service management |
| Git | 2.x | Source control |

Verify your environment:

```bash
python --version   # Python 3.11+
docker --version   # Docker 24+
docker compose version
```

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/agentos.git
cd agentos
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
```

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs the core framework plus development tools (pytest, ruff, mypy).

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# === Required ===
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://agentos:agentos@localhost:5432/agentos
REDIS_URL=redis://localhost:6379/0
CHROMA_URL=http://localhost:8100

# === Optional ===
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
API_HOST=0.0.0.0
API_PORT=8000
RATE_LIMIT_PER_MINUTE=60
```

> **Never commit `.env` to version control.** The `.gitignore` already excludes it.

### Config Validation

AgentOS validates all configuration at startup using Pydantic `BaseSettings`. Missing required values will produce a clear error message telling you exactly which variable is absent.

---

## Running with Docker Compose

The fastest way to get the full stack running:

```bash
docker compose up -d
```

This starts four services:

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI application |
| `postgres` | 5432 | PostgreSQL database |
| `redis` | 6379 | Cache and rate limiting |
| `chroma` | 8100 | Vector database |

Check that everything is healthy:

```bash
docker compose ps
```

All services should show `healthy` status within 30 seconds.

---

## Running Locally (Without Docker)

If you prefer running the API directly (while keeping infrastructure in Docker):

```bash
# Start only infrastructure
docker compose up -d postgres redis chroma

# Run the API locally
uvicorn agentos.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Your First API Call

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "database": "connected",
    "redis": "connected",
    "chroma": "connected"
  }
}
```

### List Registered Verticals

```bash
curl http://localhost:8000/api/v1/verticals
```

Response:

```json
{
  "verticals": [
    {
      "name": "task_management",
      "description": "Task management demo vertical",
      "tools_count": 5,
      "agents_count": 2
    }
  ]
}
```

---

## Running Tests

### Full Test Suite

```bash
pytest
```

### With Coverage

```bash
pytest --cov=agentos --cov-report=term-missing
```

### Specific Vertical Tests

```bash
pytest tests/verticals/task_management/ -v
```

### Linting and Type Checking

```bash
ruff check .
mypy agentos/
```

---

## Project Structure Overview

```
agentos/
├── agentos/
│   ├── main.py              # FastAPI app entrypoint
│   ├── core/                # Shared framework code
│   │   ├── config.py        # Pydantic BaseSettings
│   │   ├── agent_factory.py # create_agent helper
│   │   ├── mcp_factory.py   # create_mcp_server helper
│   │   └── rag/             # Hybrid search engine
│   └── verticals/           # Domain-specific verticals
│       └── task_management/  # Demo vertical
├── tests/
├── docker-compose.yml
├── pyproject.toml
└── docs/
```

---

## Next Steps

- [Creating Verticals](./creating-verticals.md) -- Build your own vertical
- [Pydantic AI Patterns](./pydantic-ai-patterns.md) -- Agent design patterns
- [MCP Guide](./mcp-guide.md) -- Tool server creation
- [RAG Pipeline](./rag-pipeline.md) -- Hybrid search setup
- [Deployment](./deployment.md) -- Production deployment
