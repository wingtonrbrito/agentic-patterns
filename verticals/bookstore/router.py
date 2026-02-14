"""Bookstore API router — CRUD + chat endpoint.

Demonstrates the standard AgentOS router pattern:
- Chat endpoint with keyword-based routing to specialist agents
- Full CRUD for books (with search, pagination, filtering)
- Review endpoints
- Tenant isolation via middleware
- Repository injection via FastAPI Depends
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional

from api.middleware import get_current_tenant
from verticals.bookstore.models.schemas import (
    BookCreate,
    BookUpdate,
    ReviewCreate,
    ChatRequest,
    ChatResponse,
)
from verticals.bookstore.repository import (
    BookRepository,
    ReviewRepository,
    get_book_repository,
    get_review_repository,
)

router = APIRouter()


# ============================================================================
# Chat Endpoint
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def bookstore_chat(request: ChatRequest):
    """Route a message to the appropriate bookstore specialist.

    Routing logic:
    - Book search/recommendations → catalog_search
    - Stock/inventory queries → inventory_manager
    - Reviews/ratings → review_analyst
    - Orders/shipping → order_support
    - Default → catalog_search
    """
    msg = request.message.lower()

    if any(w in msg for w in ["search", "find", "recommend", "suggest", "genre", "author"]):
        route = "catalog_search"
    elif any(w in msg for w in ["stock", "inventory", "available", "reorder", "supply"]):
        route = "inventory_manager"
    elif any(w in msg for w in ["review", "rating", "rate", "feedback", "star"]):
        route = "review_analyst"
    elif any(w in msg for w in ["order", "ship", "deliver", "return", "refund", "track"]):
        route = "order_support"
    else:
        route = "catalog_search"

    return ChatResponse(
        response=f"[{route}] Agent would process: {request.message}",
        route=route,
        session_id=request.session_id,
    )


# ============================================================================
# Book Endpoints
# ============================================================================

@router.get("/books")
async def list_books(
    query: Optional[str] = None,
    genre: Optional[str] = None,
    author: Optional[str] = None,
    in_stock: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    repo: BookRepository = Depends(get_book_repository),
):
    """Search and list books with filtering and pagination."""
    tenant_id = get_current_tenant()
    books, total = await repo.search(
        tenant_id=tenant_id,
        query=query,
        genre=genre,
        author=author,
        in_stock=in_stock,
        page=page,
        limit=limit,
    )
    return {
        "data": books,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        },
    }


@router.get("/books/{book_id}")
async def get_book(
    book_id: str,
    repo: BookRepository = Depends(get_book_repository),
    review_repo: ReviewRepository = Depends(get_review_repository),
):
    """Get a single book with its average rating."""
    tenant_id = get_current_tenant()
    book = await repo.get(item_id=book_id, tenant_id=tenant_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    avg_rating = await review_repo.get_avg_rating(tenant_id, book_id)
    book["avg_rating"] = avg_rating
    return book


@router.post("/books", status_code=201)
async def create_book(
    request: BookCreate,
    repo: BookRepository = Depends(get_book_repository),
):
    """Add a new book to the catalog."""
    tenant_id = get_current_tenant()
    book = await repo.create(tenant_id=tenant_id, data=request.model_dump())
    return book


@router.patch("/books/{book_id}")
async def update_book(
    book_id: str,
    request: BookUpdate,
    repo: BookRepository = Depends(get_book_repository),
):
    """Update a book (price, stock, description, etc.)."""
    tenant_id = get_current_tenant()
    updates = request.model_dump(exclude_unset=True)
    book = await repo.update(item_id=book_id, tenant_id=tenant_id, data=updates)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.delete("/books/{book_id}", status_code=204)
async def delete_book(
    book_id: str,
    repo: BookRepository = Depends(get_book_repository),
):
    """Remove a book from the catalog."""
    tenant_id = get_current_tenant()
    deleted = await repo.delete(item_id=book_id, tenant_id=tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Book not found")


# ============================================================================
# Inventory Endpoint
# ============================================================================

@router.get("/inventory/low-stock")
async def get_low_stock(
    threshold: int = Query(5, ge=1),
    repo: BookRepository = Depends(get_book_repository),
):
    """Get books with stock below threshold."""
    tenant_id = get_current_tenant()
    books = await repo.get_low_stock(tenant_id, threshold)
    return {"data": books, "count": len(books), "threshold": threshold}


# ============================================================================
# Review Endpoints
# ============================================================================

@router.get("/books/{book_id}/reviews")
async def get_reviews(
    book_id: str,
    repo: ReviewRepository = Depends(get_review_repository),
):
    """Get all reviews for a book."""
    tenant_id = get_current_tenant()
    reviews = await repo.get_for_book(tenant_id, book_id)
    return {"data": reviews, "count": len(reviews)}


@router.post("/books/{book_id}/reviews", status_code=201)
async def create_review(
    book_id: str,
    request: ReviewCreate,
    repo: ReviewRepository = Depends(get_review_repository),
):
    """Submit a review for a book."""
    tenant_id = get_current_tenant()
    review = await repo.create(
        tenant_id=tenant_id,
        data={"book_id": book_id, **request.model_dump(exclude={"book_id"})},
    )
    return review
