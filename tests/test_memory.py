"""Test layered memory system."""
import pytest
from core.memory.layered_memory import LayeredMemory, MemoryEntry


def test_episodic_add():
    mem = LayeredMemory()
    entry = mem.add_episodic("T1", "User asked about tasks")
    assert entry.tenant_id == "T1"
    assert entry.memory_type == "episodic"
    assert entry.content == "User asked about tasks"


def test_episodic_get():
    mem = LayeredMemory()
    mem.add_episodic("T1", "msg1")
    mem.add_episodic("T1", "msg2")
    mem.add_episodic("T1", "msg3")
    entries = mem.get_episodic("T1", limit=2)
    assert len(entries) == 2
    assert entries[-1].content == "msg3"


def test_episodic_tenant_isolation():
    mem = LayeredMemory()
    mem.add_episodic("T1", "tenant 1 msg")
    mem.add_episodic("T2", "tenant 2 msg")
    t1_entries = mem.get_episodic("T1")
    t2_entries = mem.get_episodic("T2")
    assert len(t1_entries) == 1
    assert len(t2_entries) == 1
    assert t1_entries[0].content == "tenant 1 msg"


def test_episodic_clear():
    mem = LayeredMemory()
    mem.add_episodic("T1", "msg")
    mem.clear_episodic("T1")
    assert mem.get_episodic("T1") == []


def test_episodic_max_entries():
    mem = LayeredMemory()
    for i in range(60):
        mem.add_episodic("T1", f"msg-{i}")
    entries = mem.get_episodic("T1", limit=100)
    assert len(entries) == 50  # capped at 50


def test_procedural_returns_none():
    mem = LayeredMemory()
    assert mem.get_procedural("nonexistent") is None
