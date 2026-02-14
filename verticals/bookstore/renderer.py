"""Template engine renderer for the bookstore vertical.

Registers a bookstore-specific renderer that converts tool results into
rich markdown. This is the LLM-less response layer — deterministic,
instant, and free.
"""

from typing import Any, Dict

from core.engine.template_engine import (
    fmt_money,
    fmt_int,
    render_generic,
    register_renderer,
)


def render_bookstore(tool_name: str, result: Dict[str, Any], entities: Dict) -> str:
    """Render bookstore tool results into markdown."""
    if "error" in result:
        return f"**Error:** {result['error']}"

    # -- Search results --
    if "books" in result and "result_count" in result:
        books = result["books"]
        lines = [f"## Book Search Results ({result['result_count']} found)\n"]
        if not books:
            lines.append("No books match your search criteria.")
        else:
            lines.append("| Title | Author | Genre | Price | Rating | Stock |")
            lines.append("|-------|--------|-------|-------|--------|-------|")
            for b in books[:10]:
                stock = f"{b['stock']}" if b["stock"] > 0 else "Out of stock"
                lines.append(
                    f"| {b['title'][:35]} | {b['author'][:20]} | {b['genre']} | "
                    f"{fmt_money(b['price'])} | {b['rating']}/5 | {stock} |"
                )
        return "\n".join(lines)

    # -- Recommendations --
    if "recommendations" in result:
        recs = result["recommendations"]
        lines = ["## Recommended Books\n"]
        for r in recs:
            lines.append(
                f"- **{r['title']}** by {r['author']} — {fmt_money(r['price'])} "
                f"({r['reason']})"
            )
        return "\n".join(lines)

    # -- Inventory --
    if "total_units" in result and "out_of_stock" in result:
        lines = ["## Inventory Report\n"]
        lines.append(f"- **Total Titles:** {fmt_int(result['total_titles'])}")
        lines.append(f"- **Total Units:** {fmt_int(result['total_units'])}")
        lines.append(f"- **Inventory Value:** {fmt_money(result['total_inventory_value'])}")

        oos = result["out_of_stock"]
        if oos:
            lines.append(f"\n**Out of Stock ({len(oos)}):**")
            for b in oos:
                lines.append(f"- {b['title']}")

        low = result["low_stock"]
        if low:
            lines.append(f"\n**Low Stock ({len(low)}):**")
            for b in low:
                lines.append(f"- {b['title']} ({b['stock']} remaining)")

        return "\n".join(lines)

    # -- Review summary --
    if "avg_rating" in result and ("total_reviews" in result or "sentiment" in result):
        if "book_id" in result:
            lines = [f"## Reviews — {result.get('title', result['book_id'])}\n"]
            lines.append(f"- **Average Rating:** {result['avg_rating']}/5")
            lines.append(f"- **Total Reviews:** {fmt_int(result.get('total_reviews'))}")
            lines.append(f"- **Sentiment:** {result.get('sentiment', 'N/A')}")
        else:
            lines = ["## Store-Wide Review Summary\n"]
            lines.append(f"- **Books Reviewed:** {fmt_int(result.get('total_books'))}")
            lines.append(f"- **Total Reviews:** {fmt_int(result.get('total_reviews'))}")
            lines.append(f"- **Weighted Avg:** {result.get('weighted_avg_rating')}/5")
            top = result.get("top_rated", {})
            most = result.get("most_reviewed", {})
            if top:
                lines.append(f"- **Top Rated:** {top.get('title')} ({top.get('rating')}/5)")
            if most:
                lines.append(f"- **Most Reviewed:** {most.get('title')} ({fmt_int(most.get('reviews'))} reviews)")
        return "\n".join(lines)

    # -- Store analytics --
    if "genre_breakdown" in result and "stock_health" in result:
        lines = ["## Store Analytics\n"]
        lines.append(f"- **Catalog Size:** {fmt_int(result.get('catalog_size'))}")
        lines.append(f"- **Avg Price:** {fmt_money(result.get('avg_price'))}")
        lines.append(f"- **Avg Rating:** {result.get('avg_rating')}/5")
        lines.append(f"- **Potential Revenue:** {fmt_money(result.get('total_potential_revenue'))}")

        health = result["stock_health"]
        lines.append(f"\n**Stock Health:** {health.get('healthy', 0)} healthy, "
                      f"{health.get('low_stock', 0)} low, {health.get('out_of_stock', 0)} OOS")

        lines.append("\n**By Genre:**")
        for genre, stats in result["genre_breakdown"].items():
            lines.append(f"- **{genre}**: {stats['count']} titles, "
                          f"{stats['total_stock']} units, avg {fmt_money(stats['avg_price'])}")
        return "\n".join(lines)

    return render_generic(tool_name, result)


# Auto-register on import
register_renderer("bookstore", render_bookstore)
