"""Headless UI smoke tests (Qt offscreen platform).

Run with QT_QPA_PLATFORM=offscreen. Skipped automatically on machines
without importable Qt libraries.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.bootstrap import ensure_store
from app.database.seed import seed_demo_data
from app.ui.main_window import MainWindow
from app.ui.wizard import SetupWizard


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture()
def window(tmp_path, qt_app):
    store = ensure_store(tmp_path / "ui.db")
    seed_demo_data(store)
    win = MainWindow(store)
    win.show()
    return win


def test_window_title_and_kpis(window):
    assert "EMAN PHARMACY & VACCINE" in window.windowTitle()
    assert window.kpi_cards["total_items"].value.text() == "18"
    assert window.kpi_cards["out_of_stock"].value.text() == "2"
    assert window.kpi_cards["critical"].value.text() == "7"
    assert window.kpi_cards["low_stock"].value.text() == "4"
    assert window.kpi_cards["net_units_sold"].value.text() == "11,310"
    assert window.kpi_cards["estimated_purchase_value"].value.text() == "Rs 1,008,784"


def test_cover_options_include_7_days(window):
    assert sorted(window.cover_buttons.keys()) == [7, 14, 21, 30]
    assert sorted(window.period_buttons.keys()) == [7, 30, 90]
    assert window.tabs.count() == 5


def test_reorder_table_has_18_rows(window):
    assert window.reorder_table.rowCount() == 18


def test_cover_7_recalculates(window):
    QTest.mouseClick(window.cover_buttons[7], Qt.LeftButton)
    assert window.cover_days == 7
    assert window.reorder_table.rowCount() == 15
    assert "15 items" in window.reorder_summary.text()


def test_demo_toggle_off_clears_everything(window):
    window.demo_toggle.setChecked(False)
    assert window.kpi_cards["total_items"].value.text() == "—"
    assert window.stock_table.rowCount() == 0
    assert "Live data will appear" in window.report_browser.toPlainText()
    window.demo_toggle.setChecked(True)
    assert window.reorder_table.rowCount() == 18


def test_draft_add_and_approve(window):
    # Click the "+ Draft" button of the first reorder row.
    cell = window.reorder_table.cellWidget(0, 8)
    buttons = cell.findChildren(type(window.approve_button))
    draft_button = next(b for b in buttons if "+ Draft" in b.text())
    QTest.mouseClick(draft_button, Qt.LeftButton)
    assert window.draft_order_id is not None
    assert window.approve_button.isEnabled()
    QTest.mouseClick(window.approve_button, Qt.LeftButton)
    assert "Approved" in window.order_status.text()


def test_wizard_prefills_pharmacy_and_server(tmp_path, qt_app):
    store = ensure_store(tmp_path / "wizard.db")
    wizard = SetupWizard(store)
    assert wizard.profile_page.name_edit.text() == "EMAN PHARMACY & VACCINE"
    assert wizard.connection_page.server_edit.text() == r"localhost\SQLEXPRESS"
    assert wizard.connection_page.db_edit.text() == "POS_DB"
    assert wizard.data_page.demo_check.isChecked()
