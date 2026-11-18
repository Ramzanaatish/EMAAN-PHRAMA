"""Smart reorder suggestions and manual overrides.

A suggestion is always explainable: every input and result is available
through calculation_breakdown(). A manual override replaces the formula
quantity, but only with a written reason, and the override is recorded
in the audit trail.
"""

from __future__ import annotations

from datetime import datetime

from ..core import purchase
from ..core.errors import OverrideReasonRequired, ValidationError
from ..core.purchase import ItemFigures
from ..database.models import Override
from . import audit_service, stock_service


def suggestions(
    store, analysis_days: int, cover_days: int, safety_days: int
) -> list[dict]:
    """Reorder rows, shortest cover first, each with its full calculation."""
    purchase.validate_settings(analysis_days, cover_days, safety_days)
    overrides = stock_service._overrides(store)
    rows = []
    for item in stock_service.visible_items(store):
        if item.discontinued:
            continue
        has_override = item.item_code in overrides
        if not purchase.needs_reorder(
            item, analysis_days, cover_days, safety_days, has_override=has_override
        ):
            continue
        breakdown = purchase.calculation_breakdown(
            item, analysis_days, cover_days, safety_days
        )
        rows.append(
            {
                "item": item,
                "breakdown": breakdown,
                "override_qty": overrides.get(item.item_code),
                "override_reason": _override_reason(store, item.item_code),
                "final_qty": purchase.final_qty(
                    item,
                    analysis_days,
                    cover_days,
                    safety_days,
                    override_qty=overrides.get(item.item_code),
                ),
            }
        )
    rows.sort(key=lambda row: purchase.days_left(row["item"]))
    return rows


def _override_reason(store, item_code: str) -> str | None:
    with store.session() as session:
        row = (
            session.query(Override)
            .filter(Override.item_code == item_code)
            .order_by(Override.id.desc())
            .first()
        )
        return row.reason if row else None


def save_override(store, item: ItemFigures, qty: int, reason: str) -> None:
    """Save a manual quantity override. A reason is mandatory."""
    if qty < 0:
        raise ValidationError("Override quantity must be 0 or more.")
    reason = (reason or "").strip()
    if not reason:
        raise OverrideReasonRequired(
            "Override ke liye wajah (reason) likhna lazmi hai."
        )
    with store.session() as session:
        session.add(
            Override(
                item_code=item.item_code,
                qty=qty,
                reason=reason,
                created_at=datetime.now(),
            )
        )
        session.commit()
    audit_service.log_audit(
        store,
        f"Override: {item.name} — calculated "
        f"{purchase.suggested_qty(item)} → manual {qty} units. Reason: {reason}",
    )


def clear_override(store, item: ItemFigures) -> None:
    """Remove the override; the formula quantity applies again."""
    with store.session() as session:
        session.query(Override).filter(
            Override.item_code == item.item_code
        ).delete(synchronize_session=False)
        session.commit()
    audit_service.log_audit(
        store,
        f"Override khatam: {item.name} — wapas calculated "
        f"{purchase.suggested_qty(item)} units.",
    )
