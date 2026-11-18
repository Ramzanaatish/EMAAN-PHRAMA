"""Purchase calculation engine.

Pure functions only, no database or UI access, so the numbers can be
tested on their own. The formulas mirror the HTML preview and the Final
Recommendation exactly:

    ADS = Net Sales / Analysis Days
    Safety Stock = ADS x safety days
    Target Stock = (ADS x Cover Days) + Safety Stock
    Suggested Purchase = max(0, Target Stock - Usable Stock - Confirmed Incoming)

Net sales exclude returns and cancelled sales. Usable stock excludes
expired and damaged quantities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import (
    ANALYSIS_DAY_OPTIONS,
    COVER_DAY_OPTIONS,
    DEFAULT_ANALYSIS_DAYS,
    DEFAULT_COVER_DAYS,
    DEFAULT_SAFETY_DAYS,
    MAX_SAFETY_DAYS,
)
from .errors import ValidationError

STATUS_OUT = "out"
STATUS_CRITICAL = "critical"
STATUS_LOW = "low"
STATUS_OK = "ok"

STATUS_LABELS = {
    STATUS_OUT: "OUT OF STOCK",
    STATUS_CRITICAL: "CRITICAL",
    STATUS_LOW: "LOW",
    STATUS_OK: "OK",
}


@dataclass
class ItemFigures:
    """One product's figures as imported from POS (or from demo data)."""

    name: str
    pack: str = ""
    supplier: str = ""
    stock: int = 0
    unusable: int = 0
    incoming: int = 0
    net30: int = 0
    fraction_7: float = 0.0
    fraction_90: float = 0.0
    reorder_level: int = 0
    max_level: int = 0
    cost: int = 0
    pack_size: int = 1
    item_code: str = ""
    manufacturer: str = ""
    item_group: str = ""
    expiry_batch: str = ""
    expiry_date: str = ""
    expiry_qty: int = 0
    expiry_key: int = 0
    discontinued: bool = False
    supplier_mapped: bool = True
    net_7: int | None = field(default=None)
    net_90: int | None = field(default=None)


def js_round(value: float) -> int:
    """Round half up, matching JavaScript Math.round for non-negative values.

    Python's built-in round() uses banker's rounding, so 2.5 would become
    2 here instead of the 3 the HTML preview produces.
    """
    return int(math.floor(value + 0.5))


def validate_settings(analysis_days: int, cover_days: int, safety_days: int) -> None:
    """Reject settings outside the options the UI offers."""
    if analysis_days not in ANALYSIS_DAY_OPTIONS:
        raise ValidationError(
            f"Analysis days must be one of {ANALYSIS_DAY_OPTIONS}, got {analysis_days}."
        )
    if cover_days not in COVER_DAY_OPTIONS:
        raise ValidationError(
            f"Cover days must be one of {COVER_DAY_OPTIONS}, got {cover_days}."
        )
    if not 0 <= safety_days <= MAX_SAFETY_DAYS:
        raise ValidationError(
            f"Safety days must be between 0 and {MAX_SAFETY_DAYS}, got {safety_days}."
        )


def net_sold(item: ItemFigures, analysis_days: int) -> int:
    """Net units sold in the analysis window (returns/cancelled excluded)."""
    if analysis_days == 7:
        if item.net_7 is not None:
            return item.net_7
        return js_round(item.net30 * item.fraction_7)
    if analysis_days == 90:
        if item.net_90 is not None:
            return item.net_90
        return js_round(item.net30 * item.fraction_90)
    return item.net30


def ads(item: ItemFigures, analysis_days: int = DEFAULT_ANALYSIS_DAYS) -> float:
    """Average daily sales over the analysis window."""
    return net_sold(item, analysis_days) / analysis_days


def ads30(item: ItemFigures) -> float:
    """Average daily sales over 30 days (used for days-of-cover)."""
    return item.net30 / 30


def usable_stock(item: ItemFigures) -> int:
    """Stock that can actually be sold (expired/damaged excluded)."""
    return max(0, item.stock - item.unusable)


def safety_stock(
    item: ItemFigures,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    safety_days: int = DEFAULT_SAFETY_DAYS,
) -> int:
    """Safety stock in units: ADS x safety days, rounded up."""
    return math.ceil(ads(item, analysis_days) * safety_days)


def target_stock(
    item: ItemFigures,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    cover_days: int = DEFAULT_COVER_DAYS,
    safety_days: int = DEFAULT_SAFETY_DAYS,
) -> int:
    """Target stock: (ADS x cover days) + safety stock, rounded up."""
    return math.ceil(ads(item, analysis_days) * cover_days) + safety_stock(
        item, analysis_days, safety_days
    )


def suggested_qty(
    item: ItemFigures,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    cover_days: int = DEFAULT_COVER_DAYS,
    safety_days: int = DEFAULT_SAFETY_DAYS,
) -> int:
    """Suggested purchase quantity, never below zero."""
    suggestion = target_stock(item, analysis_days, cover_days, safety_days) - usable_stock(
        item
    ) - item.incoming
    return max(0, suggestion)


def final_qty(
    item: ItemFigures,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    cover_days: int = DEFAULT_COVER_DAYS,
    safety_days: int = DEFAULT_SAFETY_DAYS,
    override_qty: int | None = None,
) -> int:
    """Quantity actually ordered: manual override wins over the formula."""
    if override_qty is not None:
        return override_qty
    return suggested_qty(item, analysis_days, cover_days, safety_days)


def needs_reorder(
    item: ItemFigures,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    cover_days: int = DEFAULT_COVER_DAYS,
    safety_days: int = DEFAULT_SAFETY_DAYS,
    has_override: bool = False,
) -> bool:
    """True when the item belongs on the reorder list."""
    return suggested_qty(item, analysis_days, cover_days, safety_days) > 0 or has_override


def days_left(item: ItemFigures) -> float:
    """How many days the usable stock lasts at the 30-day sales rate."""
    rate = ads30(item)
    if rate <= 0:
        return math.inf
    return usable_stock(item) / rate


def status_of(item: ItemFigures) -> str:
    """Stock status: out, critical (<= 3 days), low, or ok."""
    if usable_stock(item) <= 0:
        return STATUS_OUT
    if days_left(item) <= 3:
        return STATUS_CRITICAL
    if usable_stock(item) <= item.reorder_level:
        return STATUS_LOW
    return STATUS_OK


def calculation_breakdown(
    item: ItemFigures,
    analysis_days: int = DEFAULT_ANALYSIS_DAYS,
    cover_days: int = DEFAULT_COVER_DAYS,
    safety_days: int = DEFAULT_SAFETY_DAYS,
) -> dict:
    """Every input and result of one suggestion, for the UI detail view."""
    validate_settings(analysis_days, cover_days, safety_days)
    return {
        "name": item.name,
        "net_sold": net_sold(item, analysis_days),
        "analysis_days": analysis_days,
        "ads": ads(item, analysis_days),
        "cover_days": cover_days,
        "safety_days": safety_days,
        "safety_stock": safety_stock(item, analysis_days, safety_days),
        "target_stock": target_stock(item, analysis_days, cover_days, safety_days),
        "total_stock": item.stock,
        "unusable": item.unusable,
        "usable_stock": usable_stock(item),
        "incoming": item.incoming,
        "suggested_qty": suggested_qty(item, analysis_days, cover_days, safety_days),
    }
