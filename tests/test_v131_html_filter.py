"""Tests for v1.3.1: stock-entry filter + suggestions fix.

Nelson (21 Nov 2026, live HTML screenshots): the dashboard showed all
32,952 catalogue items, OUT OF STOCK 30,416, yet NET UNITS SOLD (30d) 0
and 0 reorder suggestions.

1. FILTER — only medicines with >= 1 prior stock entry are shown.
   "Stock entry" = a PurchaseDetail line (purchase / goods received)
   or an OpeningStock row. The HTML proxy (hasStockEntry) uses the
   fields /api/data already sends; the server applies the exact filter
   at import time and the HTML then stands its proxy down.
2. SUGGESTIONS — the sales query probed a date column by name only.
   When that column holds no usable dates every window came back 0
   (ADS 0 -> target 0 -> suggested 0). The connector now probes each
   date candidate for actual rows in the last 90 days and records
   diagnostics (counts only) for the server log.
"""

from __future__ import annotations

from pathlib import Path

from app.connectors.sql_server import SqlServerConnector
from app.core.errors import ConnectorError
from app.database.models import Product
from app.services import import_service, purchase_service, stock_service
from tests.test_connector import StubConnector

HTML_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


# ------------------------------------------------------- sales date probe
def test_sales_date_probe_picks_column_with_recent_rows():
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"},
         {"COLUMN_NAME": "Date"}],
        [{"n": 0}],   # probe: VoucherDate has NO recent rows
        [{"n": 5}],   # probe: Date HAS recent rows -> picked
        [{"n": 10}],  # diag: SaleDetail rows
        [{"n": 10}],  # diag: joined rows
        [{"n": 8}],   # diag: rows in the 90-day window
        [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20}],
    ])
    rows = connector.fetch_sales_all()
    assert rows == [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20}]
    assert connector.last_sales_diag["date_column"] == "Date"
    # v1.3.4: no TRY_CONVERT anywhere — it needs compat level 110+
    # and POS_DB runs below it (live error 195). Dates parse with
    # plain CONVERT + CASE + LIKE instead.
    assert "TRY_CONVERT" not in connector.seen[-1]
    assert "CONVERT(date, v.[Date], 103)" in connector.seen[-1]
    assert "CONVERT(date, v.[VoucherDate], 103)" not in connector.seen[-1]
    assert connector.last_sales_diag["detail_rows"] == 10
    assert connector.last_sales_diag["joined_rows"] == 10
    assert connector.last_sales_diag["in_window_90d"] == 8
    assert connector.last_sales_diag["items_with_sales"] == 1


def test_sales_sql_uses_no_try_functions():
    """v1.3.4 regression: TRY_CONVERT/TRY_CAST/TRY_PARSE all need
    compatibility level 110+; POS_DB is below it, so none of them may
    appear in any query the sales refresh generates."""
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"},
         {"COLUMN_NAME": "Date"}],
        [{"n": 0}],   # probe: VoucherDate has NO recent rows
        [{"n": 5}],   # probe: Date HAS recent rows -> picked
        [{"n": 10}],  # diag: SaleDetail rows
        [{"n": 10}],  # diag: joined rows
        [{"n": 8}],   # diag: rows in the 90-day window
        [{"ItemCode": "A", "Net7": 1, "Net30": 9, "Net90": 20}],
    ])
    connector.fetch_sales_all()
    for query in connector.seen:
        assert "TRY_CONVERT" not in query
        assert "TRY_CAST" not in query
        assert "TRY_PARSE" not in query


