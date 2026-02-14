"""Bookstore MCP Server — 5 tools.

Demonstrates the MCP server pattern with tools for catalog search,
book recommendations, inventory checks, review summaries, and
store analytics. All tools use deterministic logic — no LLM calls.
"""

from typing import Any

from core.mcp.server_template import create_server

# ---------------------------------------------------------------------------
# In-memory catalog (for demo; production would use repository + DB)
# ---------------------------------------------------------------------------

_CATALOG = {
    "BK-001": {"book_id": "BK-001", "title": "The Pragmatic Programmer", "author": "David Thomas & Andrew Hunt", "genre": "technology", "price": 49.99, "stock": 23, "rating": 4.7, "reviews": 342},
    "BK-002": {"book_id": "BK-002", "title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "genre": "technology", "price": 45.99, "stock": 15, "rating": 4.8, "reviews": 891},
    "BK-003": {"book_id": "BK-003", "title": "Clean Code", "author": "Robert C. Martin", "genre": "technology", "price": 39.99, "stock": 31, "rating": 4.4, "reviews": 1203},
    "BK-004": {"book_id": "BK-004", "title": "Project Hail Mary", "author": "Andy Weir", "genre": "fiction", "price": 16.99, "stock": 42, "rating": 4.9, "reviews": 2156},
    "BK-005": {"book_id": "BK-005", "title": "Atomic Habits", "author": "James Clear", "genre": "self_help", "price": 18.99, "stock": 58, "rating": 4.8, "reviews": 4521},
    "BK-006": {"book_id": "BK-006", "title": "The Midnight Library", "author": "Matt Haig", "genre": "fiction", "price": 14.99, "stock": 3, "rating": 4.3, "reviews": 1876},
    "BK-007": {"book_id": "BK-007", "title": "Sapiens", "author": "Yuval Noah Harari", "genre": "history", "price": 22.99, "stock": 0, "rating": 4.6, "reviews": 3210},
    "BK-008": {"book_id": "BK-008", "title": "Educated", "author": "Tara Westover", "genre": "biography", "price": 16.99, "stock": 19, "rating": 4.7, "reviews": 2890},
}

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

bookstore_server = create_server(
    name="bookstore",
    instructions="Bookstore catalog, inventory, and review tools.",
)


# ---------------------------------------------------------------------------
# Tool 1 — search_catalog
# ---------------------------------------------------------------------------

@bookstore_server.tool()
async def search_catalog(
    query: str | None = None,
    genre: str | None = None,
    max_price: float | None = None,
    in_stock_only: bool = True,
) -> dict[str, Any]:
    """Search the book catalog by keyword, genre, price, and availability."""
    results = list(_CATALOG.values())

    if query:
        q = query.lower()
        results = [b for b in results if q in b["title"].lower() or q in b["author"].lower()]

    if genre:
        results = [b for b in results if b["genre"] == genre]

    if max_price is not None:
        results = [b for b in results if b["price"] <= max_price]

    if in_stock_only:
        results = [b for b in results if b["stock"] > 0]

    return {
        "query": query,
        "filters": {"genre": genre, "max_price": max_price, "in_stock_only": in_stock_only},
        "result_count": len(results),
        "books": results,
    }


# ---------------------------------------------------------------------------
# Tool 2 — get_recommendations
# ---------------------------------------------------------------------------

@bookstore_server.tool()
async def get_recommendations(
    genre: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Get book recommendations based on genre and ratings."""
    books = list(_CATALOG.values())

    if genre:
        books = [b for b in books if b["genre"] == genre]

    # Sort by rating * review_count (popularity-weighted quality)
    books.sort(key=lambda b: b["rating"] * b["reviews"], reverse=True)
    top = books[:limit]

    return {
        "genre_filter": genre,
        "recommendation_count": len(top),
        "recommendations": [
            {
                "book_id": b["book_id"],
                "title": b["title"],
                "author": b["author"],
                "rating": b["rating"],
                "reviews": b["reviews"],
                "price": b["price"],
                "reason": f"Rated {b['rating']}/5 by {b['reviews']:,} readers",
            }
            for b in top
        ],
    }


# ---------------------------------------------------------------------------
# Tool 3 — check_inventory
# ---------------------------------------------------------------------------

@bookstore_server.tool()
async def check_inventory(
    low_stock_threshold: int = 5,
) -> dict[str, Any]:
    """Check inventory levels and identify low-stock or out-of-stock items."""
    out_of_stock = [b for b in _CATALOG.values() if b["stock"] == 0]
    low_stock = [b for b in _CATALOG.values() if 0 < b["stock"] <= low_stock_threshold]
    healthy = [b for b in _CATALOG.values() if b["stock"] > low_stock_threshold]

    total_units = sum(b["stock"] for b in _CATALOG.values())
    total_value = sum(b["stock"] * b["price"] for b in _CATALOG.values())

    return {
        "total_titles": len(_CATALOG),
        "total_units": total_units,
        "total_inventory_value": round(total_value, 2),
        "out_of_stock": [{"book_id": b["book_id"], "title": b["title"]} for b in out_of_stock],
        "low_stock": [
            {"book_id": b["book_id"], "title": b["title"], "stock": b["stock"]}
            for b in low_stock
        ],
        "healthy_count": len(healthy),
        "threshold": low_stock_threshold,
    }


# ---------------------------------------------------------------------------
# Tool 4 — review_summary
# ---------------------------------------------------------------------------

@bookstore_server.tool()
async def review_summary(
    book_id: str | None = None,
) -> dict[str, Any]:
    """Get review summary statistics, optionally for a specific book."""
    if book_id:
        book = _CATALOG.get(book_id)
        if not book:
            return {"error": f"Book '{book_id}' not found"}
        return {
            "book_id": book["book_id"],
            "title": book["title"],
            "avg_rating": book["rating"],
            "total_reviews": book["reviews"],
            "sentiment": "very_positive" if book["rating"] >= 4.5 else "positive" if book["rating"] >= 4.0 else "mixed",
        }

    # Aggregate across all books
    total_reviews = sum(b["reviews"] for b in _CATALOG.values())
    avg_rating = sum(b["rating"] * b["reviews"] for b in _CATALOG.values()) / total_reviews if total_reviews else 0

    top_rated = max(_CATALOG.values(), key=lambda b: b["rating"])
    most_reviewed = max(_CATALOG.values(), key=lambda b: b["reviews"])

    return {
        "total_books": len(_CATALOG),
        "total_reviews": total_reviews,
        "weighted_avg_rating": round(avg_rating, 2),
        "top_rated": {"title": top_rated["title"], "rating": top_rated["rating"]},
        "most_reviewed": {"title": most_reviewed["title"], "reviews": most_reviewed["reviews"]},
    }


# ---------------------------------------------------------------------------
# Tool 5 — store_analytics
# ---------------------------------------------------------------------------

@bookstore_server.tool()
async def store_analytics() -> dict[str, Any]:
    """Get store-wide analytics: revenue potential, genre breakdown, stock health."""
    books = list(_CATALOG.values())

    # Genre breakdown
    genre_stats: dict[str, dict] = {}
    for b in books:
        g = b["genre"]
        if g not in genre_stats:
            genre_stats[g] = {"count": 0, "total_stock": 0, "avg_price": 0, "prices": []}
        genre_stats[g]["count"] += 1
        genre_stats[g]["total_stock"] += b["stock"]
        genre_stats[g]["prices"].append(b["price"])

    for stats in genre_stats.values():
        stats["avg_price"] = round(sum(stats["prices"]) / len(stats["prices"]), 2)
        del stats["prices"]

    total_potential_revenue = sum(b["stock"] * b["price"] for b in books)

    return {
        "catalog_size": len(books),
        "genre_breakdown": genre_stats,
        "total_potential_revenue": round(total_potential_revenue, 2),
        "avg_price": round(sum(b["price"] for b in books) / len(books), 2),
        "avg_rating": round(sum(b["rating"] for b in books) / len(books), 2),
        "stock_health": {
            "out_of_stock": sum(1 for b in books if b["stock"] == 0),
            "low_stock": sum(1 for b in books if 0 < b["stock"] <= 5),
            "healthy": sum(1 for b in books if b["stock"] > 5),
        },
    }
