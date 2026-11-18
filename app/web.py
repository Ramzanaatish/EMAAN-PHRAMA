"""Local web server for the Pharma Purchase Assistant HTML.

Serves the dashboard HTML at / and a small JSON API the page fetches for
live POS_DB data. The API reads the assistant's own SQLite copy (warmed
by a read-only import from POS_DB); it never writes to POS_DB.

The SQL Server address comes from the saved settings (Settings tab), not
from a hardcoded value: every request builds its connector from the
store's current "server" setting, so changing the address takes effect
without restarting the server.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_file

from .connectors.sql_server import SqlServerConnector
from .core.config import (
    DEFAULT_AUTH,
    DEFAULT_DATABASE,
    DEFAULT_SERVER,
    PHARMACY_NAME,
    default_db_path,
    validate_server_address,
)
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


def _connector_from_settings(store, factory=SqlServerConnector) -> SqlServerConnector:
    """Read-only connector from the store's saved connection settings."""
    return factory(
        server=store.get_setting("server", DEFAULT_SERVER),
        database=store.get_setting("database", DEFAULT_DATABASE),
        auth=store.get_setting("auth", DEFAULT_AUTH),
    )


def create_app(store=None, connector=None, html_path=None, connector_factory=None):
    """Flask app serving the dashboard and its live-data API.

    Pass a store/connector in tests; otherwise the defaults (the
    assistant's own SQLite file and a read-only POS_DB connector) apply.
    A passed connector is used as-is; otherwise a fresh connector is
    built from the store's saved settings on every request, so a changed
    server address takes effect without a restart.
    """
    store = store or Store(default_db_path())
    factory = connector_factory or SqlServerConnector
    injected = connector
    html_path = Path(html_path) if html_path else default_html_path()
    app = Flask(__name__)

    def get_connector():
        if injected is not None:
            return injected
        return _connector_from_settings(store, factory=factory)

    def saved_server() -> str:
        return store.get_setting("server", DEFAULT_SERVER)

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
            import_service.refresh_from_pos(store, get_connector())
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

    @app.get("/api/settings")
    def get_settings():
        return jsonify(
            {
                "ok": True,
                "server": saved_server(),
                "database": store.get_setting("database", DEFAULT_DATABASE),
                "auth": store.get_setting("auth", DEFAULT_AUTH),
            }
        )

    @app.post("/api/settings")
    def save_settings():
        body = request.get_json(silent=True) or {}
        try:
            if "server" in body:
                server = validate_server_address(body["server"])
                store.set_setting("server", server)
            if "database" in body:
                database = str(body["database"] or "").strip()
                if not database:
                    raise ValueError("Database is empty.")
                store.set_setting("database", database)
            if "auth" in body:
                auth = str(body["auth"] or "").strip()
                if auth not in ("windows", "sql_login"):
                    raise ValueError("Auth must be 'windows' or 'sql_login'.")
                store.set_setting("auth", auth)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(
            {
                "ok": True,
                "server": saved_server(),
                "database": store.get_setting("database", DEFAULT_DATABASE),
                "auth": store.get_setting("auth", DEFAULT_AUTH),
            }
        )

    @app.post("/api/test-connection")
    def test_connection():
        body = request.get_json(silent=True) or {}
        try:
            server = validate_server_address(
                body.get("server") or saved_server()
            )
            database = str(body.get("database") or "").strip() or store.get_setting(
                "database", DEFAULT_DATABASE
            )
            auth = str(body.get("auth") or "").strip() or store.get_setting(
                "auth", DEFAULT_AUTH
            )
            if not database:
                raise ValueError("Database is empty.")
            if auth not in ("windows", "sql_login"):
                raise ValueError("Auth must be 'windows' or 'sql_login'.")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            detail = factory(server=server, database=database, auth=auth).test_connection()
        except Exception as exc:  # noqa: BLE001 - reported as the test result
            return jsonify(
                {
                    "ok": False,
                    "server": server,
                    "message": f"{server} se rabta nahi ho saka: {exc}",
                }
            )
        return jsonify({"ok": True, "server": server, "message": detail})

    @app.get("/api/health")
    def health():
        with store.session() as session:
            live_count = (
                session.query(Product).filter(Product.data_source == "live").count()
            )
        last_fetch = store.get_setting("last_fetch", "")
        server = saved_server()
        if live_count:
            return jsonify(
                {
                    "ok": True,
                    "database": "connected",
                    "server": server,
                    "live_items": live_count,
                    "last_fetch": last_fetch,
                    "message": f"POS_DB se {live_count} live items maujood hain.",
                }
            )
        try:
            detail = get_connector().test_connection()
        except Exception as exc:  # noqa: BLE001 - reported as the health result
            return jsonify(
                {
                    "ok": False,
                    "database": "unavailable",
                    "server": server,
                    "live_items": 0,
                    "last_fetch": last_fetch,
                    "message": f"POS_DB se rabta nahi ho saka: {exc}",
                }
            )
        return jsonify(
            {
                "ok": True,
                "database": "connected",
                "server": server,
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
                "server": saved_server(),
                "fetched_at": store.get_setting("last_fetch", ""),
                "item_count": len(figures),
                "items": [product_to_html_item(fig) for fig in figures],
            }
        )

    @app.post("/api/refresh")
    def refresh():
        try:
            summary = import_service.refresh_from_pos(store, get_connector())
        except Exception as exc:  # noqa: BLE001 - reported as the API error
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify({"ok": True, **summary})

    return app
