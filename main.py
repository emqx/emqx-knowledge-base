"""Main entry point for the application."""
import logging
import sys
import signal

from app.config import config
from app.services.slack_service import slack_service
from app.utils.logging import configure_logging


def main():
    """Start the application."""
    # Configure logging
    configure_logging()
    logger = logging.getLogger(__name__)

    # Validate configuration
    missing_config = config.validate_config()
    if missing_config:
        logger.error(f"Missing required configuration: {', '.join(missing_config)}")
        logger.error("Please set these environment variables in a .env file or in your environment.")
        sys.exit(1)

    logger.info("Starting EMQX Knowledge Base Slack Bot...")
    
    try:
        # Start the Slack bot
        slack_service.start()
        logger.info("Slack bot started successfully!")
        
        # Keep the main thread running until interrupted
        def signal_handler(sig, frame):
            logger.info("Shutting down...")
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.pause()  # Wait for a signal
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error starting the application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
