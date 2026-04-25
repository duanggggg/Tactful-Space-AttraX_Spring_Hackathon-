"""Logging bootstrap for the application."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: Path | None = None) -> None:
    """Configure process-wide logging once."""

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "app.log", encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""

    return logging.getLogger(name)
