"""Logging configuration for the application."""

import logging
import sys
from typing import Optional

from app.config import config


def configure_logging(level: Optional[str] = None) -> None:
    """Configure logging for the application.

    Args:
        level: The logging level to use. Defaults to the value in config.
    """
    if level is None:
        level = config.log_level

    # Convert string level to numeric level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    # Create formatter
    formatter = logging.Formatter(
        config.log_format,
        datefmt=config.log_date_format,
    )
    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)

    # Log configuration
    logging.debug(f"Logging configured with level: {level}")
