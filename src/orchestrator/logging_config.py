"""
Smartacus Structured Logging Configuration
==========================================

Configures logging for the pipeline with support for:
- JSON structured output (for production / log aggregation)
- Human-readable output (for development)
- File rotation
- Per-module log levels

Usage:
    from src.orchestrator.logging_config import setup_logging

    setup_logging(json_output=True, log_file="pipeline.log")
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from typing import Optional


class JSONFormatter(logging.Formatter):
    """
    Formats log records as JSON lines.

    Output format:
        {"ts": "2025-...", "level": "INFO", "logger": "src.data", "msg": "...", ...}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields from record
        for key in ("run_id", "stage", "asin", "duration", "score", "event_type"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
):
    """
    Configure application logging.

    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR)
        json_output: Use JSON structured format
        log_file: Optional file path for log output (with rotation)
        max_bytes: Max file size before rotation
        backup_count: Number of rotated files to keep
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root.handlers.clear()

    # Choose formatter
    if json_output:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)-30s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler with rotation
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    root.info(
        "Logging configured: level=%s json=%s file=%s",
        level, json_output, log_file or "none",
    )
