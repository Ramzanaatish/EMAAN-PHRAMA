"""Refresh: import POS data (read-only) into the assistant's SQLite copy.

The dashboard never queries POS_DB directly. A refresh — manual or
scheduled — reads the verified POS fields through the connector and
replaces the live rows in SQLite. After the first successful live fetch
the demo data is switched off, so only live data is shown afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime

from ..database.models import Product, RefreshLog, Supplier
from ..database.seed import clear_demo_data, seed_demo_data
from . import audit_service


def enable_demo(store) -> int:
    """Turn demo data on (seeds the sample items, PREVIEW labelled)."""
    count = seed_demo_data(store)
    store.set_setting("demo_data", "on")
    store.set_setting("data_source", "demo")
    audit_service.log_audit(
        store, "Demo data ON kiya gaya — sample data PREVIEW label ke saath wapas dikh raha hai."
    )
    return count


def disable_demo(store) -> int:
    """Remove demo data. Live rows, settings and audit trail are untouched.

    Overrides on demo items are cleared with them (clear_demo_data);
    overrides on live items survive.
    """
    removed = clear_demo_data(store)
    store.set_setting("demo_data", "off")
    audit_service.log_audit(
        store,
        "Demo data OFF / REMOVE kiya gaya — sample rows, figures, draft aur "
        "overrides saaf. Ab sirf live data (POS_DB) dikhega.",
    )
    return removed


def _fetch_sales(connector, conn):
    """Sales per item for the 7/30/90-day windows, as {code: row}.

    Prefers the connector's single-query fetch_sales_all; falls back
    to three fetch_sales calls for older connectors / test fakes that
    do not have it yet.
    """
    fetch_all = getattr(connector, "fetch_sales_all", None)
    if fetch_all is not None:
        rows = fetch_all(conn=conn) if conn is not None else fetch_all()
        return {row["ItemCode"]: row for row in rows}
    merged: dict[str, dict] = {}
    for days, key in ((7, "Net7"), (30, "Net30"), (90, "Net90")):
        if conn is not None:
            rows = connector.fetch_sales(days, conn=conn)
        else:
            rows = connector.fetch_sales(days)
        for row in rows:
            merged.setdefault(row["ItemCode"], {})[key] = int(row["NetQty"])
    return merged


def _fetch_stock_entries(connector, conn):
    """(entries dict or None, error text or None).

    None means the connector cannot supply stock entries (older fakes
    without fetch_stock_entries) or the fetch failed — the refresh
    then imports WITHOUT the filter (fail-open) and says so in the
    diagnostics, so a schema surprise can never wipe the dashboard.
    """
    fetch = getattr(connector, "fetch_stock_entries", None)
    if fetch is None:
        return None, None
    try:
        entries = fetch(conn=conn) if conn is not None else fetch()
        return entries, None
    except Exception as exc:  # noqa: BLE001 - fail-open, reported in diag
        return None, str(exc)


def _fetch_all(connector):
    """Fetch every POS dataset, reusing one connection when the
    connector supports sessions (SqlServerConnector.session).

    Returns (products, stock_rows, suppliers, sales, entries,
    entries_error). Connectors without a session (older fakes) keep
    the old per-query behaviour.
    """
    session_cm = getattr(connector, "session", None)
    if session_cm is not None:
        with session_cm() as conn:
            return _fetch_all_on_connection(connector, conn)
    return _fetch_all_on_connection(connector, None)


def _fetch_all_on_connection(connector, conn):
    kwargs = {"conn": conn} if conn is not None else {}
    products = connector.fetch_products(**kwargs)
    stock_rows = {
        row["ItemCode"]: row for row in connector.fetch_stock(**kwargs)
    }
    suppliers = {
        row["AccountCode"]: row["AccountName"]
        for row in connector.fetch_suppliers(**kwargs)
    }
    sales = _fetch_sales(connector, conn)
    entries, entries_error = _fetch_stock_entries(connector, conn)
    return products, stock_rows, suppliers, sales, entries, entries_error


def refresh_from_pos(store, connector) -> dict:
    """One full read-only import from POS_DB. Returns a summary dict.

    v1.2.0: ONE ODBC connection for the whole refresh (the old code
    opened 11: every list_columns + every fetch), ONE sales query for
    the 7/30/90-day windows, and ONE supplier lookup instead of one
    per product row.

    v1.3.1: the stock-entry filter — a live item is imported only when
    it has at least one stock entry (PurchaseDetail / OpeningStock,
    see connectors.sql_server.fetch_stock_entries). Items that were
    never stocked stay out of KPIs, All Stock, suggestions and the
    report, in the desktop app and the HTML alike, because the filter
    runs here at import time. The filter fails OPEN: when the
    connector cannot supply entries the refresh imports everything
    and says so in the diagnostics. Diagnostics (counts only, never
    item data) are printed to the server log and stored in settings
    so the dashboard API can show them too.
    """
    started = datetime.now()
    log = RefreshLog(started_at=started, status="running")
    with store.session() as session:
        session.add(log)
        session.commit()
        log_id = log.id
    try:
        products, stock_rows, suppliers, sales, entries, entries_error = _fetch_all(
            connector
        )
        sales_diag = getattr(connector, "last_sales_diag", None) or {}
        entries_diag = getattr(connector, "last_stock_entry_diag", None) or {}
        filter_on = entries is not None
        kept = 0
        skipped = 0

        with store.session() as session:
            session.query(Product).filter(Product.data_source == "live").delete(
                synchronize_session=False
            )
            existing_suppliers = {
                row[0] for row in session.query(Supplier.name).all()
            }
            new_suppliers: set[str] = set()
            for row in products:
                code = str(row.get("ItemCode") or "").strip()
                if not code:
                    continue
                if filter_on and entries.get(code, 0) < 1:
                    skipped += 1
                    continue
                kept += 1
                name = str(row.get("ItemName") or "").strip()
                vendor = str(row.get("VendorCode") or "").strip()
                supplier_name = suppliers.get(vendor, "")
                stock_view = stock_rows.get(code)
                stock = int(row.get("ItemStock") or 0)
                if stock_view is not None:
                    stock = int(stock_view.get("InQty") or 0) - int(
                        stock_view.get("OutQty") or 0
                    )
                sales_row = sales.get(code, {})
                net_30 = int(sales_row.get("Net30") or 0)
                net_7 = int(sales_row.get("Net7") or 0)
                net_90 = int(sales_row.get("Net90") or 0)
                # v1.3.3: last sale date, ISO "YYYY-MM-DD" (pyodbc may hand
                # back a date/datetime — str() + first 10 chars normalises
                # both; "" when the item never sold).
                raw_last_sale = sales_row.get("LastSale")
                last_sale = str(raw_last_sale)[:10] if raw_last_sale else ""
                session.add(
                    Product(
                        item_code=code,
                        name=name,
                        supplier=supplier_name,
                        supplier_mapped=bool(supplier_name),
                        stock=stock,
                        unusable=0,
                        incoming=0,
                        net_30=net_30,
                        net_7=net_7,
                        net_90=net_90,
                        fraction_7=(net_7 / net_30) if net_30 else 0.0,
                        fraction_90=(net_90 / net_30) if net_30 else 0.0,
                        reorder_level=int(row.get("ReOrderLevel") or 0),
                        max_level=int(row.get("MaxLevel") or 0),
                        cost=0,
                        pack_size=1,
                        last_sale_date=last_sale,
                        manufacturer=str(row.get("Manufacturer") or ""),
                        item_group=str(row.get("ItemGroup") or ""),
                        data_source="live",
                    )
                )
                if supplier_name and supplier_name not in existing_suppliers:
                    new_suppliers.add(supplier_name)
            if new_suppliers:
                session.add_all(
                    Supplier(name=name) for name in sorted(new_suppliers)
                )
            session.commit()
            imported = session.query(Product).filter(
                Product.data_source == "live"
            ).count()

        finished = datetime.now().strftime("%d %b %Y, %I:%M %p")
        store.set_setting("last_fetch", finished)
        store.set_setting("data_source", "live")
        store.set_setting("demo_data", "off")
        diagnostics = {
            "items_fetched": len(products),
            "sales_date_column": sales_diag.get("date_column"),
            "sales_detail_rows": sales_diag.get("detail_rows"),
            "sales_joined_rows": sales_diag.get("joined_rows"),
            "sales_in_window_90d": sales_diag.get("in_window_90d"),
            "items_with_sales": sales_diag.get("items_with_sales"),
            "items_with_last_sale": sales_diag.get("items_with_last_sale"),
            "purchase_items": entries_diag.get("purchase_items"),
            "opening_items": entries_diag.get("opening_items"),
            "items_with_entry": entries_diag.get("items_with_entry"),
            "kept_after_filter": kept,
            "skipped_no_stock_entry": skipped,
            "stock_entry_filter": "on" if filter_on else "off",
            "stock_entry_error": entries_error,
        }
        # Counts only, never item data — this is what the server window
        # on the PC shows after a Refresh, so the diagnosis is readable
        # there without reaching the live SQL Server.
        print(
            "[refresh] POS_DB: {items} items fetched; sales date column "
            "{date_col}; SaleDetail rows {detail}, joined with voucher "
            "{joined}, in 90-day window {window}, items with sales "
            "{with_sales}, items with last sale {with_last}; stock entries: purchase items {purchase}, "
            "opening items {opening}; kept {kept}, skipped {skipped} "
            "(filter {filter_state})".format(
                items=len(products),
                date_col=sales_diag.get("date_column"),
                detail=sales_diag.get("detail_rows"),
                joined=sales_diag.get("joined_rows"),
                window=sales_diag.get("in_window_90d"),
                with_sales=sales_diag.get("items_with_sales"),
                with_last=sales_diag.get("items_with_last_sale"),
                purchase=entries_diag.get("purchase_items"),
                opening=entries_diag.get("opening_items"),
                kept=kept,
                skipped=skipped,
                filter_state="on" if filter_on else "off",
            )
        )
        if entries_error:
            print(f"[refresh] stock-entry check fail hua: {entries_error} — filter nahi lagaya.")
        store.set_setting("stock_entry_filter", "on" if filter_on else "off")
        store.set_setting("last_refresh_diag", json.dumps(diagnostics))
        with store.session() as session:
            entry = session.get(RefreshLog, log_id)
            entry.finished_at = datetime.now()
            entry.status = "ok"
            entry.rows_imported = imported
            session.commit()
        audit_text = (
            f"Live data refresh hua — POS_DB se {imported} items import hue."
        )
        if filter_on and skipped:
            audit_text += f" (stock-entry filter: {skipped} chhupaye)"
        audit_service.log_audit(store, audit_text)
        return {
            "status": "ok",
            "rows_imported": imported,
            "finished_at": finished,
            "diagnostics": diagnostics,
            "stock_entry_filtered": filter_on,
        }
    except Exception as exc:  # noqa: BLE001 - recorded on the refresh log
        with store.session() as session:
            entry = session.get(RefreshLog, log_id)
            entry.finished_at = datetime.now()
            entry.status = "failed"
            entry.error = str(exc)
            session.commit()
        audit_service.log_audit(store, f"Live data refresh FAIL hua: {exc}")
        raise
