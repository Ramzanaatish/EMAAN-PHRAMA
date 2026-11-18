"""Static configuration and paths.

The pharmacy name is fixed here and used in the window header, the setup
wizard, the pharmacy profile and every report, so it can never drift
between screens.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PHARMACY_NAME = "EMAN PHARMACY & VACCINE"
APP_NAME = "Pharma Purchase Assistant"

# Same-PC deployment: the helper and SmilePOS run on one Windows PC.
DEFAULT_SERVER = r"localhost\SQLEXPRESS"
DEFAULT_DATABASE = "POS_DB"
DEFAULT_AUTH = "windows"  # "windows" or "sql_login"

COVER_DAY_OPTIONS = (7, 14, 21, 30)
ANALYSIS_DAY_OPTIONS = (7, 30, 90)
DEFAULT_COVER_DAYS = 21
DEFAULT_ANALYSIS_DAYS = 30
DEFAULT_SAFETY_DAYS = 5
MAX_SAFETY_DAYS = 30

DEMO_DATA_LABEL = "PREVIEW — sample data"


def app_data_dir() -> Path:
    """Local folder for the assistant's own SQLite database and files."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "PharmaPurchaseAssistant" / "data"
    return Path.home() / ".local" / "share" / "PharmaPurchaseAssistant" / "data"


def default_db_path() -> Path:
    return app_data_dir() / "pharma_purchase.db"
