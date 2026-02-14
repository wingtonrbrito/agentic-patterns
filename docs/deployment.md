# Deployment Guide

This guide covers deploying AgentOS with Docker Compose, configuring for production, and scaling considerations.

---

## Docker Compose Services

AgentOS runs four services:

```yaml
# docker-compose.yml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      chroma:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: agentos
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-agentos}
      POSTGRES_DB: agentos
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentos"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  chroma:
    image: chromadb/chroma:latest
    ports:
      - "8100:8000"
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      ANONYMIZED_TELEMETRY: "false"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  chroma_data:
```

### Service Overview

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `api` | Custom build | 8000 | FastAPI application server |
| `postgres` | postgres:16-alpine | 5432 | Persistent data storage |
| `redis` | redis:7-alpine | 6379 | Caching, rate limiting, sessions |
| `chroma` | chromadb/chroma | 8100 | Vector database for RAG |

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

# Application code
COPY . .

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "agentos.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

---

## Environment Configuration

### Required Variables

```env
# LLM Provider
OPENAI_API_KEY=sk-...

# Database
DATABASE_URL=postgresql+asyncpg://agentos:${POSTGRES_PASSWORD}@postgres:5432/agentos
POSTGRES_PASSWORD=<strong-random-password>

# Redis
REDIS_URL=redis://redis:6379/0

# ChromaDB
CHROMA_URL=http://chroma:8000
```

### Optional Variables

```env
# Server
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
WORKERS=4

# Security
CORS_ORIGINS=https://your-domain.com
API_KEY_HEADER=X-API-Key
RATE_LIMIT_PER_MINUTE=60

# RAG Configuration
EMBEDDING_MODEL=text-embedding-3-small
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

> **Note:** In Docker Compose, services reference each other by service name (e.g., `postgres`, `redis`, `chroma`) rather than `localhost`.

---

## Production Checklist

### Security

- [ ] **API Keys**: Set a strong `OPENAI_API_KEY`. Rotate regularly.
- [ ] **Database Password**: Use a random 32+ character password for `POSTGRES_PASSWORD`.
- [ ] **CORS Origins**: Restrict `CORS_ORIGINS` to your actual frontend domain(s). Never use `*` in production.
- [ ] **API Authentication**: Enable API key validation via `API_KEY_HEADER`.
- [ ] **HTTPS**: Terminate TLS at your load balancer or reverse proxy (nginx, Caddy, Cloudflare).
- [ ] **Non-root containers**: The Dockerfile runs as `appuser` -- verify this is not overridden.
- [ ] **Secrets management**: Use Docker secrets or a vault (e.g., AWS Secrets Manager) instead of plain `.env` files.

### Rate Limiting

Rate limiting is enforced via Redis using a sliding window algorithm:

```env
RATE_LIMIT_PER_MINUTE=60       # Requests per minute per API key
RATE_LIMIT_BURST=10            # Burst allowance
```

Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

### Database

- [ ] Run migrations before deploying: `alembic upgrade head`
- [ ] Enable connection pooling (default pool size: 20)
- [ ] Set up automated backups (pg_dump or managed service snapshots)
- [ ] Monitor connection count and query latency

### Logging

```env
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json             # json or text
```

Structured JSON logs are recommended for production -- they integrate with log aggregators (Datadog, ELK, CloudWatch).

---

## Health Checks

### API Health Endpoint

```
GET /health
```

Response:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "services": {
    "database": "connected",
    "redis": "connected",
    "chroma": "connected"
  },
  "verticals": {
    "task-management": {
      "status": "healthy",
      "tools_count": 5
    }
  }
}
```

### Docker Health Checks

Each service defines its own health check in `docker-compose.yml`. Docker will:
- Restart unhealthy containers (with `restart: unless-stopped`)
- Delay dependent service startup until dependencies are healthy
- Report health status via `docker compose ps`

### Monitoring

Set up external monitoring to poll `/health` every 30 seconds. Alert if:
- Response time exceeds 5 seconds
- Any service reports non-`healthy` status
- HTTP status code is not 200

---

## Starting and Stopping

### Start All Services

```bash
docker compose up -d
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
```

### Stop All Services

```bash
docker compose down
```

### Stop and Remove Volumes (Full Reset)

```bash
docker compose down -v
```

> **Warning:** This deletes all data (database, cache, vectors). Use only for development.

### Rebuild After Code Changes

```bash
docker compose up -d --build api
```

---

## Scaling Considerations

### Horizontal Scaling (API)

Scale the API service to multiple containers:

```bash
docker compose up -d --scale api=3
```

You will need a load balancer in front (nginx, Traefik, or cloud LB). The API is stateless -- all state lives in Postgres, Redis, and Chroma.

### Database Scaling

| Scale | Approach |
|-------|----------|
| Small (< 10k requests/day) | Single Postgres instance |
| Medium (10k-100k/day) | Read replicas + connection pooling (PgBouncer) |
| Large (100k+/day) | Managed Postgres (RDS, Cloud SQL) with auto-scaling |

### Redis Scaling

Redis handles caching and rate limiting. For most deployments, a single instance with 256MB memory is sufficient. For higher scale:

- Enable Redis persistence (AOF) for durability
- Use Redis Cluster for horizontal scaling
- Consider managed Redis (ElastiCache, Memorystore)

### ChromaDB Scaling

ChromaDB is the vector store for RAG. Scaling options:

| Scale | Approach |
|-------|----------|
| < 1M vectors | Single Chroma instance |
| 1M-10M vectors | Increase memory, use SSD storage |
| > 10M vectors | Consider migrating to Qdrant, Pinecone, or Weaviate |

### Resource Recommendations

| Service | CPU | Memory | Storage |
|---------|-----|--------|---------|
| API (per instance) | 2 cores | 2 GB | -- |
| Postgres | 2 cores | 4 GB | 50 GB SSD |
| Redis | 1 core | 512 MB | 1 GB |
| Chroma | 2 cores | 4 GB | 20 GB SSD |

---

## Reverse Proxy Example (nginx)

```nginx
upstream agentos_api {
    server api:8000;
}

server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /etc/ssl/certs/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/privkey.pem;

    location / {
        proxy_pass http://agentos_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://agentos_api/health;
        access_log off;
    }
}
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| API won't start | Missing env vars | Check `.env` -- startup error names the missing var |
| `database: disconnected` | Postgres not ready | Wait for health check or check `docker compose logs postgres` |
| `chroma: disconnected` | Chroma port conflict | Verify port 8100 is not in use |
| 429 responses | Rate limit hit | Increase `RATE_LIMIT_PER_MINUTE` or distribute load |
| Slow embeddings | Network latency to OpenAI | Consider caching embeddings in Redis |
