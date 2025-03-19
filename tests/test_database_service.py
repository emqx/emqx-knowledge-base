"""Tests for the database service."""

import os
from unittest.mock import MagicMock

import pytest
from psycopg_pool import ConnectionPool

from app.models.knowledge import KnowledgeEntry
from app.services.database import DatabaseService


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
class TestDatabaseService:
    """Tests for the database service."""

    def test_save_knowledge(self, monkeypatch):
        """Test saving a knowledge entry."""
        # Mock the connection pool
        mock_pool = MagicMock(spec=ConnectionPool)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [1]  # Return ID 1
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pool.connection.return_value.__enter__.return_value = mock_conn

        # Create the service with the mock pool
        service = DatabaseService()
        service.pool = mock_pool

        # Create test data
        entry = KnowledgeEntry(
            channel_id="C123",
            thread_ts="1234.5678",
            user_id="U123",
            content="This is a test entry.",
            embedding=[0.1, 0.2, 0.3],
        )

        # Call the method
        entry_id = service.save_knowledge(entry)

        # Check the result
        assert entry_id == 1
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_find_similar_entries(self, monkeypatch):
        """Test finding similar entries."""
        # Mock the connection pool
        mock_pool = MagicMock(spec=ConnectionPool)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "channel_id": "C123",
                "thread_ts": "1234.5678",
                "user_id": "U123",
                "content": "This is a test entry.",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "similarity": 0.9,
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pool.connection.return_value.__enter__.return_value = mock_conn

        # Create the service with the mock pool
        service = DatabaseService()
        service.pool = mock_pool

        # Call the method
        results = service.find_similar_entries([0.1, 0.2, 0.3])

        # Check the result
        assert len(results) == 1
        entry, similarity = results[0]
        assert entry.id == 1
        assert entry.channel_id == "C123"
        assert similarity == 0.9
        mock_cursor.execute.assert_called_once()

    def test_get_entry_by_thread(self, monkeypatch):
        """Test getting an entry by thread."""
        # Mock the connection pool
        mock_pool = MagicMock(spec=ConnectionPool)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "id": 1,
            "channel_id": "C123",
            "thread_ts": "1234.5678",
            "user_id": "U123",
            "content": "This is a test entry.",
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_pool.connection.return_value.__enter__.return_value = mock_conn

        # Create the service with the mock pool
        service = DatabaseService()
        service.pool = mock_pool

        # Call the method
        entry = service.get_entry_by_thread("C123", "1234.5678")

        # Check the result
        assert entry is not None
        assert entry.id == 1
        assert entry.channel_id == "C123"
        assert entry.thread_ts == "1234.5678"
        mock_cursor.execute.assert_called_once()
