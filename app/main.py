"""Pharma Purchase Assistant — desktop entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.bootstrap import ensure_store, setup_logging
from app.database.seed import seed_demo_data
from app.services import stock_service
from app.ui.main_window import MainWindow
from app.ui.wizard import SetupWizard


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Pharma Purchase Assistant")
    app.setOrganizationName("Eman Pharmacy")

    store = ensure_store()
    if store.get_setting("setup_done", "") != "on":
        wizard = SetupWizard(store)
        if wizard.exec() != SetupWizard.Accepted:
            return 0
    if store.get_setting("demo_data", "on") == "on" and not stock_service.visible_items(store):
        seed_demo_data(store)

    window = MainWindow(store)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
