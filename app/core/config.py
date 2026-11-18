"""Static configuration and paths.

The pharmacy name is fixed here and used in the window header, the setup
wizard, the pharmacy profile and every report, so it can never drift
between screens.
"""

from __future__ import annotations

import os
import re
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


def resource_path(filename: str) -> Path:
    """Path to a bundled asset, from source or a PyInstaller build."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / filename
    return Path(__file__).resolve().parents[2] / "assets" / filename


SERVER_ADDRESS_RE = re.compile(
    r"^[A-Za-z0-9_.\-]+(\\[A-Za-z0-9_.\-#$]+)?(,\d{1,5})?$"
)


def validate_server_address(value: str) -> str:
    """Validate a SQL Server address and return it stripped.

    Accepts a server name or IP, with an optional instance
    (SERVER\\INSTANCE) and/or port (SERVER,1433).
    Raises ValueError when the address is empty or malformed.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("Server address is empty.")
    if not SERVER_ADDRESS_RE.match(cleaned):
        raise ValueError(
            f"Invalid server address {cleaned!r}. Use SERVER, SERVER\\INSTANCE, "
            "an IP, or a server with a port (SERVER,1433)."
        )
    port = cleaned.rsplit(",", 1)[-1] if "," in cleaned else ""
    if port and not 1 <= int(port) <= 65535:
        raise ValueError(f"Invalid port {port!r} in server address.")
    return cleaned
