"""Supplier-wise purchase order draft.

A draft is only ever a draft: items are grouped by supplier, the user
reviews quantities, rates and suppliers, approves it, and only then
downloads the file to send outside the app. No order is ever sent
automatically.
"""

from __future__ import annotations

from datetime import datetime

from ..core import purchase
from ..core.purchase import ItemFigures
from ..database.models import PurchaseOrder, PurchaseOrderItem
from . import audit_service, stock_service


def build_draft(store, items: list[dict]) -> PurchaseOrder:
    """Create a draft order from suggestion rows (item dicts with final_qty)."""
    total = 0
    with store.session() as session:
        order = PurchaseOrder(status="draft", created_at=datetime.now())
        session.add(order)
        session.flush()
        for row in items:
            item: ItemFigures = row["item"]
            qty = row["final_qty"]
            session.add(
                PurchaseOrderItem(
                    order_id=order.id,
                    item_code=item.item_code,
                    qty=qty,
                    cost=item.cost,
                    basis="override" if row.get("override_qty") is not None else "formula",
                )
            )
            total += qty * item.cost
        order.total_cost = total
        session.commit()
        session.refresh(order)
        return order


def order_items(store, order_id: int) -> list[dict]:
    """Draft items grouped by supplier, with item details attached."""
    with store.session() as session:
        order = session.get(PurchaseOrder, order_id)
        if order is None:
            return []
        figures = {
            item.item_code: item for item in stock_service.visible_items(store)
        }
        groups: dict[str, list[dict]] = {}
        for line in order.items:
            item = figures.get(line.item_code)
            if item is None:
                continue
            groups.setdefault(item.supplier, []).append(
                {"item": item, "qty": line.qty, "cost": line.cost, "basis": line.basis}
            )
        return [
            {"supplier": supplier, "lines": lines}
            for supplier, lines in sorted(groups.items())
        ]


def approve_order(store, order_id: int) -> None:
    """Approve a draft. Approval is recorded in the audit trail."""
    with store.session() as session:
        order = session.get(PurchaseOrder, order_id)
        if order is None:
            raise ValueError(f"No purchase order with id {order_id}.")
        order.status = "approved"
        order.approved_at = datetime.now()
        session.commit()
    audit_service.log_audit(
        store, f"Purchase order draft APPROVE kiya gaya (order #{order_id})."
    )


def latest_draft(store) -> PurchaseOrder | None:
    with store.session() as session:
        return (
            session.query(PurchaseOrder)
            .filter(PurchaseOrder.status == "draft")
            .order_by(PurchaseOrder.id.desc())
            .first()
        )


def clear_draft(store, order_id: int) -> None:
    with store.session() as session:
        session.query(PurchaseOrderItem).filter(
            PurchaseOrderItem.order_id == order_id
        ).delete(synchronize_session=False)
        session.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).delete(
            synchronize_session=False
        )
        session.commit()
