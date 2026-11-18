"""Tests for demo data: the exact HTML sample figures, on/off behaviour."""

from __future__ import annotations

from app.database.models import Product
from app.database.seed import DEMO_ITEMS, clear_demo_data, seed_demo_data
from app.services import import_service, stock_service

EXPECTED_NAMES = [
    "Panadol Extra 500mg", "Augmentin 625mg", "Brufen 400mg", "Flagyl 400mg",
    "Risek 20mg", "Arinac Forte", "Hydryllin Syrup 120ml", "Disprin",
    "CaC-1000 Plus", "Surbex-Z", "Nuberol Forte", "Velosef 500mg",
    "Calpol Syrup 90ml", "Strepsils", "Montika 10mg", "Gravinate 50mg",
    "Deltacortril 5mg", "Septran DS",
]


def test_demo_seed_has_the_18_html_items():
    assert len(DEMO_ITEMS) == 18
    assert [item.name for item in DEMO_ITEMS] == EXPECTED_NAMES
    assert {item.supplier for item in DEMO_ITEMS} == {
        "Premier Agencies", "Aslam Traders", "Madina Medicine Co.", "City Distributors",
    }


def test_demo_on_shows_sample_data(demo_store):
    items = stock_service.visible_items(demo_store)
    assert len(items) == 18
    assert stock_service.is_demo(demo_store) is True


def test_demo_off_hides_all_sample_data(demo_store):
    removed = import_service.disable_demo(demo_store)
    assert removed == 18
    assert stock_service.visible_items(demo_store) == []
    assert stock_service.is_demo(demo_store) is False
    assert stock_service.kpis(demo_store, 30, 21, 5) == {}
    with demo_store.session() as session:
        assert session.query(Product).count() == 0


def test_demo_off_keeps_live_rows(demo_store):
    with demo_store.session() as session:
        session.add(
            Product(
                item_code="LIVE-1", name="Live Item", supplier="Premier Agencies",
                stock=10, net_30=30, data_source="live",
            )
        )
        session.commit()
    import_service.disable_demo(demo_store)
    items = stock_service.visible_items(demo_store)
    assert [item.name for item in items] == ["Live Item"]


def test_demo_can_be_turned_back_on(demo_store):
    import_service.disable_demo(demo_store)
    assert stock_service.visible_items(demo_store) == []
    count = import_service.enable_demo(demo_store)
    assert count == 18
    assert len(stock_service.visible_items(demo_store)) == 18


def test_clear_demo_data_removes_only_demo_rows(demo_store):
    assert clear_demo_data(demo_store) == 18
    assert clear_demo_data(demo_store) == 0
