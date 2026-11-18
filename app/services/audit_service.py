"""Audit trail: every important user change is recorded with a timestamp."""

from __future__ import annotations

from datetime import datetime

from ..database.models import AuditLog


def log_audit(store, text: str) -> None:
    with store.session() as session:
        session.add(AuditLog(created_at=datetime.now(), text=text))
        session.commit()


def list_audit(store, limit: int = 100) -> list[AuditLog]:
    with store.session() as session:
        rows = (
            session.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
        )
        return list(reversed(rows))
