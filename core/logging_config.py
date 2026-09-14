"""Application-level logging for the HEEH-V1™ DICOM Viewer.

Usage::

    from core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Engine initialized", extra={"component": "QuantitativeEngine"})
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from core.standards import redact_phi_mapping

_LOG_DIR = Path.home() / ".neuroproject_logs"
_INITIALIZED = False


def setup_logging(level: int = logging.INFO,
                  log_dir: Optional[Path] = None) -> None:
    """Configure root logger with console + rotating file handlers.

    Called once at application startup. Subsequent calls are no-ops.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    target = log_dir or _LOG_DIR
    target.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler — WARNING+ only (avoid polluting Streamlit UI)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(
        "%(levelname)s | %(name)s | %(message)s"
    ))
    root.addHandler(console)

    # File handler — INFO+ with rotation (10 MB x 5 backups)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        str(target / "neuroonco.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger. Sets up logging on first call."""
    setup_logging()
    return logging.getLogger(name)


def audit_event(logger: logging.Logger, event: str, **context) -> None:
    """Write a PHI-safe audit event using only redacted context."""
    safe_context = redact_phi_mapping(context)
    logger.info("audit.%s | %s", event, safe_context)
