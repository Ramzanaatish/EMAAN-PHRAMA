"""Stock views: KPIs, demand ranking, attention list, expiry, full stock.

Reads the assistant's own SQLite copy (demo or live). The dashboard never
queries POS_DB directly; only the scheduled/manual refresh does that.

v1.2.0: every view function accepts a pre-loaded `items` list. The main
window loads the products ONCE per refresh and passes the list down —
the old code re-ran a full SELECT * + object build ~10 times per
refresh (once per render function), which is what made every click
feel heavy on a real catalogue.
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


def override_details(store) -> dict[str, dict]:
    """Latest override quantity + reason per item code, in ONE query.

    The old suggestions() code asked the database for the reason of
    every single suggestion row (one query per row). This loads all
    Override rows once; the latest row per code wins for both fields.
    """
    from ..database.models import Override

    result: dict[str, dict] = {}
    with store.session() as session:
        for row in session.query(Override).order_by(Override.id).all():
            result[row.item_code] = {"qty": row.qty, "reason": row.reason}
    return result


def _items(store, items=None) -> list[ItemFigures]:
    return items if items is not None else visible_items(store)


def kpis(store, analysis_days: int, cover_days: int, safety_days: int, items=None, overrides=None) -> dict:
    """The six KPI cards, mirroring the HTML preview."""
    items = _items(store, items)
    if not items:
        return {}
    overrides = overrides if overrides is not None else _overrides(store)
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


def demand_ranking(store, analysis_days: int, limit: int = 10, items=None) -> list[ItemFigures]:
    """Most-demanding medicines, ranked by net units sold."""
    items = _items(store, items)
    ranked = sorted(
        items, key=lambda item: purchase.net_sold(item, analysis_days), reverse=True
    )
    return ranked[:limit]


def needs_attention(store, items=None) -> list[ItemFigures]:
    """Out-of-stock and critical items, most urgent first.

    v1.3.3: same urgency order as suggestions (out first, most
    recently sold first) instead of plain days-left.
    """
    items = [
        item
        for item in _items(store, items)
        if purchase.status_of(item) in (purchase.STATUS_OUT, purchase.STATUS_CRITICAL)
    ]
    return sorted(items, key=purchase.urgency_key)


def near_expiry(store, items=None) -> list[ItemFigures]:
    """Items with an expiry batch, soonest expiry first."""
    items = [item for item in _items(store, items) if item.expiry_key]
    return sorted(items, key=lambda item: item.expiry_key)


def stock_rows(
    store, query: str = "", supplier: str = "", status: str = "", items=None
) -> list[ItemFigures]:
    """Full stock position, filtered by search text, supplier and status."""
    items = _items(store, items)
    query = query.strip().lower()
    rows = [
        item
        for item in items
        if (not query or query in item.name.lower())
        and (not supplier or item.supplier == supplier)
        and (not status or purchase.status_of(item) == status)
    ]
    return sorted(rows, key=purchase.days_left)


def suppliers(store, items=None) -> list[str]:
    """Supplier names present in the visible data, sorted."""
    return sorted({item.supplier for item in _items(store, items) if item.supplier})