def test_sales_date_probe_falls_back_to_voucher_date():
    connector = StubConnector([
        [{"COLUMN_NAME": "ItemCode"}, {"COLUMN_NAME": "Quantity"},
         {"COLUMN_NAME": "VoucherNo"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"}],
        [{"n": 0}],   # probe: no recent rows anywhere
        [{"n": 0}],
        [{"n": 0}],
        [{"n": 0}],
        [{"ItemCode": "A", "Net7": 0, "Net30": 0, "Net90": 0}],
    ])
    rows = connector.fetch_sales_all()
    assert rows == [{"ItemCode": "A", "Net7": 0, "Net30": 0, "Net90": 0}]
    # Genuinely no recent sales: VoucherDate stays, windows stay 0 —
    # nothing is faked, the dashboard says so plainly instead.
    assert connector.last_sales_diag["date_column"] == "VoucherDate"
    assert connector.last_sales_diag["items_with_sales"] == 0


# --------------------------------------------------------- stock entries
class _TableFake(SqlServerConnector):
    """Connector whose _query answers from a {table: columns} map."""

    def __init__(self, tables):
        super().__init__()
        self.tables = tables

    def _query(self, sql, params=(), conn=None):
        if "INFORMATION_SCHEMA" in sql:
            columns = self.tables.get(params[0])
            if columns is None:
                raise ConnectorError(f"table {params[0]} missing")
            return [{"COLUMN_NAME": c} for c in columns]
        if "PurchaseDetail" in sql:
            return [
                {"ItemCode": "A", "EntryCount": 3},
                {"ItemCode": "B", "EntryCount": 1},
            ]
        if "OpeningStock" in sql:
            return [{"ItemCode": "A", "EntryCount": 2}]
        return [{"n": 0}]


def test_fetch_stock_entries_counts_purchases_plus_opening():
    connector = _TableFake(
        {"PurchaseDetail": ["ItemCode"], "OpeningStock": ["ItemCode"]}
    )
    assert connector.fetch_stock_entries() == {"A": 5, "B": 1}
    diag = connector.last_stock_entry_diag
    assert diag["purchase_items"] == 2
    assert diag["opening_items"] == 1
    assert diag["purchase_rows"] == 4
    assert diag["opening_rows"] == 2
    assert diag["items_with_entry"] == 2


def test_fetch_stock_entries_missing_table_contributes_zero():
    connector = _TableFake({"PurchaseDetail": ["ItemCode"], "OpeningStock": None})
    assert connector.fetch_stock_entries() == {"A": 3, "B": 1}
    assert connector.last_stock_entry_diag["opening_items"] == 0
    assert connector.last_stock_entry_diag["items_with_entry"] == 2


# ------------------------------------------------------------ import filter
class _EntryConnector:
    """Fake connector: A was stocked (2 entries) + sold; B never stocked."""

    def __init__(self, entries):
        self.entries = entries

    def fetch_products(self, conn=None):
        return [
            {"ItemCode": "A", "ItemName": "Panadol", "ItemStock": 0,
             "ReOrderLevel": 5, "MaxLevel": 50, "VendorCode": "",
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
        return [{"ItemCode": "A", "Net7": 70, "Net30": 300, "Net90": 900}]

    def fetch_stock_entries(self, conn=None):
        return self.entries


def test_import_keeps_only_items_with_a_stock_entry(store):
    result = import_service.refresh_from_pos(store, _EntryConnector({"A": 2}))
    assert result["status"] == "ok"
    assert result["rows_imported"] == 1
    assert result["stock_entry_filtered"] is True
    diag = result["diagnostics"]
    assert diag["items_fetched"] == 2
    assert diag["kept_after_filter"] == 1
    assert diag["skipped_no_stock_entry"] == 1
    assert diag["stock_entry_filter"] == "on"
    # The never-stocked item is gone from listings, KPIs and suggestions.
    items = stock_service.visible_items(store)
    assert [item.name for item in items] == ["Panadol"]
    assert stock_service.kpis(store, 30, 21, 5)["total_items"] == 1
    rows = purchase_service.suggestions(store, 30, 21, 5)
    assert [row["item"].name for row in rows] == ["Panadol"]
    # Formula numbers: ADS 300/30 = 10, target (10x21) + (10x5) = 260,
    # usable 0, incoming 0 -> suggested 260.
    breakdown = rows[0]["breakdown"]
    assert breakdown["ads"] == 10.0
    assert breakdown["target_stock"] == 260
    assert breakdown["suggested_qty"] == 260
    assert rows[0]["final_qty"] == 260
    assert store.get_setting("stock_entry_filter") == "on"


def test_import_fails_open_when_stock_entries_unavailable(store):
    class _FailingEntries(_EntryConnector):
        def fetch_stock_entries(self, conn=None):
            raise RuntimeError("PurchaseDetail not readable")

    result = import_service.refresh_from_pos(store, _FailingEntries({"A": 2}))
    assert result["status"] == "ok"
    # Filter off: both items imported, nothing silently wiped.
    assert result["rows_imported"] == 2
    assert result["stock_entry_filtered"] is False
    assert result["diagnostics"]["stock_entry_filter"] == "off"
    assert "PurchaseDetail" in (result["diagnostics"]["stock_entry_error"] or "")
    assert len(stock_service.visible_items(store)) == 2


def test_suggestion_formula_numbers_for_low_stock_with_sales(store):
    """A sold-out item with real sales gets a real suggestion."""
    with store.session() as session:
        session.add(
            Product(
                item_code="A",
                name="Panadol",
                stock=0,
                unusable=0,
                incoming=0,
                net_30=300,
                net_7=70,
                net_90=900,
                fraction_7=70 / 300,
                fraction_90=900 / 300,
                reorder_level=5,
                max_level=50,
                data_source="live",
            )
        )
        session.commit()
    rows = purchase_service.suggestions(store, 30, 21, 5)
    assert len(rows) == 1
    breakdown = rows[0]["breakdown"]
    assert breakdown["net_sold"] == 300
    assert breakdown["ads"] == 10.0
    assert breakdown["safety_stock"] == 50
    assert breakdown["target_stock"] == 260
    assert breakdown["usable_stock"] == 0
    assert breakdown["suggested_qty"] == 260


# ------------------------------------------------------------------- HTML
def test_html_stock_entry_proxy_filter():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "function hasStockEntry(it)" in html
    # The exact proxy signal, from the fields /api/data already sends.
    for field in ("it.stock", "it.net30", "it.reorder", "it.max",
                  "it.incoming", "it.unusable"):
        assert field in html
    assert "function data()" in html
    assert "live.filter(hasStockEntry)" in html
    # Demo data is not filtered; the server-filtered flag stands the
    # proxy down once the rebuilt server filters at import time.
    assert "if (state.demo) return ITEMS;" in html
    assert "state.serverFiltered" in html
    assert "stock_entry_filtered" in html


def test_html_says_why_no_suggestions_when_sales_are_zero():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "Koi suggestion nahi — POS_DB se koi sales data nahi aaya" in html
    assert "ADS 0 hai aur target 0 banta hai" in html
    assert "server window mein refresh ki diagnosis dekhein" in html
    # The old misleading message is kept only for the real
    # "stock is enough" case.
    assert "sab ka usable stock target se zyada hai" in html


def test_html_filter_empty_state_is_honest():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "function allFilteredOut()" in html
    assert "function filterEmptyHTML()" in html
    assert "koi medicine stock-entry filter par poori nahi utri" in html
    assert "sirf stock-entry wali" in html


def test_html_stock_list_capped_at_50_with_show_more():
    # v1.3.2 — memory: All Stock renders at most 50 rows at once; the
    # Show more button adds 50 more. No unbounded render.
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "stockShown: 50" in html
    assert "rows.slice(0, state.stockShown)" in html
    assert "state.stockShown += 50" in html
    assert 'id="stockShowMore"' in html
    assert "Show more" in html
    assert 'id="stockCount"' in html
    assert "dikhaye ja rahe hain" in html
