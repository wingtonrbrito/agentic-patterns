"""Bookstore repository — async database access with tenant isolation.

Extends BaseRepository with bookstore-specific queries: search by title/author,
filter by genre, stock level checks, and review aggregation.
"""

from typing import Any

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from patterns.repository import BaseRepository
from verticals.bookstore.models.db_models import Book, Review, Author


# ---------------------------------------------------------------------------
# Book repository
# ---------------------------------------------------------------------------

class BookRepository(BaseRepository[Book]):
    """Repository for book CRUD and search operations."""

    model = Book

    async def search(
        self,
        tenant_id: str,
        query: str | None = None,
        genre: str | None = None,
        author: str | None = None,
        in_stock: bool | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Search books with multiple filters."""
        stmt = select(Book).where(Book.tenant_id == tenant_id)
        count_stmt = select(func.count()).select_from(Book).where(
            Book.tenant_id == tenant_id
        )

        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                (Book.title.ilike(pattern)) | (Book.author.ilike(pattern))
            )
            count_stmt = count_stmt.where(
                (Book.title.ilike(pattern)) | (Book.author.ilike(pattern))
            )

        if genre:
            stmt = stmt.where(Book.genre == genre)
            count_stmt = count_stmt.where(Book.genre == genre)

        if author:
            stmt = stmt.where(Book.author.ilike(f"%{author}%"))
            count_stmt = count_stmt.where(Book.author.ilike(f"%{author}%"))

        if in_stock is True:
            stmt = stmt.where(Book.stock_quantity > 0)
            count_stmt = count_stmt.where(Book.stock_quantity > 0)

        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit).order_by(Book.title)

        result = await self.session.execute(stmt)
        books = [row.to_dict() for row in result.scalars().all()]

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        return books, total

    async def get_low_stock(
        self, tenant_id: str, threshold: int = 5
    ) -> list[dict]:
        """Get books with stock below threshold."""
        stmt = select(Book).where(
            Book.tenant_id == tenant_id,
            Book.stock_quantity <= threshold,
            Book.stock_quantity > 0,
        ).order_by(Book.stock_quantity)

        result = await self.session.execute(stmt)
        return [row.to_dict() for row in result.scalars().all()]


# ---------------------------------------------------------------------------
# Review repository
# ---------------------------------------------------------------------------

class ReviewRepository(BaseRepository[Review]):
    """Repository for book reviews."""

    model = Review

    async def get_for_book(
        self, tenant_id: str, book_id: str
    ) -> list[dict]:
        """Get all reviews for a specific book."""
        stmt = select(Review).where(
            Review.tenant_id == tenant_id,
            Review.book_id == book_id,
        ).order_by(Review.created_at.desc())

        result = await self.session.execute(stmt)
        return [row.to_dict() for row in result.scalars().all()]

    async def get_avg_rating(
        self, tenant_id: str, book_id: str
    ) -> float | None:
        """Get average rating for a book."""
        stmt = select(func.avg(Review.rating)).where(
            Review.tenant_id == tenant_id,
            Review.book_id == book_id,
        )
        result = await self.session.execute(stmt)
        avg = result.scalar()
        return round(float(avg), 2) if avg else None


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------

def get_book_repository(
    session: AsyncSession = Depends(get_session),
) -> BookRepository:
    """FastAPI dependency for BookRepository."""
    return BookRepository(session)


def get_review_repository(
    session: AsyncSession = Depends(get_session),
) -> ReviewRepository:
    """FastAPI dependency for ReviewRepository."""
    return ReviewRepository(session)
