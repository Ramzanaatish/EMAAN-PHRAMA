"""Tests for the purchase formula.

Expected figures come from the HTML preview and the Daily Stock Report
(analysis 30 days, cover 21 days, safety 5 days) — the same numbers the
desktop app must reproduce.
"""

from __future__ import annotations

import math

import pytest

from app.core import purchase
from app.core.errors import ValidationError
from app.core.purchase import ItemFigures
from app.database.seed import DEMO_ITEMS


def test_js_round_matches_javascript():
    assert purchase.js_round(2.5) == 3
    assert purchase.js_round(0.5) == 1
    assert purchase.js_round(2.4) == 2
    assert purchase.js_round(2.6) == 3
    assert purchase.js_round(0.0) == 0


def test_panadol_suggested_970(panadol):
    assert purchase.ads(panadol) == pytest.approx(62.0)
    assert purchase.safety_stock(panadol) == 310
    assert purchase.target_stock(panadol) == 1612
    assert purchase.suggested_qty(panadol) == 970


def test_urgent_items_match_daily_report():
    expected = {
        "Brufen 400mg": (18.0, 268),
        "Augmentin 625mg": (24.0, 592),
        "Gravinate 50mg": (9.0, 114),
        "Nuberol Forte": (15.0, 382),
        "Hydryllin Syrup 120ml": (16.0, 304),
        "Flagyl 400mg": (22.0, 550),
        "Calpol Syrup 90ml": (17.0, 266),
        "Septran DS": (13.0, 305),
    }
    by_name = {item.name: item for item in DEMO_ITEMS}
    for name, (ads_value, suggested) in expected.items():
        item = by_name[name]
        assert purchase.ads(item) == pytest.approx(ads_value), name
        assert purchase.suggested_qty(item) == suggested, name


def test_cover_7_days_option_exists_and_works(panadol):
    assert 7 in purchase.COVER_DAY_OPTIONS
    purchase.validate_settings(30, 7, 5)
    # Target = ceil(62 x 7) + 310 = 744; suggested = 744 - 142 - 500 = 102
    assert purchase.target_stock(panadol, cover_days=7) == 744
    assert purchase.suggested_qty(panadol, cover_days=7) == 102


def test_cover_day_options_are_7_14_21_30():
    assert purchase.COVER_DAY_OPTIONS == (7, 14, 21, 30)
    assert purchase.ANALYSIS_DAY_OPTIONS == (7, 30, 90)
    assert purchase.DEFAULT_COVER_DAYS == 21
    assert purchase.DEFAULT_ANALYSIS_DAYS == 30
    assert purchase.DEFAULT_SAFETY_DAYS == 5


def test_cover_14_and_30(panadol):
    # Cover 14: target = ceil(62 x 14) + 310 = 1178; suggested = 1178 - 142 - 500 = 536
    assert purchase.suggested_qty(panadol, cover_days=14) == 536
    # Cover 30: target = 1860 + 310 = 2170; suggested = 2170 - 142 - 500 = 1528
    assert purchase.suggested_qty(panadol, cover_days=30) == 1528


def test_invalid_cover_and_analysis_rejected():
    with pytest.raises(ValidationError):
        purchase.validate_settings(30, 10, 5)
    with pytest.raises(ValidationError):
        purchase.validate_settings(14, 21, 5)
    with pytest.raises(ValidationError):
        purchase.validate_settings(30, 21, 31)
    with pytest.raises(ValidationError):
        purchase.validate_settings(30, 21, -1)


def test_suggested_never_negative():
    item = ItemFigures(name="X", stock=1000, net30=30)
    assert purchase.suggested_qty(item) == 0


def test_zero_sales_gives_zero_suggestion():
    item = ItemFigures(name="X", stock=10, net30=0, reorder_level=5)
    assert purchase.ads(item) == 0
    assert purchase.suggested_qty(item) == 0
    assert purchase.days_left(item) == math.inf


def test_usable_stock_excludes_unusable(augmentin):
    assert purchase.usable_stock(augmentin) == 32
    assert purchase.usable_stock(augmentin) == augmentin.stock - augmentin.unusable


def test_statuses(panadol, brufen):
    assert purchase.status_of(brufen) == purchase.STATUS_OUT
    assert purchase.status_of(panadol) == purchase.STATUS_CRITICAL
    by_name = {item.name: item for item in DEMO_ITEMS}
    assert purchase.status_of(by_name["Risek 20mg"]) == purchase.STATUS_LOW
    assert purchase.status_of(by_name["Disprin"]) == purchase.STATUS_OK
    assert purchase.status_of(by_name["Strepsils"]) == purchase.STATUS_OK


def test_calculation_breakdown_shows_every_input(panadol):
    breakdown = purchase.calculation_breakdown(panadol)
    assert breakdown["net_sold"] == 1860
    assert breakdown["analysis_days"] == 30
    assert breakdown["ads"] == pytest.approx(62.0)
    assert breakdown["cover_days"] == 21
    assert breakdown["safety_days"] == 5
    assert breakdown["safety_stock"] == 310
    assert breakdown["target_stock"] == 1612
    assert breakdown["total_stock"] == 142
    assert breakdown["unusable"] == 0
    assert breakdown["usable_stock"] == 142
    assert breakdown["incoming"] == 500
    assert breakdown["suggested_qty"] == 970


def test_seven_day_analysis_scales_from_fractions(panadol):
    # 7-day net = round(1860 x 0.24) = 446; ADS = 446 / 7
    assert purchase.net_sold(panadol, 7) == 446
    assert purchase.ads(panadol, 7) == pytest.approx(446 / 7)
    # 90-day net = round(1860 x 2.9) = 5394
    assert purchase.net_sold(panadol, 90) == 5394
