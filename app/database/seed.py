"""Demo (sample) data — the exact figures from the HTML preview.

These 18 items are labelled PREVIEW in the app. They exist only so the
screens can be reviewed before the live POS connection is made. When the
demo-data switch is turned off they disappear, and after a live fetch only
live POS_DB rows are shown.
"""

from __future__ import annotations

from ..core.purchase import ItemFigures

DEMO_ITEMS: list[ItemFigures] = [
    ItemFigures(
        name="Panadol Extra 500mg", pack="Strip of 10 tabs", supplier="Premier Agencies",
        stock=142, unusable=0, incoming=500, net30=1860, fraction_7=0.24, fraction_90=2.9,
        reorder_level=300, max_level=2400, cost=42, pack_size=10,
    ),
    ItemFigures(
        name="Augmentin 625mg", pack="Strip of 6 tabs", supplier="Premier Agencies",
        stock=38, unusable=6, incoming=0, net30=720, fraction_7=0.22, fraction_90=3.0,
        reorder_level=120, max_level=900, cost=310, pack_size=6,
    ),
    ItemFigures(
        name="Brufen 400mg", pack="Strip of 10 tabs", supplier="Aslam Traders",
        stock=0, unusable=0, incoming=200, net30=540, fraction_7=0.25, fraction_90=2.8,
        reorder_level=100, max_level=800, cost=55, pack_size=10,
    ),
    ItemFigures(
        name="Flagyl 400mg", pack="Strip of 10 tabs", supplier="Madina Medicine Co.",
        stock=22, unusable=0, incoming=0, net30=660, fraction_7=0.23, fraction_90=2.95,
        reorder_level=150, max_level=1000, cost=38, pack_size=10,
    ),
    ItemFigures(
        name="Risek 20mg", pack="Strip of 14 caps", supplier="Premier Agencies",
        stock=96, unusable=0, incoming=0, net30=840, fraction_7=0.24, fraction_90=2.9,
        reorder_level=140, max_level=1100, cost=185, pack_size=14,
    ),
    ItemFigures(
        name="Arinac Forte", pack="Strip of 10 tabs", supplier="Aslam Traders",
        stock=310, unusable=60, incoming=0, net30=690, fraction_7=0.21, fraction_90=3.1,
        reorder_level=120, max_level=900, cost=60, pack_size=10,
        expiry_batch="B-2214", expiry_date="Feb 2027", expiry_qty=60, expiry_key=202702,
    ),
    ItemFigures(
        name="Hydryllin Syrup 120ml", pack="Bottle", supplier="Madina Medicine Co.",
        stock=12, unusable=0, incoming=100, net30=480, fraction_7=0.26, fraction_90=2.85,
        reorder_level=80, max_level=600, cost=95, pack_size=1,
    ),
    ItemFigures(
        name="Disprin", pack="Strip of 10 tabs", supplier="City Distributors",
        stock=520, unusable=45, incoming=0, net30=1230, fraction_7=0.23, fraction_90=2.9,
        reorder_level=200, max_level=1800, cost=28, pack_size=10,
        expiry_batch="B-1987", expiry_date="Dec 2026", expiry_qty=45, expiry_key=202612,
    ),
    ItemFigures(
        name="CaC-1000 Plus", pack="Tube of 10 tabs", supplier="Premier Agencies",
        stock=64, unusable=0, incoming=0, net30=570, fraction_7=0.24, fraction_90=3.0,
        reorder_level=100, max_level=800, cost=260, pack_size=10,
    ),
    ItemFigures(
        name="Surbex-Z", pack="Bottle of 30 tabs", supplier="Aslam Traders",
        stock=45, unusable=0, incoming=0, net30=390, fraction_7=0.22, fraction_90=2.9,
        reorder_level=60, max_level=500, cost=720, pack_size=1,
    ),
    ItemFigures(
        name="Nuberol Forte", pack="Strip of 10 tabs", supplier="Madina Medicine Co.",
        stock=8, unusable=0, incoming=0, net30=450, fraction_7=0.25, fraction_90=2.8,
        reorder_level=90, max_level=700, cost=88, pack_size=10,
    ),
    ItemFigures(
        name="Velosef 500mg", pack="Strip of 6 caps", supplier="City Distributors",
        stock=130, unusable=30, incoming=0, net30=300, fraction_7=0.20, fraction_90=3.1,
        reorder_level=60, max_level=600, cost=240, pack_size=6,
        expiry_batch="B-3102", expiry_date="Jan 2027", expiry_qty=30, expiry_key=202701,
    ),
    ItemFigures(
        name="Calpol Syrup 90ml", pack="Bottle", supplier="Premier Agencies",
        stock=26, unusable=0, incoming=150, net30=510, fraction_7=0.26, fraction_90=2.85,
        reorder_level=90, max_level=700, cost=110, pack_size=1,
    ),
    ItemFigures(
        name="Strepsils", pack="Pack of 24 lozenges", supplier="City Distributors",
        stock=400, unusable=0, incoming=0, net30=780, fraction_7=0.23, fraction_90=2.95,
        reorder_level=150, max_level=1200, cost=150, pack_size=1,
    ),
    ItemFigures(
        name="Montika 10mg", pack="Strip of 14 tabs", supplier="Aslam Traders",
        stock=58, unusable=0, incoming=0, net30=420, fraction_7=0.21, fraction_90=3.0,
        reorder_level=70, max_level=650, cost=240, pack_size=14,
    ),
    ItemFigures(
        name="Gravinate 50mg", pack="Strip of 10 tabs", supplier="Madina Medicine Co.",
        stock=0, unusable=0, incoming=120, net30=270, fraction_7=0.24, fraction_90=2.9,
        reorder_level=60, max_level=500, cost=45, pack_size=10,
    ),
    ItemFigures(
        name="Deltacortril 5mg", pack="Strip of 10 tabs", supplier="City Distributors",
        stock=175, unusable=0, incoming=0, net30=210, fraction_7=0.19, fraction_90=3.2,
        reorder_level=50, max_level=500, cost=130, pack_size=10,
    ),
    ItemFigures(
        name="Septran DS", pack="Strip of 10 tabs", supplier="Premier Agencies",
        stock=33, unusable=0, incoming=0, net30=390, fraction_7=0.23, fraction_90=2.9,
        reorder_level=80, max_level=700, cost=68, pack_size=10,
    ),
]


