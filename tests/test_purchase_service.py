"""Tests for reorder suggestions and manual overrides."""

from __future__ import annotations

import pytest

from app.core.errors import OverrideReasonRequired, ValidationError
from app.database.seed import DEMO_ITEMS
from app.services import purchase_service


def test_all_18_items_need_reorder_at_cover_21(demo_store):
    rows = purchase_service.suggestions(demo_store, 30, 21, 5)
    assert len(rows) == 18


def test_cover_14_summary_matches_current_html(demo_store):
    # Current HTML, analysis 30 din, cover 14 din: 17 items need reorder
    # (Deltacortril's usable stock covers its target). The older screenshot
    # showed 4062 units / Rs 649,055 because that build still counted
    # expiry-batch stock as usable; the current HTML excludes all unusable
    # stock, giving 4197 units / Rs 661,115.
    rows = purchase_service.suggestions(demo_store, 30, 14, 5)
    assert len(rows) == 17
    total_qty = sum(row["final_qty"] for row in rows)
    total_cost = sum(row["final_qty"] * row["item"].cost for row in rows)
    assert total_qty == 4197
    assert total_cost == 661115


def test_seven_day_analysis_summary(demo_store):
    # Analysis 7 din, cover 21 din: 17 items, Deltacortril drops out.
    rows = purchase_service.suggestions(demo_store, 7, 21, 5)
    assert len(rows) == 17
    total_qty = sum(row["final_qty"] for row in rows)
    total_cost = sum(row["final_qty"] * row["item"].cost for row in rows)
    assert total_qty == 6823
    assert total_cost == 985537


def test_suggestion_row_carries_full_breakdown(demo_store):
    rows = purchase_service.suggestions(demo_store, 30, 21, 5)
    panadol = next(row for row in rows if row["item"].name == "Panadol Extra 500mg")
    assert panadol["final_qty"] == 970
    assert panadol["breakdown"]["target_stock"] == 1612
    assert panadol["override_qty"] is None


def test_override_requires_a_reason(demo_store):
    item = DEMO_ITEMS[0]
    with pytest.raises(OverrideReasonRequired):
        purchase_service.save_override(demo_store, item, 100, "")
    with pytest.raises(OverrideReasonRequired):
        purchase_service.save_override(demo_store, item, 100, "   ")


def test_override_replaces_formula_and_is_audited(demo_store):
    item = DEMO_ITEMS[0]  # Panadol, calculated 970
    purchase_service.save_override(demo_store, item, 250, "supplier pack size")
    rows = purchase_service.suggestions(demo_store, 30, 21, 5)
    panadol = next(row for row in rows if row["item"].name == "Panadol Extra 500mg")
    assert panadol["final_qty"] == 250
    assert panadol["override_qty"] == 250
    assert panadol["override_reason"] == "supplier pack size"
    from app.services import audit_service

    entries = audit_service.list_audit(demo_store)
    assert any("Override: Panadol Extra 500mg" in e.text for e in entries)
    assert any("supplier pack size" in e.text for e in entries)


def test_override_negative_qty_rejected(demo_store):
    with pytest.raises(ValidationError):
        purchase_service.save_override(demo_store, DEMO_ITEMS[0], -5, "reason")


def test_clear_override_restores_formula(demo_store):
    item = DEMO_ITEMS[0]
    purchase_service.save_override(demo_store, item, 250, "supplier pack size")
    purchase_service.clear_override(demo_store, item)
    rows = purchase_service.suggestions(demo_store, 30, 21, 5)
    panadol = next(row for row in rows if row["item"].name == "Panadol Extra 500mg")
    assert panadol["final_qty"] == 970
    assert panadol["override_qty"] is None


def test_item_with_override_stays_on_list_even_at_zero_suggestion(demo_store):
    item = next(i for i in DEMO_ITEMS if i.name == "Deltacortril 5mg")
    purchase_service.save_override(demo_store, item, 0, "do not order this month")
    rows = purchase_service.suggestions(demo_store, 7, 21, 5)
    names = [row["item"].name for row in rows]
    assert "Deltacortril 5mg" in names
