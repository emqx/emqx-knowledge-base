"""Main entry point for the application."""
import logging
import sys
import signal
import uvicorn
import traceback

from app.config import config
from app.utils.logging import configure_logging
from app.api.app import app as api_app
from app.services.database import db_service


def handle_exit(signum, frame):
    """Handle exit signals."""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")
    # Close database connection pool
    db_service.close()
    sys.exit(0)


def main():
    """Start the application."""
    # Configure logging
    configure_logging()
    logger = logging.getLogger(__name__)

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # Validate configuration
    missing_config = config.validate_config()
    if missing_config:
        logger.error(f"Missing required configuration: {', '.join(missing_config)}")
        logger.error("Please set these environment variables in a .env file or in your environment.")
        sys.exit(1)

    logger.info("Starting EMQX Knowledge Base application...")

    try:
        # Start the API server directly in the main thread
        logger.info(f"Starting API server on http://{config.host}:{config.port}")
        uvicorn.run(api_app, host=config.host, port=config.port, log_level=config.log_level.lower())

    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        db_service.close()
    except Exception as e:
        logger.error(f"Error starting the application: {e}")
        logger.error(traceback.format_exc())
        db_service.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
