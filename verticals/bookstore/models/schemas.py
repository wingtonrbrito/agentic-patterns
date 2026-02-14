"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Genre(str, Enum):
    FICTION = "fiction"
    NON_FICTION = "non_fiction"
    SCIENCE = "science"
    TECHNOLOGY = "technology"
    HISTORY = "history"
    BIOGRAPHY = "biography"
    CHILDREN = "children"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    SELF_HELP = "self_help"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class BookCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    author: str = Field(..., min_length=1, max_length=200)
    isbn: Optional[str] = Field(None, pattern=r"^\d{10,13}$")
    genre: Genre = Genre.FICTION
    price: float = Field(..., gt=0)
    stock_quantity: int = Field(0, ge=0)
    description: Optional[str] = None


class BookUpdate(BaseModel):
    title: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    description: Optional[str] = None


class ReviewCreate(BaseModel):
    book_id: str
    customer_name: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    route: str
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class BookResponse(BaseModel):
    id: str
    title: str
    author: str
    isbn: Optional[str] = None
    genre: str
    price: float
    stock_quantity: int
    description: Optional[str] = None
    avg_rating: Optional[float] = None
    review_count: int = 0
    created_at: Optional[datetime] = None


class ReviewResponse(BaseModel):
    id: str
    book_id: str
    customer_name: str
    rating: int
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class PaginatedResponse(BaseModel):
    data: list
    pagination: dict
