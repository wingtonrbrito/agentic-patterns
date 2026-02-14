"""Test MCP tool registry and circuit breaker."""
import pytest
import asyncio
from core.mcp.tool_registry import ToolRegistry
from core.mcp.circuit_breaker import CircuitBreaker, CircuitState


def test_tool_registry_register():
    registry = ToolRegistry()
    registry.register(
        name="search",
        description="Search items",
        server_name="demo",
        handler=lambda: {"results": []},
    )
    assert registry.tool_count == 1
    tool = registry.get_tool("search")
    assert tool is not None
    assert tool.name == "search"


def test_tool_registry_deregister():
    registry = ToolRegistry()
    registry.register(name="test", description="Test", server_name="s", handler=lambda: {})
    assert registry.tool_count == 1
    registry.deregister("test")
    assert registry.tool_count == 0


def test_tool_registry_list():
    registry = ToolRegistry()
    registry.register(name="a", description="A", server_name="s", handler=lambda: {})
    registry.register(name="b", description="B", server_name="s", handler=lambda: {})
    tools = registry.list_tools()
    assert len(tools) == 2


@pytest.mark.asyncio
async def test_tool_registry_invoke():
    registry = ToolRegistry()
    registry.register(
        name="echo",
        description="Echo back",
        server_name="demo",
        handler=lambda msg="": {"echo": msg},
    )
    result = await registry.invoke("echo", msg="hello")
    assert result == {"echo": "hello"}


@pytest.mark.asyncio
async def test_tool_registry_invoke_missing():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="Tool not found"):
        await registry.invoke("nonexistent")


def test_circuit_breaker_initial_state():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_success():
    cb = CircuitBreaker()
    result = await cb.call(lambda: "ok")
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_caches():
    call_count = 0

    def counting_fn():
        nonlocal call_count
        call_count += 1
        return f"result-{call_count}"

    cb = CircuitBreaker()
    r1 = await cb.call(counting_fn, cache_key="test")
    assert r1 == "result-1"
    assert cb._cache["test"] == "result-1"


@pytest.mark.asyncio
async def test_circuit_breaker_retries():
    attempt = 0

    def failing_then_ok():
        nonlocal attempt
        attempt += 1
        if attempt < 3:
            raise RuntimeError("fail")
        return "success"

    cb = CircuitBreaker(max_retries=3, backoff_base=0.01)
    result = await cb.call(failing_then_ok)
    assert result == "success"
