"""Knowledge models for the database."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class FileType(str, Enum):
    """Types of files that can be attached."""

    LOG = "log"
    IMAGE = "image"
    PDF = "pdf"
    OTHER = "other"


class FileAttachment(BaseModel):
    """A file attachment from a Slack thread."""

    id: Optional[int] = None
    channel_id: str
    thread_ts: str
    user_id: str
    file_name: str
    file_type: FileType
    file_url: str
    content_summary: str
    content_text: Optional[str] = None
    embedding: List[float] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)


class KnowledgeEntry(BaseModel):
    """A knowledge entry from a Slack thread."""

    id: Optional[int] = None
    channel_id: str
    thread_ts: str
    user_id: str
    content: str
    embedding: List[float] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)


class KnowledgeQuestion(BaseModel):
    """A question asked by a user."""

    question: str
    embedding: List[float] = Field(default_factory=list)


class KnowledgeResponse(BaseModel):
    """A response to a question."""

    question: str
    answer: str
    sources: List[KnowledgeEntry] = Field(default_factory=list)
    file_sources: List[FileAttachment] = Field(default_factory=list)
    confidence: float = 0.0
