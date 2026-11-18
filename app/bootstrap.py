"""Bootstrap: logging, data directory and store creation."""

from __future__ import annotations

import logging
from pathlib import Path

from .core.config import app_data_dir, default_db_path
from .database.store import Store


def setup_logging() -> None:
    log_dir = app_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "pharma_purchase.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def ensure_store(db_path: Path | None = None) -> Store:
    """Create (or open) the assistant's own SQLite database."""
    return Store(db_path or default_db_path())
