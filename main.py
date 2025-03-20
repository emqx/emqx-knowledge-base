"""Main entry point for the application."""

import logging
import sys
import signal
import uvicorn
import traceback
import threading
import asyncio

from app.config import config
from app.utils.logging import configure_logging
from app.api.app import app as api_app
from app.services.database import db_service

# Global variable to store the Slack thread
slack_thread = None


def handle_exit(signum, frame):
    """Handle exit signals."""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")
    # Close database connection pool
    db_service.close()
    sys.exit(0)


def start_slack_service():
    """Start the Slack service in a separate thread with its own event loop."""
    if not config.enable_slack:
        return

    logger = logging.getLogger(__name__)

    try:
        from app.services.slack_service import slack_service

        # Create a function that sets up an event loop for the thread
        def start_slack_with_loop():
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Start the slack service
            try:
                logger.info("Starting Slack service...")
                slack_service.start()
            except Exception as e:
                logger.error(f"Error in Slack service: {e}")
                logger.error(traceback.format_exc())

        # Start in a daemon thread so it gets killed when the main thread exits
        global slack_thread
        slack_thread = threading.Thread(target=start_slack_with_loop, daemon=True)
        slack_thread.start()
        logger.info("Slack service started in background thread with event loop")

    except Exception as e:
        logger.error(f"Failed to start Slack service: {e}")
        logger.error(traceback.format_exc())


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
        logger.error(
            "Please set these environment variables in a .env file or in your environment."
        )
        sys.exit(1)

    logger.info("Starting EMQX Knowledge Base application...")

    # Log configuration details
    logger.info(f"Environment: {config.environment}")
    logger.info(
        f"Slack integration: {'Enabled' if config.enable_slack else 'Disabled'}"
    )

    # Start Slack service if enabled
    if config.enable_slack:
        start_slack_service()

    # Log WebSocket configuration at debug level
    logger.debug(f"WebSocket ping interval: {config.websocket_ping_interval} seconds")
    logger.debug(f"WebSocket timeout: {config.websocket_timeout} seconds")
    logger.debug(
        f"WebSocket max message size: {config.websocket_max_message_size} bytes"
    )

    try:
        # Start the API server directly in the main thread
        logger.info(f"Starting API server on http://{config.host}:{config.port}")
        uvicorn.run(
            api_app,
            host=config.host,
            port=config.port,
            log_level=config.log_level.lower(),
            ws_ping_interval=config.websocket_ping_interval,
            ws_ping_timeout=config.websocket_timeout,
            ws_max_size=config.websocket_max_message_size,
        )

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
