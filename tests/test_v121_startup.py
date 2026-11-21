"""v1.2.1 smooth-startup tests: deferred first refresh + lazy tabs.

Startup must paint first and load data after: the window is built with
empty tables, the first refresh runs once the event loop starts, and
only the tab on screen is rendered — the other four render the first
time they are opened. Run with QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.bootstrap import ensure_store
from app.database.seed import seed_demo_data
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(tmp_path, qt_app):
    store = ensure_store(tmp_path / "startup.db")
    seed_demo_data(store)
    win = MainWindow(store)
    win.show()
    return win


def _pump_until_refreshed(window, timeout_s=5):
    """Let the deferred first refresh run, the way the real app does."""
    deadline = time.monotonic() + timeout_s
    while not window._last_items and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    assert window._refresh_done is True


def _show_tab(window, index):
    """Select a tab; lazy rendering fills it synchronously."""
    window.tabs.setCurrentIndex(index)
    QApplication.processEvents()


def test_first_paint_happens_before_data(window):
    """Construction alone must not compute or render any data."""
    assert window._refresh_done is False
    assert window._last_items == []
    assert window.reorder_table.rowCount() == 0
    assert window.stock_table.rowCount() == 0
    assert window.report_browser.toPlainText() == ""


def test_deferred_refresh_fires_without_manual_call(window):
    """The deferred first refresh runs once events are processed."""
    _pump_until_refreshed(window)
    assert len(window._last_items) == 18
    assert window.kpi_cards["total_items"].value.text() == "18"


def test_only_visible_tab_renders(window):
    """After refresh, hidden tabs stay empty until first opened."""
    _pump_until_refreshed(window)
    assert window._dirty_tabs == {1, 2, 3, 4}
    assert window.reorder_table.rowCount() == 0
    assert window.stock_table.rowCount() == 0
    assert window.report_browser.toPlainText() == ""
    _show_tab(window, 1)
    assert window.reorder_table.rowCount() == 18
    assert window._dirty_tabs == {2, 3, 4}
    _show_tab(window, 2)
    assert window.stock_table.rowCount() == 18
    _show_tab(window, 3)
    assert "EMAN PHARMACY" in window.report_browser.toPlainText()
    _show_tab(window, 4)
    assert "ON" in window.demo_status_text.text()
    assert window._dirty_tabs == set()


def test_refresh_marks_hidden_tabs_dirty_again(window):
    """Changing cover re-renders the open tab; hidden tabs re-render on open."""
    _pump_until_refreshed(window)
    _show_tab(window, 1)
    assert window.reorder_table.rowCount() == 18
    QTest.mouseClick(window.cover_buttons[7], Qt.LeftButton)
    assert window.cover_days == 7
    assert window.reorder_table.rowCount() == 15
    assert window._dirty_tabs == {0, 2, 3, 4}
    _show_tab(window, 2)
    assert window.stock_table.rowCount() == 18
    assert 2 not in window._dirty_tabs
