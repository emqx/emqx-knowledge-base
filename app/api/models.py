"""API models for the application."""
from typing import List, Optional

from pydantic import BaseModel


class QuestionRequest(BaseModel):
    """Request model for asking a question."""

    question: str


class LogAnalysisRequest(BaseModel):
    """Request model for analyzing a log."""

    log_text: str


class SourceReference(BaseModel):
    """Reference to a source of information."""

    title: str
    url: Optional[str] = None
    content_snippet: str


class FileReference(BaseModel):
    """Reference to a file attachment."""

    file_name: str
    file_type: str


class AnswerResponse(BaseModel):
    """Response model for an answer."""

    answer: str
    sources: List[SourceReference] = []
    file_sources: List[FileReference] = [] 