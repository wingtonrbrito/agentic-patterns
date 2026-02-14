"""AgentOS API — FastAPI entry point.

Registers middleware, routers, and lifecycle hooks. Each vertical
adds its own router under /api/{vertical}/.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import TenantMiddleware

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
).split(",")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown hooks."""
    # Startup — import renderer to auto-register with template engine
    import verticals.bookstore.renderer  # noqa: F401

    print("AgentOS API started")
    yield
    print("AgentOS API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AgentOS",
    description="Production AI agent framework with Pydantic AI, MCP Protocol, and modular skill architecture",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Multi-tenant middleware
app.add_middleware(TenantMiddleware)

# ---------------------------------------------------------------------------
# Routers — verticals register here
# ---------------------------------------------------------------------------

from verticals.bookstore.router import router as bookstore_router  # noqa: E402

app.include_router(bookstore_router, prefix="/api/bookstore", tags=["Bookstore"])


# ---------------------------------------------------------------------------
# Health & root
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def root():
    return {
        "name": "AgentOS",
        "version": "0.1.0",
        "docs": "/docs",
        "verticals": ["bookstore"],
        "description": "Production AI agent framework",
    }
