"""Async repository pattern for database access.

Provides a generic base repository with CRUD operations, tenant isolation,
pagination, and FastAPI dependency injection. Verticals subclass this to
add domain-specific queries.

Example: BookstoreRepository extending BaseRepository.
"""

from typing import Any, Generic, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.models.base import Base

# ---------------------------------------------------------------------------
# Type variable for model classes
# ---------------------------------------------------------------------------

ModelT = TypeVar("ModelT", bound=Base)


# ---------------------------------------------------------------------------
# Base repository
# ---------------------------------------------------------------------------

class BaseRepository(Generic[ModelT]):
    """Generic async repository with CRUD + pagination + tenant isolation.

    Subclass and set `model` to your SQLAlchemy model::

        class BookRepository(BaseRepository[Book]):
            model = Book

            async def search_by_title(self, tenant_id: str, query: str):
                stmt = select(self.model).where(
                    self.model.tenant_id == tenant_id,
                    self.model.title.ilike(f"%{query}%"),
                )
                result = await self.session.execute(stmt)
                return [r.to_dict() for r in result.scalars().all()]
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    # -- List with pagination --

    async def list(
        self,
        tenant_id: str,
        page: int = 1,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[dict], int]:
        """List items with pagination and optional filters.

        Returns (items, total_count).
        """
        # Base query with tenant isolation
        stmt = select(self.model).where(self.model.tenant_id == tenant_id)
        count_stmt = select(func.count()).select_from(self.model).where(
            self.model.tenant_id == tenant_id
        )

        # Apply dynamic filters
        if filters:
            for col_name, value in filters.items():
                if hasattr(self.model, col_name) and value is not None:
                    stmt = stmt.where(getattr(self.model, col_name) == value)
                    count_stmt = count_stmt.where(getattr(self.model, col_name) == value)

        # Pagination
        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)

        # Execute
        result = await self.session.execute(stmt)
        items = [row.to_dict() for row in result.scalars().all()]

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        return items, total

    # -- Get by ID --

    async def get(self, item_id: str | UUID, tenant_id: str) -> dict | None:
        """Get a single item by ID with tenant isolation."""
        stmt = select(self.model).where(
            self.model.id == item_id,
            self.model.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return row.to_dict() if row else None

    # -- Create --

    async def create(self, tenant_id: str, data: dict[str, Any]) -> dict:
        """Create a new item."""
        item = self.model(tenant_id=tenant_id, **data)
        self.session.add(item)
        await self.session.flush()
        return item.to_dict()

    # -- Update --

    async def update(
        self, item_id: str | UUID, tenant_id: str, data: dict[str, Any]
    ) -> dict | None:
        """Update an existing item. Returns None if not found."""
        stmt = select(self.model).where(
            self.model.id == item_id,
            self.model.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return None

        for key, value in data.items():
            if hasattr(item, key) and key not in ("id", "tenant_id", "created_at"):
                setattr(item, key, value)

        await self.session.flush()
        return item.to_dict()

    # -- Delete --

    async def delete(self, item_id: str | UUID, tenant_id: str) -> bool:
        """Delete an item. Returns True if deleted, False if not found."""
        stmt = select(self.model).where(
            self.model.id == item_id,
            self.model.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return False

        await self.session.delete(item)
        await self.session.flush()
        return True
