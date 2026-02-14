"""SQLAlchemy models for the bookstore vertical.

Each model inherits from Base and uses TenantMixin for multi-tenant isolation.
The to_dict() method provides a standard serialisation interface used by
repositories and routers.
"""

from sqlalchemy import String, Float, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TenantMixin


class Book(TenantMixin, Base):
    """A book in the catalog."""

    __tablename__ = "books"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    isbn: Mapped[str | None] = mapped_column(String(13), unique=True, nullable=True)
    genre: Mapped[str] = mapped_column(String(50), nullable=False, default="fiction")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviews: Mapped[list["Review"]] = relationship(back_populates="book", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "title": self.title,
            "author": self.author,
            "isbn": self.isbn,
            "genre": self.genre,
            "price": self.price,
            "stock_quantity": self.stock_quantity,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Review(TenantMixin, Base):
    """A customer review of a book."""

    __tablename__ = "reviews"

    book_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("books.id"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    book: Mapped["Book"] = relationship(back_populates="reviews")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "book_id": self.book_id,
            "customer_name": self.customer_name,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Author(TenantMixin, Base):
    """An author with bio and stats."""

    __tablename__ = "authors"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "name": self.name,
            "bio": self.bio,
            "website": self.website,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
