"""Tests for the SQLite store: settings, backup and restore."""

from __future__ import annotations

import pytest

from app.database.models import Override
from app.database.store import Store
from app.services import audit_service


def test_default_settings(store):
    assert store.get_setting("pharmacy_name") == "EMAN PHARMACY & VACCINE"
    assert store.get_setting("server") == r"localhost\SQLEXPRESS"
    assert store.get_setting("database") == "POS_DB"
    assert store.get_int_setting("cover_days", 0) == 21
    assert store.get_int_setting("analysis_days", 0) == 30
    assert store.get_int_setting("safety_days", 0) == 5
    assert store.get_setting("demo_data") == "on"


def test_set_and_get_setting(store):
    store.set_setting("cover_days", "14")
    assert store.get_int_setting("cover_days", 0) == 14


def test_bad_int_setting_falls_back_to_default(store):
    store.set_setting("cover_days", "not-a-number")
    assert store.get_int_setting("cover_days", 21) == 21


def test_backup_round_trip(tmp_path, demo_store):
    from datetime import datetime

    from app.database.seed import item_code_for

    with demo_store.session() as session:
        session.add(
            Override(item_code=item_code_for("Panadol Extra 500mg"), qty=100,
                     reason="test reason", created_at=datetime.now())
        )
        session.commit()
    audit_service.log_audit(demo_store, "test audit entry")
    demo_store.set_setting("safety_days", "7")

    backup_path = tmp_path / "backup.json"
    demo_store.backup_to_file(backup_path)
    assert backup_path.exists()

    restored = Store(tmp_path / "restored.db")
    restored.restore_from_file(backup_path)
    assert restored.get_int_setting("safety_days", 0) == 7
    with restored.session() as session:
        overrides = session.query(Override).all()
        assert len(overrides) == 1
        assert overrides[0].qty == 100
        assert overrides[0].reason == "test reason"
    entries = audit_service.list_audit(restored)
    assert any("test audit entry" in entry.text for entry in entries)


def test_restore_rejects_wrong_file(tmp_path, store):
    bad = tmp_path / "bad.json"
    bad.write_text('{"kind": "something-else"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Not a Pharma Purchase Assistant backup"):
        store.restore_from_file(bad)
