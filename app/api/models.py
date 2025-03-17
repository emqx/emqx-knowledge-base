"""API models for the application."""
from typing import List, Optional

from pydantic import BaseModel


class QuestionRequest(BaseModel):
    """Request model for asking a question."""

    question: str


class SourceReference(BaseModel):
    """Reference to a knowledge source."""

    id: Optional[int] = None
    content_snippet: str


class FileReference(BaseModel):
    """Reference to a file attachment."""

    id: Optional[int] = None
    file_name: str
    file_type: str


class AnswerResponse(BaseModel):
    """Response model for an answer."""

    answer: str
    sources: List[SourceReference] = []
    file_sources: List[FileReference] = []
    confidence: float 