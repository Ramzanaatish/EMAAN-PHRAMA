"""SQLite store: engine, sessions, settings, backup and restore."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import (
    DEFAULT_ANALYSIS_DAYS,
    DEFAULT_COVER_DAYS,
    DEFAULT_DATABASE,
    DEFAULT_SAFETY_DAYS,
    DEFAULT_SERVER,
)
from .models import Base, Setting

DEFAULT_SETTINGS = {
    "pharmacy_name": "EMAN PHARMACY & VACCINE",
    "server": DEFAULT_SERVER,
    "database": DEFAULT_DATABASE,
    "auth": "windows",
    "analysis_days": str(DEFAULT_ANALYSIS_DAYS),
    "cover_days": str(DEFAULT_COVER_DAYS),
    "safety_days": str(DEFAULT_SAFETY_DAYS),
    "demo_data": "on",
    "data_source": "demo",
}


class Store:
    """Owns the assistant's SQLite database file."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self._ensure_model_columns()
        self._sessions = sessionmaker(bind=self.engine, future=True)
        self._ensure_default_settings()

    def _ensure_model_columns(self) -> None:
        """ADD COLUMN for model fields missing from an older database file.

        create_all() only creates missing TABLES — it never adds a column
        to a table that already exists. Without this, a database file made
        by an older version (e.g. products without last_sale_date, added
        in v1.3.3) would fail every insert with "no such column". Only
        nullable columns are added (existing rows get NULL, which the code
        already treats as "unknown"); anything else is left alone.
        """
        from sqlalchemy import inspect, text

        inspector = inspect(self.engine)
        with self.engine.begin() as conn:
            for table in Base.metadata.tables.values():
                existing = {
                    column["name"]
                    for column in inspector.get_columns(table.name)
                }
                for column in table.columns:
                    if column.name in existing or not column.nullable:
                        continue
                    coltype = column.type.compile(dialect=self.engine.dialect)
                    conn.execute(
                        text(
                            f'ALTER TABLE "{table.name}" '
                            f'ADD COLUMN "{column.name}" {coltype}'
                        )
                    )

    def session(self) -> Session:
        return self._sessions()

    def _ensure_default_settings(self) -> None:
        with self.session() as session:
            existing = {row.key for row in session.query(Setting).all()}
            for key, value in DEFAULT_SETTINGS.items():
                if key not in existing:
                    session.add(Setting(key=key, value=value))
            session.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self.session() as session:
            row = session.get(Setting, key)
            return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.session() as session:
            row = session.get(Setting, key)
            if row is None:
                session.add(Setting(key=key, value=value))
            else:
                row.value = value
            session.commit()

    def get_int_setting(self, key: str, default: int) -> int:
        try:
            return int(self.get_setting(key, str(default)))
        except ValueError:
            return default

    def export_backup(self) -> dict:
        """Backup payload: settings, overrides and audit trail (no POS data)."""
        from .models import AuditLog, Override

        with self.session() as session:
            settings = {row.key: row.value for row in session.query(Setting).all()}
            overrides = [
                {"item_code": row.item_code, "qty": row.qty, "reason": row.reason}
                for row in session.query(Override).all()
            ]
            audit = [
                {"created_at": row.created_at.isoformat(), "text": row.text}
                for row in session.query(AuditLog).order_by(AuditLog.id).all()
            ]
        return {
            "app": "Pharma Purchase Assistant",
            "kind": "assistant-backup",
            "created": datetime.now().isoformat(timespec="seconds"),
            "settings": settings,
            "overrides": overrides,
            "audit": audit,
        }

    def import_backup(self, payload: dict) -> None:
        """Restore a backup payload created by export_backup()."""
        from .models import AuditLog, Override

        if not isinstance(payload, dict) or payload.get("kind") != "assistant-backup":
            raise ValueError("Not a Pharma Purchase Assistant backup file.")
        with self.session() as session:
            for key, value in (payload.get("settings") or {}).items():
                row = session.get(Setting, key)
                if row is None:
                    session.add(Setting(key=key, value=str(value)))
                else:
                    row.value = str(value)
            session.query(Override).delete()
            for item in payload.get("overrides") or []:
                session.add(
                    Override(
                        item_code=item["item_code"],
                        qty=int(item["qty"]),
                        reason=item["reason"],
                        created_at=datetime.now(),
                    )
                )
            session.query(AuditLog).delete()
            for entry in payload.get("audit") or []:
                session.add(
                    AuditLog(
                        created_at=datetime.fromisoformat(entry["created_at"]),
                        text=entry["text"],
                    )
                )
            session.commit()

    def backup_to_file(self, path: Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.export_backup(), indent=2), encoding="utf-8")
        return path

    def restore_from_file(self, path: Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.import_backup(payload)
