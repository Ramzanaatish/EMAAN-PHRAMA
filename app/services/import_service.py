"""Refresh: import POS data (read-only) into the assistant's SQLite copy.

The dashboard never queries POS_DB directly. A refresh — manual or
scheduled — reads the verified POS fields through the connector and
replaces the live rows in SQLite. After the first successful live fetch
the demo data is switched off, so only live data is shown afterwards.
"""

from __future__ import annotations

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


def refresh_from_pos(store, connector) -> dict:
    """One full read-only import from POS_DB. Returns a summary dict."""
    started = datetime.now()
    log = RefreshLog(started_at=started, status="running")
    with store.session() as session:
        session.add(log)
        session.commit()
        log_id = log.id
    try:
        products = connector.fetch_products()
        stock_rows = {row["ItemCode"]: row for row in connector.fetch_stock()}
        suppliers = {row["AccountCode"]: row["AccountName"] for row in connector.fetch_suppliers()}
        sales_30 = {row["ItemCode"]: int(row["NetQty"]) for row in connector.fetch_sales(30)}
        sales_7 = {row["ItemCode"]: int(row["NetQty"]) for row in connector.fetch_sales(7)}
        sales_90 = {row["ItemCode"]: int(row["NetQty"]) for row in connector.fetch_sales(90)}

        with store.session() as session:
            session.query(Product).filter(Product.data_source == "live").delete(
                synchronize_session=False
            )
            for row in products:
                code = str(row.get("ItemCode") or "").strip()
                if not code:
                    continue
                name = str(row.get("ItemName") or "").strip()
                vendor = str(row.get("VendorCode") or "").strip()
                supplier_name = suppliers.get(vendor, "")
                stock_view = stock_rows.get(code)
                stock = int(row.get("ItemStock") or 0)
                if stock_view is not None:
                    stock = int(stock_view.get("InQty") or 0) - int(
                        stock_view.get("OutQty") or 0
                    )
                net_30 = sales_30.get(code, 0)
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
                        net_7=sales_7.get(code),
                        net_90=sales_90.get(code),
                        fraction_7=(sales_7.get(code, 0) / net_30) if net_30 else 0.0,
                        fraction_90=(sales_90.get(code, 0) / net_30) if net_30 else 0.0,
                        reorder_level=int(row.get("ReOrderLevel") or 0),
                        max_level=int(row.get("MaxLevel") or 0),
                        cost=0,
                        manufacturer=str(row.get("Manufacturer") or ""),
                        item_group=str(row.get("ItemGroup") or ""),
                        data_source="live",
                    )
                )
                if supplier_name and not session.query(Supplier).filter_by(
                    name=supplier_name
                ).first():
                    session.add(Supplier(name=supplier_name))
            session.commit()
            imported = session.query(Product).filter(
                Product.data_source == "live"
            ).count()

        finished = datetime.now().strftime("%d %b %Y, %I:%M %p")
        store.set_setting("last_fetch", finished)
        store.set_setting("data_source", "live")
        store.set_setting("demo_data", "off")
        with store.session() as session:
            entry = session.get(RefreshLog, log_id)
            entry.finished_at = datetime.now()
            entry.status = "ok"
            entry.rows_imported = imported
            session.commit()
        audit_service.log_audit(
            store, f"Live data refresh hua — POS_DB se {imported} items import hue."
        )
        return {"status": "ok", "rows_imported": imported, "finished_at": finished}
    except Exception as exc:  # noqa: BLE001 - recorded on the refresh log
        with store.session() as session:
            entry = session.get(RefreshLog, log_id)
            entry.finished_at = datetime.now()
            entry.status = "failed"
            entry.error = str(exc)
            session.commit()
        audit_service.log_audit(store, f"Live data refresh FAIL hua: {exc}")
        raise
