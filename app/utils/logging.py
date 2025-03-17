"""Logging configuration for the application."""
import logging
import sys
from typing import Optional


def configure_logging(level: Optional[int] = None) -> None:
    """Configure logging for the application.

    Args:
        level: The logging level to use. Defaults to INFO.
    """
    if level is None:
        level = logging.INFO

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)
