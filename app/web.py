"""Local web server for the Pharma Purchase Assistant HTML.

Serves the dashboard HTML at / and a small JSON API the page fetches for
live POS_DB data. The API reads the assistant's own SQLite copy (warmed
by a read-only import from POS_DB); it never writes to POS_DB.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, send_file

from .connectors.sql_server import SqlServerConnector
from .core.config import PHARMACY_NAME, default_db_path
from .database.models import Product
from .database.store import Store
from .services import import_service


def product_to_html_item(figures) -> dict:
    """One product as the dashboard HTML expects it.

    The HTML's demo rows use these exact field names, so live rows map to
    the same shape and the page's own formula renders them unchanged.
    """
    item = {
        "name": figures.name,
        "pack": figures.pack,
        "supplier": figures.supplier,
        "stock": figures.stock,
        "unusable": figures.unusable,
        "incoming": figures.incoming,
        "net30": figures.net30,
        "f7": figures.fraction_7,
        "f90": figures.fraction_90,
        "reorder": figures.reorder_level,
        "max": figures.max_level,
        "cost": figures.cost,
        "packSize": figures.pack_size,
    }
    if figures.expiry_qty and figures.expiry_batch:
        item["expiry"] = {
            "batch": figures.expiry_batch,
            "date": figures.expiry_date,
            "qty": figures.expiry_qty,
            "key": figures.expiry_key,
        }
    return item


def default_html_path() -> Path:
    """Dashboard HTML shipped with the project."""
    return Path(__file__).resolve().parent.parent / "web" / "index.html"


def _connector_from_settings(store) -> SqlServerConnector:
    """Read-only connector from the store's saved connection settings."""
    return SqlServerConnector(
        server=store.get_setting("server", ""),
        database=store.get_setting("database", ""),
        auth=store.get_setting("auth", "windows"),
    )


def create_app(store=None, connector=None, html_path=None):
    """Flask app serving the dashboard and its live-data API.

    Pass a store/connector in tests; otherwise the defaults (the
    assistant's own SQLite file and a read-only POS_DB connector) apply.
    """
    store = store or Store(default_db_path())
    connector = connector or _connector_from_settings(store)
    html_path = Path(html_path) if html_path else default_html_path()
    app = Flask(__name__)

    def live_figures():
        """Live products from the store, importing once when still empty."""
        with store.session() as session:
            rows = (
                session.query(Product)
                .filter(Product.data_source == "live")
                .order_by(Product.name)
                .all()
            )
        if not rows and store.get_setting("data_source", "demo") != "live":
            import_service.refresh_from_pos(store, connector)
            with store.session() as session:
                rows = (
                    session.query(Product)
                    .filter(Product.data_source == "live")
                    .order_by(Product.name)
                    .all()
                )
        return [row.to_figures() for row in rows]

    @app.get("/")
    def index():
        if not html_path.is_file():
            return jsonify({"ok": False, "error": "Dashboard HTML not found."}), 500
        return send_file(html_path, mimetype="text/html")

    @app.get("/api/health")
    def health():
        with store.session() as session:
            live_count = (
                session.query(Product).filter(Product.data_source == "live").count()
            )
        last_fetch = store.get_setting("last_fetch", "")
        if live_count:
            return jsonify(
                {
                    "ok": True,
                    "database": "connected",
                    "live_items": live_count,
                    "last_fetch": last_fetch,
                    "message": f"POS_DB se {live_count} live items maujood hain.",
                }
            )
        try:
            detail = connector.test_connection()
        except Exception as exc:  # noqa: BLE001 - reported as the health result
            return jsonify(
                {
                    "ok": False,
                    "database": "unavailable",
                    "live_items": 0,
                    "last_fetch": last_fetch,
                    "message": f"POS_DB se rabta nahi ho saka: {exc}",
                }
            )
        return jsonify(
            {
                "ok": True,
                "database": "connected",
                "live_items": 0,
                "last_fetch": last_fetch,
                "message": "POS_DB reachable hai ("
                + detail
                + "), lekin abhi koi live import nahi hua — Refresh dabayein.",
            }
        )

    @app.get("/api/data")
    def data():
        try:
            figures = live_figures()
        except Exception as exc:  # noqa: BLE001 - reported as the API error
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify(
            {
                "ok": True,
                "source": "live",
                "pharmacy": PHARMACY_NAME,
                "fetched_at": store.get_setting("last_fetch", ""),
                "item_count": len(figures),
                "items": [product_to_html_item(fig) for fig in figures],
            }
        )

    @app.post("/api/refresh")
    def refresh():
        try:
            summary = import_service.refresh_from_pos(store, connector)
        except Exception as exc:  # noqa: BLE001 - reported as the API error
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify({"ok": True, **summary})

    return app
