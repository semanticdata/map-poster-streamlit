"""Logging configuration for Map Poster Generator."""

import logging
import sys
from pathlib import Path


def setup_logging(log_dir: Path = Path("logs"), level: int = logging.INFO) -> None:
    """
    Configure application logging with both file and console handlers.

    Args:
        log_dir: Directory for log files (created if doesn't exist)
        level: Logging level (default: INFO)
    """
    # Create logs directory if needed
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Format
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    log_file = log_dir / "map_poster.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
