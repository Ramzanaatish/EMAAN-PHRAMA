"""Tests for the v1.2.0 fixes: POS fetch robustness + refresh speed.

Covers: driver auto-detection, fetch_products column discovery, the
single-query sales aggregation, plain-language connection errors, the
one-connection refresh (and its fallback for older connectors), and the
single-load service views.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.connectors import sql_server as connector_module
from app.connectors.sql_server import (
    DRIVER_FALLBACK,
    SqlServerConnector,
    detect_driver,
)
from app.core.errors import ConnectorError
from app.services import import_service, purchase_service, stock_service
from tests.test_connector import StubConnector


# ------------------------------------------------------------------ driver
def test_detect_driver_picks_newest_installed(monkeypatch):
    monkeypatch.setattr(
        connector_module.pyodbc,
        "drivers",
        lambda: ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"],
    )
    assert detect_driver() == "ODBC Driver 18 for SQL Server"


def test_detect_driver_returns_none_when_nothing_installed(monkeypatch):
    monkeypatch.setattr(connector_module.pyodbc, "drivers", lambda: [])
    assert detect_driver() is None
    assert SqlServerConnector().resolved_driver() == DRIVER_FALLBACK


def test_driver18_connection_string_trusts_certificate():
    text = SqlServerConnector(driver="ODBC Driver 18 for SQL Server").connection_string()
    assert "TrustServerCertificate=yes" in text
    assert "Encrypt=yes" in text


def test_driver17_connection_string_has_no_encrypt_flag():
    text = SqlServerConnector(driver="ODBC Driver 17 for SQL Server").connection_string()
    assert "TrustServerCertificate" not in text


# ------------------------------------------------------- column discovery
def test_fetch_products_selects_only_existing_columns():
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "ItemName"},
         {"COLUMN_NAME": "ItemStock"}],
        [{"ItemCode": "A", "ItemName": "Panadol", "ItemStock": 5}],
    ])
    rows = connector.fetch_products()
    assert rows[0]["ItemCode"] == "A"
    # Missing columns are normalised to None instead of failing the import.
    assert rows[0]["MaxLevel"] is None
    assert rows[0]["ReOrderLevel"] is None
    assert "MaxLevel" not in connector.seen[-1]
    assert "ItemCode" in connector.seen[-1]


def test_fetch_products_fails_loudly_without_item_code():
    connector = StubConnector([[{"COLUMN_NAME": "ItemName"}]])
    with pytest.raises(ConnectorError, match="ItemCode"):
        connector.fetch_products()


# ------------------------------------------------------------ sales query
def test_fetch_sales_all_is_one_query_for_three_windows():
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"}],
        [{"n": 5}],   # date probe: VoucherDate has recent rows
        [{"n": 10}],  # diag: SaleDetail rows
        [{"n": 10}],  # diag: rows joined with a voucher
        [{"n": 8}],   # diag: rows inside the 90-day window
        [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20}],
    ])
    rows = connector.fetch_sales_all()
    assert rows == [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20}]
    assert "Net7" in connector.seen[-1]
    assert "Net30" in connector.seen[-1]
    assert "Net90" in connector.seen[-1]
    assert "SaleDetail" in connector.seen[-1]
    assert "VoucherDate" in connector.seen[-1]
    assert len(connector.seen) == 7  # 2 column lookups + probe + 3 diag + 1 aggregation
    assert connector.last_sales_diag["date_column"] == "VoucherDate"
    assert connector.last_sales_diag["items_with_sales"] == 1


def test_fetch_sales_wrapper_reads_the_right_window():
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"}],
        [{"n": 5}],
        [{"n": 10}],
        [{"n": 10}],
        [{"n": 8}],
        [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20}],
    ])
    assert connector.fetch_sales(30) == [{"ItemCode": "A", "NetQty": 9}]


# --------------------------------------------------------- friendly errors
def test_friendly_error_names_browser_when_server_not_found():
    connector = SqlServerConnector()
    error = connector._friendly_error(
        Exception("[08001] [Microsoft][ODBC Driver 17 for SQL Server] "
                  "SQL Server Network Interfaces: Error Locating Server/Instance Specified")
    )
    assert "Browser" in str(error)
    assert "TCP/IP" in str(error)


def test_friendly_error_names_driver_when_missing():
    connector = SqlServerConnector()
    error = connector._friendly_error(
        Exception("[IM002] [unixODBC][Driver Manager]Data source name not found")
    )
    assert "ODBC Driver" in str(error)


def test_friendly_error_names_login_problem():
    connector = SqlServerConnector()
    error = connector._friendly_error(
        Exception("[28000] [Microsoft][ODBC Driver 17 for SQL Server]Login failed for user")
    )
    assert "Login" in str(error)


def test_friendly_error_names_missing_database():
    connector = SqlServerConnector(database="WRONG_DB")
    error = connector._friendly_error(
        Exception("Cannot open database 'WRONG_DB' requested by the login")
    )
    assert "WRONG_DB" in str(error)


# ------------------------------------------------- one-connection refresh
class SessionConnector:
    """Fake connector with a session() context manager; counts opens."""

    def __init__(self):
        self.sessions_opened = 0
        self.calls = []

    @contextmanager
    def session(self):
        self.sessions_opened += 1
        yield "fake-conn"

    def fetch_products(self, conn=None):
        self.calls.append(("products", conn))
        return [
            {"ItemCode": "A", "ItemName": "Panadol", "ItemStock": 10,
             "ReOrderLevel": 5, "MaxLevel": 50, "VendorCode": "V1",
             "Manufacturer": "GSK", "ItemGroup": "Tablet"},
        ]

    def fetch_stock(self, conn=None):
        self.calls.append(("stock", conn))
        return [{"ItemCode": "A", "InQty": 12, "OutQty": 2}]

    def fetch_suppliers(self, conn=None):
        self.calls.append(("suppliers", conn))
        return [{"AccountCode": "V1", "AccountName": "ABC Traders"}]

    def fetch_sales_all(self, conn=None):
        self.calls.append(("sales", conn))
        return [{"ItemCode": "A", "Net7": 7, "Net30": 30, "Net90": 90}]


def test_refresh_uses_one_connection(store):
    connector = SessionConnector()
    result = import_service.refresh_from_pos(store, connector)
    assert connector.sessions_opened == 1
    # Every fetch ran on the same (fake) connection.
    assert all(conn == "fake-conn" for _name, conn in connector.calls)
    assert {name for name, _conn in connector.calls} == {
        "products", "stock", "suppliers", "sales",
    }
    assert result["status"] == "ok"
    assert result["rows_imported"] == 1
    items = stock_service.visible_items(store)
    assert len(items) == 1
    assert items[0].name == "Panadol"
    assert items[0].stock == 10  # InQty 12 - OutQty 2
    assert items[0].supplier == "ABC Traders"
    assert items[0].net30 == 30
    assert store.get_setting("data_source") == "live"
    assert store.get_setting("demo_data") == "off"


class LegacyConnector:
    """Old-style connector: no session(), no fetch_sales_all()."""

    def fetch_products(self):
        return [
            {"ItemCode": "B", "ItemName": "Brufen", "ItemStock": 3,
             "ReOrderLevel": 2, "MaxLevel": 20, "VendorCode": "",
             "Manufacturer": "", "ItemGroup": ""},
        ]

    def fetch_stock(self):
        return []

    def fetch_suppliers(self):
        return []

    def fetch_sales(self, days):
        return [{"ItemCode": "B", "NetQty": days}]


def test_refresh_falls_back_for_legacy_connectors(store):
    result = import_service.refresh_from_pos(store, LegacyConnector())
    assert result["status"] == "ok"
    assert result["rows_imported"] == 1
    items = stock_service.visible_items(store)
    assert items[0].net30 == 30
    assert items[0].net_7 == 7
    assert items[0].net_90 == 90


# ---------------------------------------------------- single-load views
def test_service_views_accept_preloaded_items(demo_store):
    items = stock_service.visible_items(demo_store)
    assert stock_service.kpis(demo_store, 30, 21, 5) == stock_service.kpis(
        demo_store, 30, 21, 5, items=items
    )
    assert stock_service.demand_ranking(demo_store, 30, items=items) == \
        stock_service.demand_ranking(demo_store, 30)
    assert stock_service.suppliers(demo_store, items=items) == \
        stock_service.suppliers(demo_store)
    assert stock_service.stock_rows(demo_store, items=items) == \
        stock_service.stock_rows(demo_store)


def test_suggestions_use_preloaded_items_and_overrides(demo_store):
    items = stock_service.visible_items(demo_store)
    details = stock_service.override_details(demo_store)
    rows = purchase_service.suggestions(
        demo_store, 30, 21, 5, items=items, override_details=details
    )
    assert rows == purchase_service.suggestions(demo_store, 30, 21, 5)


def test_override_details_carries_latest_qty_and_reason(demo_store, panadol):
    figures = next(
        item for item in stock_service.visible_items(demo_store)
        if item.name == panadol.name
    )
    purchase_service.save_override(demo_store, figures, 10, "pehli wajah")
    purchase_service.save_override(demo_store, figures, 25, "doosri wajah")
    details = stock_service.override_details(demo_store)
    assert details[figures.item_code]["qty"] == 25
    assert details[figures.item_code]["reason"] == "doosri wajah"
