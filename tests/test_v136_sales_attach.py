"""Tests for v1.3.6: sales attach to kept products.

Live (21 Nov 2026, server window): the refresh counted 8,678
SaleDetail rows, 7,200 in the 90-day window, 781 items with sales
and 1,388 items with a last sale — yet the dashboard showed NET
UNITS SOLD (30d) 0, 0 suggestions and empty "aakhri sale" dates.

Root cause: the lookup dicts were keyed by RAW pyodbc values while
products are looked up by str(code).strip(). An INT ItemCode (or a
CHAR value padded with spaces) never matched its string code, so
sales, stock and supplier rows silently missed every product. The
fix normalises every lookup dict to str(code).strip() at import
time, and the refresh now also reports "kept with sales" /
"kept with last sale" so a future attach failure is visible in the
server window instead of hiding behind a 0 dashboard.
"""

from __future__ import annotations

from app.database.models import Product
from app.services import import_service


def _product(code, name="Panadol"):
    return {
        "ItemCode": code, "ItemName": name, "ItemStock": 0,
        "ReOrderLevel": 0, "MaxLevel": 0, "VendorCode": "",
        "Manufacturer": "", "ItemGroup": "",
    }


class _IntCodeConnector:
    """SaleDetail hands back INT codes; ItemInfo hands back strings."""

    def fetch_products(self, conn=None):
        return [_product("101"), _product("102", "Brufen")]

    def fetch_stock(self, conn=None):
        return [{"ItemCode": 101, "InQty": 5, "OutQty": 5}]

    def fetch_suppliers(self, conn=None):
        return []

    def fetch_sales_all(self, conn=None):
        return [{
            "ItemCode": 101, "Net7": 70, "Net30": 300, "Net90": 900,
            "LastSale": "2026-11-20",
        }]

    def fetch_stock_entries(self, conn=None):
        return {"101": 1, "102": 1}


def test_int_sales_code_attaches_to_string_product(store):
    result = import_service.refresh_from_pos(store, _IntCodeConnector())
    assert result["status"] == "ok"
    assert result["diagnostics"]["kept_with_sales"] == 1
    assert result["diagnostics"]["kept_with_last_sale"] == 1
    with store.session() as session:
        row = session.get(Product, "101")
        assert row.net_30 == 300
        assert row.net_7 == 70
        assert row.last_sale_date == "2026-11-20"
        # The stock row was keyed by the same raw INT code.
        assert row.stock == 0  # 5 in - 5 out


class _PaddedCodeConnector(_IntCodeConnector):
    """CHAR-style codes padded with spaces on the sales/stock side."""

    def fetch_stock(self, conn=None):
        return [{"ItemCode": " 101 ", "InQty": 10, "OutQty": 2}]

    def fetch_sales_all(self, conn=None):
        return [{
            "ItemCode": " 101 ", "Net7": 7, "Net30": 30, "Net90": 90,
            "LastSale": "2026-11-19",
        }]

    def fetch_stock_entries(self, conn=None):
        return {" 101 ": 1, " 102 ": 1}


def test_space_padded_codes_attach(store):
    result = import_service.refresh_from_pos(store, _PaddedCodeConnector())
    assert result["status"] == "ok"
    assert result["diagnostics"]["kept_with_sales"] == 1
    assert result["diagnostics"]["kept_with_last_sale"] == 1
    with store.session() as session:
        row = session.get(Product, "101")
        assert row.net_30 == 30
        assert row.stock == 8  # 10 in - 2 out, via the padded stock row
        assert row.last_sale_date == "2026-11-19"
