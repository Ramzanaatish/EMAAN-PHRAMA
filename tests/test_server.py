"""Tests for the live-data web server (Flask app, mocked POS connector)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import ConnectorError
from app.web import create_app, product_to_html_item

# Field names the dashboard HTML's demo rows use (see web/index.html ITEMS).
# v1.3.3 adds lastSale (last sale date, ISO or null) for the urgency sort.
HTML_ITEM_FIELDS = {
    "name",
    "pack",
    "supplier",
    "stock",
    "unusable",
    "incoming",
    "net30",
    "f7",
    "f90",
    "reorder",
    "max",
    "cost",
    "packSize",
    "lastSale",
}


class FakeConnector:
    """Canned POS rows: two products, one supplier, 7/30/90-day sales."""

    def __init__(self):
        self.products = [
            {
                "ItemCode": "A1",
                "ItemName": "Test Panadol",
                "ItemStock": 50,
                "ReOrderLevel": 100,
                "MaxLevel": 500,
                "VendorCode": "V1",
                "Manufacturer": "GSK",
                "ItemGroup": "Tablet",
            },
            {
                "ItemCode": "B2",
                "ItemName": "Test Brufen",
                "ItemStock": 10,
                "ReOrderLevel": 50,
                "MaxLevel": 300,
                "VendorCode": "V1",
                "Manufacturer": "Abbott",
                "ItemGroup": "Tablet",
            },
        ]

    def test_connection(self):
        return "Connected to POS_DB on localhost\\SQLEXPRESS (test)"

    def fetch_products(self):
        return list(self.products)

    def fetch_stock(self):
        return [
            {"ItemCode": "A1", "InQty": 60, "OutQty": 10},
            {"ItemCode": "B2", "InQty": 15, "OutQty": 5},
        ]

    def fetch_suppliers(self):
        return [{"AccountCode": "V1", "AccountName": "Premier Agencies"}]

    def fetch_sales(self, days):
        qty = {7: 70, 30: 300, 90: 900}
        return [
            {"ItemCode": "A1", "NetQty": qty[days]},
            {"ItemCode": "B2", "NetQty": qty[days] // 2},
        ]


class FailingConnector(FakeConnector):
    """POS that is unreachable: every call raises."""

    def test_connection(self):
        raise ConnectorError("SQL Server is not reachable.")

    def fetch_products(self):
        raise ConnectorError("SQL Server is not reachable.")


def _make_client(store, tmp_path, connector):
    html_path = tmp_path / "index.html"
    html_path.write_text(
        "<html><head><title>Pharma Purchase Assistant</title></head>"
        "<body>dashboard</body></html>",
        encoding="utf-8",
    )
    app = create_app(store=store, connector=connector, html_path=html_path)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def client(store, tmp_path):
    return _make_client(store, tmp_path, FakeConnector())


@pytest.fixture()
def failing_client(store, tmp_path):
    return _make_client(store, tmp_path, FailingConnector())


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Pharma Purchase Assistant" in res.data


def test_health_with_live_rows(client):
    client.post("/api/refresh")
    body = client.get("/api/health").get_json()
    assert body["ok"] is True
    assert body["database"] == "connected"
    assert body["live_items"] == 2


def test_health_without_live_rows_probes_db(client):
    body = client.get("/api/health").get_json()
    assert body["ok"] is True
    assert body["database"] == "connected"
    assert body["live_items"] == 0


def test_health_db_unreachable(failing_client):
    body = failing_client.get("/api/health").get_json()
    assert body["ok"] is False
    assert body["database"] == "unavailable"
    assert "not reachable" in body["message"]


def test_data_returns_live_items_in_html_shape(client):
    client.post("/api/refresh")
    res = client.get("/api/data")
    body = res.get_json()
    assert res.status_code == 200
    assert body["ok"] is True
    assert body["source"] == "live"
    assert body["pharmacy"] == "EMAN PHARMACY & VACCINE"
    assert body["item_count"] == 2
    by_name = {item["name"]: item for item in body["items"]}
    panadol = by_name["Test Panadol"]
    assert set(panadol.keys()) == HTML_ITEM_FIELDS
    assert panadol["stock"] == 50
    assert panadol["net30"] == 300
    assert panadol["f7"] == pytest.approx(70 / 300)
    assert panadol["f90"] == pytest.approx(3.0)
    assert panadol["reorder"] == 100
    assert panadol["supplier"] == "Premier Agencies"


def test_data_imports_when_empty(client):
    body = client.get("/api/data").get_json()
    assert body["ok"] is True
    assert body["item_count"] == 2
    assert {item["name"] for item in body["items"]} == {"Test Panadol", "Test Brufen"}


def test_data_db_unreachable_returns_error(failing_client):
    res = failing_client.get("/api/data")
    body = res.get_json()
    assert res.status_code == 503
    assert body["ok"] is False
    assert "not reachable" in body["error"]


def test_refresh_endpoint(client):
    res = client.post("/api/refresh")
    body = res.get_json()
    assert res.status_code == 200
    assert body["ok"] is True
    assert body["rows_imported"] == 2
    assert client.get("/api/data").get_json()["item_count"] == 2


def test_refresh_db_unreachable_returns_error(failing_client):
    res = failing_client.post("/api/refresh")
    body = res.get_json()
    assert res.status_code == 503
    assert body["ok"] is False


def test_item_shape_matches_demo(panadol):
    item = product_to_html_item(panadol)
    assert set(item.keys()) == HTML_ITEM_FIELDS
    assert item["name"] == "Panadol Extra 500mg"
    assert item["net30"] == 1860
    assert item["f7"] == 0.24
    assert item["f90"] == 2.9
    assert item["reorder"] == 300
    assert item["max"] == 2400
    assert item["cost"] == 42
    assert item["packSize"] == 10


def test_html_calls_the_api():
    html = (
        Path(__file__).resolve().parent.parent / "web" / "index.html"
    ).read_text(encoding="utf-8")
    for url in ("/api/data", "/api/health", "/api/refresh"):
        assert url in html
    assert "liveBadge" in html
    assert "fetch(" in html


class RecordingConnector(FakeConnector):
    """FakeConnector that records the server it was built with."""

    instances = []

    def __init__(
        self,
        server=r"localhost\SQLEXPRESS",
        database="POS_DB",
        auth="windows",
    ):
        super().__init__()
        self.server = server
        self.database = database
        self.auth = auth
        RecordingConnector.instances.append(self)

    def test_connection(self):
        return f"Connected to {self.database} on {self.server} (test)"


@pytest.fixture()
def recording_client(store, tmp_path):
    RecordingConnector.instances.clear()
    html_path = tmp_path / "index.html"
    html_path.write_text(
        "<html><head><title>Pharma Purchase Assistant</title></head>"
        "<body>dashboard</body></html>",
        encoding="utf-8",
    )
    app = create_app(
        store=store, html_path=html_path, connector_factory=RecordingConnector
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_get_settings_returns_defaults(client):
    body = client.get("/api/settings").get_json()
    assert body["ok"] is True
    assert body["server"] == r"localhost\SQLEXPRESS"
    assert body["database"] == "POS_DB"
    assert body["auth"] == "windows"


def test_save_settings_persists_server(client, store):
    res = client.post("/api/settings", json={"server": r"192.168.1.10\SQLEXPRESS"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["server"] == r"192.168.1.10\SQLEXPRESS"
    assert store.get_setting("server") == r"192.168.1.10\SQLEXPRESS"
    assert client.get("/api/settings").get_json()["server"] == (
        r"192.168.1.10\SQLEXPRESS"
    )


def test_save_settings_rejects_bad_server(client, store):
    res = client.post("/api/settings", json={"server": "not a server!!"})
    assert res.status_code == 400
    assert res.get_json()["ok"] is False
    assert store.get_setting("server") == r"localhost\SQLEXPRESS"


def test_test_connection_uses_typed_server(recording_client):
    res = recording_client.post(
        "/api/test-connection", json={"server": r"DESKTOP-SJO68CG\SQLEXPRESS"}
    )
    body = res.get_json()
    assert res.status_code == 200
    assert body["ok"] is True
    assert body["server"] == r"DESKTOP-SJO68CG\SQLEXPRESS"
    assert RecordingConnector.instances[-1].server == (
        r"DESKTOP-SJO68CG\SQLEXPRESS"
    )


def test_test_connection_rejects_bad_server(recording_client):
    res = recording_client.post("/api/test-connection", json={"server": "bad server!!"})
    assert res.status_code == 400
    assert res.get_json()["ok"] is False
    assert RecordingConnector.instances == []


def test_data_uses_saved_server(recording_client):
    recording_client.post("/api/settings", json={"server": r"192.168.1.10\SQLEXPRESS"})
    body = recording_client.get("/api/data").get_json()
    assert body["ok"] is True
    assert body["item_count"] == 2
    assert body["server"] == r"192.168.1.10\SQLEXPRESS"
    assert RecordingConnector.instances[-1].server == r"192.168.1.10\SQLEXPRESS"


def test_health_reports_server(client):
    body = client.get("/api/health").get_json()
    assert body["server"] == r"localhost\SQLEXPRESS"
