"""Tests for the OpenAI service."""
import os
from unittest.mock import MagicMock

import pytest

from app.models.knowledge import KnowledgeEntry
from app.services.openai_service import OpenAIService


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
class TestOpenAIService:
    """Tests for the OpenAI service."""

    def test_create_embedding(self, monkeypatch):
        """Test creating an embedding."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client.embeddings.create.return_value = mock_response

        # Create the service with the mock client
        service = OpenAIService()
        service.client = mock_client

        # Call the method
        embedding = service.create_embedding("test text")

        # Check the result
        assert embedding == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once()

    def test_generate_response(self, monkeypatch):
        """Test generating a response."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.output_text = "This is a test response."
        mock_client.responses.create.return_value = mock_response

        # Create the service with the mock client
        service = OpenAIService()
        service.client = mock_client

        # Create test data
        entries = [
            KnowledgeEntry(
                channel_id="C123",
                thread_ts="1234.5678",
                user_id="U123",
                content="This is a test entry.",
            )
        ]

        # Call the method
        response = service.generate_response("test question", entries)

        # Check the result
        assert response.question == "test question"
        assert response.answer == "This is a test response."
        assert response.sources == entries
        assert response.confidence == 0.8
        mock_client.responses.create.assert_called_once() 