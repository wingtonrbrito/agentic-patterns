"""Template Engine — formats tool results into rich markdown responses.

Replaces the need for an LLM to generate natural language from structured data.
Each vertical registers its own renderer functions; the engine dispatches based
on the vertical name. A generic fallback handles any unregistered vertical.

This is useful for:
- Deterministic testing (no LLM variance)
- Cost reduction (skip LLM call for structured data)
- Latency reduction (instant rendering)
- Demos and development (no API keys needed)
"""

from typing import Any, Callable, Dict, Optional


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_money(value: float | int | None, currency: str = "$") -> str:
    """Format a number as currency."""
    if value is None:
        return "N/A"
    return f"{currency}{value:,.2f}"


def fmt_pct(value: float | None) -> str:
    """Format a float as percentage."""
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def fmt_int(value: int | None) -> str:
    """Format an integer with comma separators."""
    if value is None:
        return "N/A"
    return f"{value:,}"


# ---------------------------------------------------------------------------
# Generic fallback renderer
# ---------------------------------------------------------------------------

def render_generic(tool_name: str, result: Dict) -> str:
    """Generic fallback renderer for any tool result.

    Produces a readable markdown summary by iterating over dict keys.
    Lists are summarised, nested dicts show first 4 keys, etc.
    """
    if "error" in result:
        return f"**Error:** {result['error']}"

    lines = [f"## Tool Result: {tool_name}\n"]

    for key, value in result.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            lines.append(f"**{key}:** {len(value)} items")
            for item in value[:5]:
                if isinstance(item, dict):
                    summary = ", ".join(f"{k}={v}" for k, v in list(item.items())[:3])
                    lines.append(f"  - {summary}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(value, dict):
            summary = ", ".join(f"{k}={v}" for k, v in list(value.items())[:4])
            lines.append(f"**{key}:** {summary}")
        elif isinstance(value, float):
            lines.append(f"**{key}:** {value:,.2f}")
        else:
            lines.append(f"**{key}:** {value}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Renderer type and registry
# ---------------------------------------------------------------------------

VerticalRenderer = Callable[[str, Dict, Dict], str]

_VERTICAL_RENDERERS: Dict[str, VerticalRenderer] = {}


def register_renderer(vertical: str, renderer: VerticalRenderer) -> None:
    """Register a vertical-specific renderer.

    Example::

        def render_bookstore(tool_name, result, entities):
            if "books" in result:
                ...
            return render_generic(tool_name, result)

        register_renderer("bookstore", render_bookstore)
    """
    _VERTICAL_RENDERERS[vertical] = renderer


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class TemplateEngine:
    """Formats tool results into rich markdown responses.

    Usage::

        engine = TemplateEngine()
        markdown = engine.render(
            tool_name="search_books",
            tool_result={"books": [...]},
            vertical="bookstore",
        )
    """

    @staticmethod
    def render(
        tool_name: str,
        tool_result: Dict[str, Any],
        vertical: str,
        entities: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Render a tool result into human-readable markdown.

        Args:
            tool_name: Name of the tool that was called.
            tool_result: Dict returned by the tool.
            vertical: The vertical (bookstore, healthcare, etc.).
            entities: Extracted entities from the user message.

        Returns:
            Rich markdown string.
        """
        entities = entities or {}
        renderer = _VERTICAL_RENDERERS.get(vertical)
        if renderer is None:
            return render_generic(tool_name, tool_result)
        return renderer(tool_name, tool_result, entities)

    @staticmethod
    def list_verticals() -> list[str]:
        """Return list of verticals with registered renderers."""
        return list(_VERTICAL_RENDERERS.keys())
