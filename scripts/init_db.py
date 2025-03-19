#!/usr/bin/env python
"""Script to initialize the database with the pg_vector extension."""

import logging
import os
import sys

import psycopg
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import config
from app.utils.logging import configure_logging

# Configure logging
configure_logging()
logger = logging.getLogger(__name__)


def init_db():
    """Initialize the database with the pg_vector extension."""
    # Load environment variables
    load_dotenv()

    # Check if DATABASE_URL is set
    if not config.database_url:
        logger.error("DATABASE_URL environment variable is not set.")
        sys.exit(1)

    try:
        # Connect to the database
        logger.info(f"Connecting to database: {config.database_url}")
        with psycopg.connect(config.database_url) as conn:
            with conn.cursor() as cur:
                # Create the vector extension
                logger.info("Creating pg_vector extension...")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                # Check if the extension was created successfully
                cur.execute(
                    "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
                )
                result = cur.fetchone()
                if result:
                    logger.info(
                        f"pg_vector extension installed successfully: version {result[1]}"
                    )
                else:
                    logger.error("Failed to install pg_vector extension.")
                    sys.exit(1)

                # Commit the changes
                conn.commit()

        logger.info("Database initialization completed successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_db()
