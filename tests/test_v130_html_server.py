"""Tests for v1.3.0: HTML file + server-connector setup.

- The Flask API answers CORS headers, so a file:// dashboard (opened
  with a double-click) can call http://127.0.0.1:5000/api/...
- web/index.html uses an API base (127.0.0.1:5000 when opened as file://,
  same-origin otherwise) for every fetch call, and tells the user in
  Roman Urdu to run PharmaServer.exe when the server is unreachable.
- server.py binds 127.0.0.1:5000 by default.
"""

from __future__ import annotations

from pathlib import Path

import server as server_module
from app.web import create_app

HTML_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"

# file:// pages send "Origin: null" — use it so the tests mirror reality.
FILE_ORIGIN = {"Origin": "null"}


class _StubConnector:
    """POS connector stub: reachable, two products, canned sales."""

    def __init__(self, server=r"localhost\SQLEXPRESS", database="POS_DB", auth="windows"):
        self.server = server
        self.database = database
        self.auth = auth

    def test_connection(self):
        return "Connected to POS_DB on localhost\\SQLEXPRESS (test)"

    def fetch_products(self):
        return [
            {
                "ItemCode": "A1",
                "ItemName": "Test Panadol",
                "ItemStock": 50,
                "ReOrderLevel": 100,
                "MaxLevel": 500,
                "VendorCode": "V1",
                "Manufacturer": "GSK",
                "ItemGroup": "Tablet",
            }
        ]

    def fetch_stock(self):
        return [{"ItemCode": "A1", "InQty": 60, "OutQty": 10}]

    def fetch_suppliers(self):
        return [{"AccountCode": "V1", "AccountName": "Premier Agencies"}]

    def fetch_sales(self, days):
        return [{"ItemCode": "A1", "NetQty": {7: 70, 30: 300, 90: 900}[days]}]


def _make_client(store, tmp_path):
    html_path = tmp_path / "index.html"
    html_path.write_text(
        "<html><head><title>Pharma Purchase Assistant</title></head>"
        "<body>dashboard</body></html>",
        encoding="utf-8",
    )
    app = create_app(store=store, connector=_StubConnector(), html_path=html_path)
    app.config["TESTING"] = True
    return app.test_client()


def test_cors_headers_on_api_response(store, tmp_path):
    res = _make_client(store, tmp_path).get("/api/health", headers=FILE_ORIGIN)
    assert res.status_code == 200
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in res.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in res.headers["Access-Control-Allow-Headers"]


def test_cors_preflight_options(store, tmp_path):
    res = _make_client(store, tmp_path).options("/api/data", headers=FILE_ORIGIN)
    assert res.status_code == 200
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    methods = res.headers["Access-Control-Allow-Methods"]
    assert "GET" in methods and "POST" in methods and "OPTIONS" in methods


def test_cors_headers_on_post(store, tmp_path):
    res = _make_client(store, tmp_path).post(
        "/api/settings",
        json={"server": r"localhost\SQLEXPRESS"},
        headers=FILE_ORIGIN,
    )
    assert res.status_code == 200
    assert res.headers["Access-Control-Allow-Origin"] == "*"


def test_html_has_file_api_base():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert 'window.location.protocol === "file:"' in html
    assert "http://127.0.0.1:5000" in html
    assert "function apiUrl(path)" in html
    # Same-origin (server-served page) keeps an empty base.
    assert 'var API_BASE = (window.location.protocol === "file:")' in html


def test_html_all_fetch_calls_use_api_base():
    html = HTML_PATH.read_text(encoding="utf-8")
    for url in (
        "/api/data",
        "/api/health",
        "/api/refresh",
        "/api/settings",
        "/api/test-connection",
    ):
        assert f'fetch(apiUrl("{url}")' in html, f"{url} is not fetched via apiUrl"
    assert 'fetch("/api/' not in html, "a bare relative fetch() is still left"


def test_html_server_unreachable_hint():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "Server nahi chal raha" in html
    assert "PharmaServer.exe chalao" in html
    assert "8080" not in html


def test_server_default_binds_localhost_5000():
    parser = server_module.build_parser()
    assert parser.get_default("host") == "127.0.0.1"
    assert parser.get_default("port") == 5000
