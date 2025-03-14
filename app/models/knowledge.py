"""Knowledge models for the database."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


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

    class Config:
        """Pydantic model configuration."""

        from_attributes = True


class KnowledgeQuestion(BaseModel):
    """A question asked by a user."""

    question: str
    embedding: List[float] = Field(default_factory=list)


class KnowledgeResponse(BaseModel):
    """A response to a question."""

    question: str
    answer: str
    sources: List[KnowledgeEntry] = Field(default_factory=list)
    confidence: float = 0.0 