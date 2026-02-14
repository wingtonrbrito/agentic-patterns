"""Demo vertical — Task management models."""
from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    assignee: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    deadline: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = ""


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    assignee: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    deadline: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[TaskStatus] = None
    assignee: Optional[str] = None
    tags: Optional[list[str]] = None
    deadline: Optional[datetime] = None