def item_code_for(name: str) -> str:
    """Stable demo code derived from the name (demo rows have no POS code)."""
    return "DEMO-" + "".join(ch for ch in name.upper() if ch.isalnum())[:16]


# Demo figures carry the same codes as their database rows, so overrides
# and draft lines saved against a figure match the stored product.
for _item in DEMO_ITEMS:
    _item.item_code = item_code_for(_item.name)


def seed_demo_data(store) -> int:
    """Insert the demo items into the store (replacing any demo rows)."""
    from .models import Product, Supplier

    with store.session() as session:
        session.query(Product).filter(Product.data_source == "demo").delete()
        for item in DEMO_ITEMS:
            if not session.query(Supplier).filter_by(name=item.supplier).first():
                session.add(Supplier(name=item.supplier))
            session.add(
                Product(
                    item_code=item_code_for(item.name),
                    name=item.name,
                    pack=item.pack,
                    supplier=item.supplier,
                    stock=item.stock,
                    unusable=item.unusable,
                    incoming=item.incoming,
                    net_30=item.net30,
                    net_7=None,
                    net_90=None,
                    fraction_7=item.fraction_7,
                    fraction_90=item.fraction_90,
                    reorder_level=item.reorder_level,
                    max_level=item.max_level,
                    cost=item.cost,
                    pack_size=item.pack_size,
                    expiry_batch=item.expiry_batch,
                    expiry_date=item.expiry_date,
                    expiry_qty=item.expiry_qty,
                    expiry_key=item.expiry_key,
                    data_source="demo",
                )
            )
        session.commit()
    return len(DEMO_ITEMS)


def clear_demo_data(store) -> int:
    """Remove all demo rows; live rows are never touched."""
    from .models import Override, Product, PurchaseOrder, PurchaseOrderItem

    with store.session() as session:
        demo_codes = [
            row.item_code
            for row in session.query(Product.item_code).filter(
                Product.data_source == "demo"
            )
        ]
        removed = len(demo_codes)
        if demo_codes:
            session.query(Override).filter(Override.item_code.in_(demo_codes)).delete(
                synchronize_session=False
            )
            session.query(PurchaseOrderItem).filter(
                PurchaseOrderItem.item_code.in_(demo_codes)
            ).delete(synchronize_session=False)
            session.query(Product).filter(Product.data_source == "demo").delete(
                synchronize_session=False
            )
        session.query(PurchaseOrder).filter(
            ~PurchaseOrder.items.any()
        ).delete(synchronize_session=False)
        session.commit()
    return removed
