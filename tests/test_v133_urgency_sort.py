"""Tests for v1.3.3: out-of-stock-first urgency sort + suggestions audit.

Nelson (21 Nov 2026, live screenshot after the v1.3.2 proxy filter):
TOTAL ITEMS 2,535 (proxy kept), but OUT OF STOCK 0 — the proxy hid the
very medicines that need buying, because an out-of-stock medicine has
stock=0, net30=0, reorder=0, max=0, incoming=0, unusable=0: no signal
in the fields /api/data sends. Suggestions were still 0 (server sends
net30=0 for every item).

1. SORT — out-of-stock first, most recently out of stock first.
   Signal: per-item last sale date (MAX sale date from SaleDetail,
   any voucher ever — not just the 90-day window). Undated items sort
   after dated ones, then days-of-cover. Same order in All Stock,
   Reorder Suggestions, the attention list and the report's Urgent
   table, in the desktop app and the HTML alike.
2. EXACT FILTER — the server-side PurchaseDetail/OpeningStock filter
   (v1.3.1) is the real fix for hidden out-of-stock items: an item
   with a purchase entry but all-zero live fields MUST be kept.
3. SUGGESTIONS AUDIT — the date probe now counts JOINED detail rows
   (a column can hold recent vouchers while the VoucherNo join drops
   every detail row) and dates parse with a dd/mm/yyyy fallback
   (style 103). Last-sale dates ride along in the same query.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.connectors.sql_server import SqlServerConnector
from app.core.purchase import ItemFigures, urgency_key
from app.database.models import Product
from app.database.store import Store
from app.services import import_service, purchase_service, stock_service
from app.web import create_app, product_to_html_item
from tests.test_connector import StubConnector

HTML_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


# ------------------------------------------------------------ urgency sort
def test_urgency_key_out_first_most_recent_first():
    recent_out = ItemFigures(name="A", stock=0, net30=300, last_sale_date="2026-11-20")
    older_out = ItemFigures(name="B", stock=0, net30=300, last_sale_date="2026-11-10")
    undated_out = ItemFigures(name="D", stock=0, net30=30, last_sale_date="")
    stocked = ItemFigures(name="C", stock=10, net30=300, last_sale_date="2026-11-21")
    items = [stocked, undated_out, older_out, recent_out]
    assert [item.name for item in sorted(items, key=urgency_key)] == [
        "A", "B", "D", "C",
    ]


def test_urgency_key_undated_and_bad_dates_sort_last():
    bad_date = ItemFigures(name="X", stock=0, net30=30, last_sale_date="not-a-date")
    undated = ItemFigures(name="Y", stock=0, net30=30, last_sale_date="")
    dated = ItemFigures(name="Z", stock=0, net30=30, last_sale_date="2026-01-05")
    assert [i.name for i in sorted([bad_date, undated, dated], key=urgency_key)] == [
        "Z", "X", "Y",
    ]


def _live_product(code, name, stock, net30, last_sale_date):
    return Product(
        item_code=code,
        name=name,
        stock=stock,
        unusable=0,
        incoming=0,
        net_30=net30,
        net_7=net30 // 4 if net30 else 0,
        net_90=net30 * 3 if net30 else 0,
        fraction_7=0.25 if net30 else 0.0,
        fraction_90=3.0 if net30 else 0.0,
        reorder_level=5,
        max_level=50,
        last_sale_date=last_sale_date,
        data_source="live",
    )


def test_suggestions_sorted_by_urgency(store):
    """All four need reorder; order is A, B, D (out, recent first), then C."""
    with store.session() as session:
        session.add_all(
            [
                _live_product("C", "C-instock", 10, 300, "2026-11-21"),
                _live_product("D", "D-out-undated", 0, 30, ""),
                _live_product("B", "B-out-older", 0, 300, "2026-11-10"),
                _live_product("A", "A-out-recent", 0, 300, "2026-11-20"),
            ]
        )
        session.commit()
    rows = purchase_service.suggestions(store, 30, 21, 5)
    assert [row["item"].name for row in rows] == [
        "A-out-recent", "B-out-older", "D-out-undated", "C-instock",
    ]
    # The most urgent row still carries the agreed formula numbers.
    assert rows[0]["breakdown"]["suggested_qty"] == 260
    assert rows[0]["item"].last_sale_date == "2026-11-20"


def test_attention_list_uses_urgency_order(store):
    with store.session() as session:
        session.add_all(
            [
                _live_product("B", "B-out-older", 0, 300, "2026-11-10"),
                _live_product("A", "A-out-recent", 0, 300, "2026-11-20"),
            ]
        )
        session.commit()
    assert [i.name for i in stock_service.needs_attention(store)] == [
        "A-out-recent", "B-out-older",
    ]


# ------------------------------------------------- exact filter, zero fields
class _ZeroFieldConnector:
    """A: purchased once, but every live field is 0. B: never stocked."""

    def fetch_products(self, conn=None):
        return [
            {"ItemCode": "A", "ItemName": "Panadol", "ItemStock": 0,
             "ReOrderLevel": 0, "MaxLevel": 0, "VendorCode": "",
             "Manufacturer": "", "ItemGroup": ""},
            {"ItemCode": "B", "ItemName": "CatalogueFiller", "ItemStock": 0,
             "ReOrderLevel": 0, "MaxLevel": 0, "VendorCode": "",
             "Manufacturer": "", "ItemGroup": ""},
        ]

    def fetch_stock(self, conn=None):
        return []

    def fetch_suppliers(self, conn=None):
        return []

    def fetch_sales_all(self, conn=None):
        return []

    def fetch_stock_entries(self, conn=None):
        return {"A": 1}


def test_import_keeps_zero_field_item_with_purchase_entry(store):
    """The v1.3.2 proxy would hide Panadol (all fields 0); the exact
    server filter must keep it — it was stocked once, so it can run
    out and needs buying."""
    result = import_service.refresh_from_pos(store, _ZeroFieldConnector())
    assert result["status"] == "ok"
    assert result["rows_imported"] == 1
    assert result["diagnostics"]["kept_after_filter"] == 1
    assert result["diagnostics"]["skipped_no_stock_entry"] == 1
    items = stock_service.visible_items(store)
    assert [item.name for item in items] == ["Panadol"]
    # It IS out of stock — the KPI the live screenshot showed as 0.
    assert stock_service.kpis(store, 30, 21, 5)["out_of_stock"] == 1
    assert stock_service.kpis(store, 30, 21, 5)["total_items"] == 1


# ------------------------------------------- last sale date end to end
class _DatedSalesConnector(_ZeroFieldConnector):
    """A was purchased once and last sold 2026-11-20."""

    def fetch_sales_all(self, conn=None):
        return [{
            "ItemCode": "A", "Net7": 70, "Net30": 300, "Net90": 900,
            "LastSale": "2026-11-20",
        }]


def test_import_stores_last_sale_date_and_api_serves_it(store, tmp_path):
    result = import_service.refresh_from_pos(store, _DatedSalesConnector())
    assert result["rows_imported"] == 1
    with store.session() as session:
        row = session.get(Product, "A")
        assert row.last_sale_date == "2026-11-20"
    client = create_app(
        store=store, connector=_DatedSalesConnector(),
        html_path=tmp_path / "missing.html",
    ).test_client()
    body = client.get("/api/data").get_json()
    assert body["item_count"] == 1
    assert body["items"][0]["lastSale"] == "2026-11-20"
    assert body["items"][0]["name"] == "Panadol"


def test_product_to_html_item_carries_last_sale():
    figures = ItemFigures(name="Panadol", stock=0, net30=300,
                          last_sale_date="2026-11-20")
    assert product_to_html_item(figures)["lastSale"] == "2026-11-20"
    assert product_to_html_item(ItemFigures(name="X"))["lastSale"] is None


# ------------------------------------------- probe: joined rows, last sale
def test_probe_counts_joined_rows_not_vouchers():
    """VoucherDate has recent vouchers but the join drops them (probe 0);
    Date has recent JOINED sales (probe 5) -> Date is picked, and the
    probe SQL proves the join."""
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"},
         {"COLUMN_NAME": "Date"}],
        [{"n": 0}],   # probe: VoucherDate, 0 joined rows in 90 days
        [{"n": 5}],   # probe: Date, 5 joined rows -> picked
        [{"n": 10}],  # diag: SaleDetail rows
        [{"n": 10}],  # diag: joined rows
        [{"n": 8}],   # diag: rows in the 90-day window
        [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20,
          "LastSale": "2026-11-20"}],
    ])
    rows = connector.fetch_sales_all()
    assert rows[0]["LastSale"] == "2026-11-20"
    assert connector.last_sales_diag["date_column"] == "Date"
    assert connector.last_sales_diag["items_with_last_sale"] == 1
    probe_sql = connector.seen[2]
    assert "INNER JOIN" in probe_sql and "SaleDetail" in probe_sql
    assert "MAX(" in connector.seen[-1] and "LastSale" in connector.seen[-1]


def test_probe_falls_back_when_join_yields_nothing():
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"}],
        [{"n": 0}],   # probe: VoucherDate, 0 joined rows
        [{"n": 10}],  # diag: SaleDetail rows exist...
        [{"n": 0}],   # diag: ...but NONE join to a voucher
        [{"n": 0}],   # diag: 0 in the 90-day window
        [{"ItemCode": "A", "Net7": 0, "Net30": 0, "Net90": 0,
          "LastSale": None}],
    ])
    rows = connector.fetch_sales_all()
    assert rows[0]["LastSale"] is None
    assert connector.last_sales_diag["date_column"] == "VoucherDate"
    assert connector.last_sales_diag["joined_rows"] == 0
    assert connector.last_sales_diag["items_with_sales"] == 0
    assert connector.last_sales_diag["items_with_last_sale"] == 0


# ------------------------------------------------------- store migration
def test_store_adds_missing_last_sale_date_column(tmp_path):
    """A database file made by v1.3.2 has no last_sale_date column;
    opening it with v1.3.3 must add the column instead of failing."""
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.execute(
        "CREATE TABLE settings (key VARCHAR(64) PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE products (item_code VARCHAR(64) PRIMARY KEY,"
        " name VARCHAR(256) NOT NULL)"
    )
    conn.commit()
    conn.close()
    store = Store(legacy)
    cols = [
        row[1]
        for row in sqlite3.connect(legacy).execute("PRAGMA table_info(products)")
    ]
    assert "last_sale_date" in cols
    with store.session() as session:
        session.add(
            Product(item_code="A", name="Panadol",
                    last_sale_date="2026-11-20", data_source="live")
        )
        session.commit()
    with store.session() as session:
        assert session.get(Product, "A").last_sale_date == "2026-11-20"


# ------------------------------------------------------------------- HTML
def test_html_urgency_sort_out_first_most_recent_first():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "function urgencySort(a, b)" in html
    assert "function lastSaleMs(it)" in html
    assert "function lastSaleText(it)" in html
    assert "aakhri sale:" in html
    # All four urgency lists use it; the old days-left-only sort is gone.
    assert html.count(".sort(urgencySort)") == 4
    assert "sort(function(a,b){ return daysLeft(a) - daysLeft(b); })" not in html
    # The last-sale date is shown next to "stock chalega".
    assert "lastSaleText(it)" in html
