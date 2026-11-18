"""Stock views: KPIs, demand ranking, attention list, expiry, full stock.

Reads the assistant's own SQLite copy (demo or live). The dashboard never
queries POS_DB directly; only the scheduled/manual refresh does that.
"""

from __future__ import annotations

from ..core import purchase
from ..core.purchase import ItemFigures
from ..database.models import Product


def _all_products(store) -> list[Product]:
    with store.session() as session:
        return list(session.query(Product).order_by(Product.name).all())


def visible_items(store) -> list[ItemFigures]:
    """Items the UI may show: demo rows only while demo data is on."""
    if store.get_setting("demo_data", "on") != "on":
        return [row.to_figures() for row in _all_products(store) if row.data_source == "live"]
    return [row.to_figures() for row in _all_products(store)]


def is_demo(store) -> bool:
    return store.get_setting("demo_data", "on") == "on"


def _overrides(store) -> dict[str, int]:
    """Latest manual override quantity per item code."""
    from ..database.models import Override

    result: dict[str, int] = {}
    with store.session() as session:
        for row in session.query(Override).order_by(Override.id).all():
            result[row.item_code] = row.qty
    return result


def kpis(store, analysis_days: int, cover_days: int, safety_days: int) -> dict:
    """The six KPI cards, mirroring the HTML preview."""
    items = visible_items(store)
    if not items:
        return {}
    overrides = _overrides(store)
    out = sum(1 for item in items if purchase.status_of(item) == purchase.STATUS_OUT)
    critical = sum(
        1 for item in items if purchase.status_of(item) == purchase.STATUS_CRITICAL
    )
    low = sum(1 for item in items if purchase.status_of(item) == purchase.STATUS_LOW)
    sold = sum(purchase.net_sold(item, analysis_days) for item in items)
    estimated = sum(
        purchase.final_qty(
            item,
            analysis_days,
            cover_days,
            safety_days,
            override_qty=overrides.get(item.item_code),
        )
        * item.cost
        for item in items
        if purchase.needs_reorder(
            item, analysis_days, cover_days, safety_days,
            has_override=item.item_code in overrides,
        )
    )
    return {
        "total_items": len(items),
        "out_of_stock": out,
        "critical": critical,
        "low_stock": low,
        "net_units_sold": sold,
        "estimated_purchase_value": estimated,
    }


def demand_ranking(store, analysis_days: int, limit: int = 10) -> list[ItemFigures]:
    """Most-demanding medicines, ranked by net units sold."""
    items = visible_items(store)
    ranked = sorted(
        items, key=lambda item: purchase.net_sold(item, analysis_days), reverse=True
    )
    return ranked[:limit]


def needs_attention(store) -> list[ItemFigures]:
    """Out-of-stock and critical items, shortest cover first."""
    items = [
        item
        for item in visible_items(store)
        if purchase.status_of(item) in (purchase.STATUS_OUT, purchase.STATUS_CRITICAL)
    ]
    return sorted(items, key=purchase.days_left)


def near_expiry(store) -> list[ItemFigures]:
    """Items with an expiry batch, soonest expiry first."""
    items = [item for item in visible_items(store) if item.expiry_key]
    return sorted(items, key=lambda item: item.expiry_key)


def stock_rows(
    store, query: str = "", supplier: str = "", status: str = ""
) -> list[ItemFigures]:
    """Full stock position, filtered by search text, supplier and status."""
    items = visible_items(store)
    query = query.strip().lower()
    rows = [
        item
        for item in items
        if (not query or query in item.name.lower())
        and (not supplier or item.supplier == supplier)
        and (not status or purchase.status_of(item) == status)
    ]
    return sorted(rows, key=purchase.days_left)


def suppliers(store) -> list[str]:
    """Supplier names present in the visible data, sorted."""
    return sorted({item.supplier for item in visible_items(store) if item.supplier})
