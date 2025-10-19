"""Centralised logging configuration for the headless_sidewalkreator package."""

from __future__ import annotations

import logging
from typing import Optional


def _configure_root_logger(level: int = logging.WARNING) -> None:
    """Ensure the root logger has at least one handler configured."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=level)
    else:
        logging.getLogger().setLevel(level)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger with the package defaults applied."""
    _configure_root_logger()
    logger = logging.getLogger(name if name else "headless_sidewalkreator")
    return logger


__all__ = ["get_logger"]
