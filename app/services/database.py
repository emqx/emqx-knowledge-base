"""Database service for PostgreSQL with pg_vector."""
import logging
from typing import List, Optional, Tuple

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import config
from app.models.knowledge import FileAttachment, KnowledgeEntry

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for interacting with the PostgreSQL database."""

    def __init__(self):
        """Initialize the database service."""
        self.pool = ConnectionPool(config.database_url, min_size=1, max_size=10, open=True)
        self._initialize_database()

    def _initialize_database(self):
        """Initialize the database schema if it doesn't exist."""
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                # Check if vector extension is installed
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                if not cur.fetchone():
                    logger.error("pg_vector extension is not installed in the database")
                    raise RuntimeError(
                        "pg_vector extension is not installed. Please run: CREATE EXTENSION vector;"
                    )

                # Create knowledge table if it doesn't exist
                dimension = config.embedding_dimension
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS knowledge_entries (
                        id SERIAL PRIMARY KEY,
                        channel_id TEXT NOT NULL,
                        thread_ts TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector({dimension}) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        UNIQUE(channel_id, thread_ts)
                    )
                    """
                )

                # Create index for vector similarity search
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS knowledge_entries_embedding_idx
                    ON knowledge_entries
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )

                # Create file attachments table
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS file_attachments (
                        id SERIAL PRIMARY KEY,
                        channel_id TEXT NOT NULL,
                        thread_ts TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        file_url TEXT NOT NULL,
                        content_summary TEXT NOT NULL,
                        content_text TEXT,
                        embedding vector({dimension}),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                    """
                )

                # Create index for file attachments vector similarity search
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS file_attachments_embedding_idx
                    ON file_attachments
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )

                conn.commit()

    def save_knowledge(self, entry: KnowledgeEntry) -> int:
        """Save a knowledge entry to the database.

        Args:
            entry: The knowledge entry to save.

        Returns:
            The ID of the saved entry.
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_entries
                    (channel_id, thread_ts, user_id, content, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    ON CONFLICT (channel_id, thread_ts)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        entry.channel_id,
                        entry.thread_ts,
                        entry.user_id,
                        entry.content,
                        entry.embedding,
                    ),
                )
                entry_id = cur.fetchone()[0]
                conn.commit()
                return entry_id

    def find_similar_entries(
        self, embedding: List[float], limit: int = 5, threshold: float = 0.7
    ) -> List[Tuple[KnowledgeEntry, float]]:
        """Find similar knowledge entries based on embedding similarity.

        Args:
            embedding: The embedding vector to compare against.
            limit: Maximum number of results to return.
            threshold: Minimum similarity threshold (0-1).

        Returns:
            A list of tuples containing the knowledge entry and its similarity score.
        """
        with self.pool.connection() as conn:
            # logger.info(f"Finding similar entries with threshold {threshold} for embedding: {embedding}")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id, channel_id, thread_ts, user_id, content, 
                        created_at, updated_at,
                        1 - (embedding <=> %s::vector) AS similarity
                    FROM knowledge_entries
                    WHERE 1 - (embedding <=> %s::vector) > %s
                    ORDER BY similarity DESC
                    LIMIT %s
                    """,
                    (embedding, embedding, threshold, limit),
                )
                results = []
                for row in cur.fetchall():
                    similarity = row.pop("similarity")
                    entry = KnowledgeEntry.model_validate(row)
                    results.append((entry, similarity))
                return results

    def get_entry_by_thread(self, channel_id: str, thread_ts: str) -> Optional[KnowledgeEntry]:
        """Get a knowledge entry by channel ID and thread timestamp.

        Args:
            channel_id: The Slack channel ID.
            thread_ts: The Slack thread timestamp.

        Returns:
            The knowledge entry if found, None otherwise.
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, channel_id, thread_ts, user_id, content, created_at, updated_at
                    FROM knowledge_entries
                    WHERE channel_id = %s AND thread_ts = %s
                    """,
                    (channel_id, thread_ts),
                )
                row = cur.fetchone()
                if row:
                    return KnowledgeEntry.model_validate(row)
                return None

    def save_file_attachment(self, attachment: FileAttachment) -> int:
        """Save a file attachment to the database.
        
        Args:
            attachment: The file attachment to save.
            
        Returns:
            The ID of the saved attachment.
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO file_attachments
                    (channel_id, thread_ts, user_id, file_name, file_type, file_url, 
                     content_summary, content_text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    RETURNING id
                    """,
                    (
                        attachment.channel_id,
                        attachment.thread_ts,
                        attachment.user_id,
                        attachment.file_name,
                        attachment.file_type,
                        attachment.file_url,
                        attachment.content_summary,
                        attachment.content_text,
                        attachment.embedding,
                    ),
                )
                attachment_id = cur.fetchone()[0]
                conn.commit()
                return attachment_id
    
    def find_similar_file_attachments(
        self, embedding: List[float], limit: int = 3, threshold: float = 0.6
    ) -> List[Tuple[FileAttachment, float]]:
        """Find similar file attachments based on embedding similarity.
        
        Args:
            embedding: The embedding vector to compare against.
            limit: Maximum number of results to return.
            threshold: Minimum similarity threshold (0-1).
            
        Returns:
            A list of tuples containing the file attachment and its similarity score.
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        id, channel_id, thread_ts, user_id, file_name, file_type,
                        file_url, content_summary, content_text, created_at,
                        1 - (embedding <=> %s::vector) AS similarity
                    FROM file_attachments
                    WHERE embedding IS NOT NULL AND 1 - (embedding <=> %s::vector) > %s
                    ORDER BY similarity DESC
                    LIMIT %s
                    """,
                    (embedding, embedding, threshold, limit),
                )
                results = []
                for row in cur.fetchall():
                    similarity = row.pop("similarity")
                    attachment = FileAttachment.model_validate(row)
                    results.append((attachment, similarity))
                return results
    
    def get_file_attachments_by_thread(self, channel_id: str, thread_ts: str) -> List[FileAttachment]:
        """Get all file attachments for a specific thread.
        
        Args:
            channel_id: The Slack channel ID.
            thread_ts: The Slack thread timestamp.
            
        Returns:
            A list of file attachments for the thread.
        """
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, channel_id, thread_ts, user_id, file_name, file_type,
                           file_url, content_summary, content_text, created_at
                    FROM file_attachments
                    WHERE channel_id = %s AND thread_ts = %s
                    """,
                    (channel_id, thread_ts),
                )
                return [FileAttachment.model_validate(row) for row in cur.fetchall()]


# Create a global database service instance
db_service = DatabaseService() 
