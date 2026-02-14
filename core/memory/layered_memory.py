"""
AgentOS Layered Memory — Episodic + Semantic + Procedural

Three memory layers:
1. Episodic: Short-term interaction context (current session)
2. Semantic: Long-term knowledge facts (vector-backed)
3. Procedural: Reusable skills and code patterns (SKILL.md files)

Tenant-scoped: all memory operations isolated by tenant.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
import uuid


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    content: str
    memory_type: str  # episodic | semantic | procedural
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    access_count: int = 0


class LayeredMemory:
    """Three-layer memory system."""

    def __init__(self, vector_store=None, redis_client=None):
        self.vector_store = vector_store
        self.redis = redis_client
        self._episodic: dict[str, list[MemoryEntry]] = {}  # tenant -> entries

    # --- Episodic (short-term, session-scoped) ---

    def add_episodic(self, tenant_id: str, content: str, metadata: dict = None) -> MemoryEntry:
        """Add to short-term session memory."""
        entry = MemoryEntry(
            tenant_id=tenant_id,
            content=content,
            memory_type="episodic",
            metadata=metadata or {},
        )
        if tenant_id not in self._episodic:
            self._episodic[tenant_id] = []
        self._episodic[tenant_id].append(entry)

        # Keep only last 50 entries per session
        if len(self._episodic[tenant_id]) > 50:
            self._episodic[tenant_id] = self._episodic[tenant_id][-50:]

        return entry

    def get_episodic(self, tenant_id: str, limit: int = 10) -> list[MemoryEntry]:
        """Get recent session memory."""
        entries = self._episodic.get(tenant_id, [])
        return entries[-limit:]

    def clear_episodic(self, tenant_id: str):
        """Clear session memory (end of conversation)."""
        self._episodic.pop(tenant_id, None)

    # --- Semantic (long-term, vector-backed) ---

    async def add_semantic(self, tenant_id: str, content: str, metadata: dict = None) -> MemoryEntry:
        """Store in long-term semantic memory (vector DB)."""
        entry = MemoryEntry(
            tenant_id=tenant_id,
            content=content,
            memory_type="semantic",
            metadata=metadata or {},
        )
        if self.vector_store:
            self.vector_store.add(
                documents=[content],
                ids=[entry.id],
                metadatas=[{"tenant_id": tenant_id, "type": "semantic", **(metadata or {})}],
            )
        return entry

    async def search_semantic(self, tenant_id: str, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Search long-term memory by semantic similarity."""
        if not self.vector_store:
            return []

        results = self.vector_store.query(
            query_texts=[query],
            n_results=top_k,
            where={"tenant_id": tenant_id, "type": "semantic"},
        )

        entries = []
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"][0]):
                entries.append(MemoryEntry(
                    id=results["ids"][0][i],
                    tenant_id=tenant_id,
                    content=doc,
                    memory_type="semantic",
                    metadata=results["metadatas"][0][i] if results.get("metadatas") else {},
                ))
        return entries

    # --- Procedural (skills-backed) ---

    def get_procedural(self, skill_name: str) -> Optional[str]:
        """Retrieve procedural memory (skill instructions)."""
        # Delegates to SkillLoader — procedural memory IS the skill system
        return None  # Connected via SkillLoader in production
