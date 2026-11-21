"""Pharma Purchase Assistant — desktop entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from app.bootstrap import ensure_store, setup_logging
from app.core.config import resource_path
from app.database.seed import seed_demo_data
from app.services import stock_service
from app.ui.main_window import MainWindow
from app.ui.wizard import SetupWizard


def _splash_pixmap() -> QPixmap:
    """Brand splash: dark-green panel, EMAN logo, app name, Loading…

    Shown the moment the Qt app exists, so the user sees the app at
    once while the store, demo data and window are still being built.
    Falls back to text only when the logo file is missing.
    """
    pixmap = QPixmap(480, 300)
    pixmap.fill(QColor("#084f43"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    y = 56
    logo = QPixmap(str(resource_path("eman-logo-light.png")))
    if not logo.isNull():
        logo = logo.scaledToWidth(300, Qt.SmoothTransformation)
        painter.drawPixmap((480 - logo.width()) // 2, y, logo)
        y += logo.height() + 24
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 20, QFont.Bold))
    painter.drawText(0, y, 480, 30, Qt.AlignHCenter, "Pharma Purchase Assistant")
    y += 36
    painter.setPen(QColor("#8fd6bd"))
    painter.setFont(QFont("Segoe UI", 12))
    painter.drawText(0, y, 480, 24, Qt.AlignHCenter, "EMAN PHARMACY & VACCINE")
    painter.setPen(QColor("#cdeee2"))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(0, 258, 480, 24, Qt.AlignHCenter, "Loading…")
    painter.end()
    return pixmap


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Pharma Purchase Assistant")
    app.setOrganizationName("Eman Pharmacy")

    splash = QSplashScreen(_splash_pixmap())
    splash.show()
    app.processEvents()

    store = ensure_store()
    if store.get_setting("setup_done", "") != "on":
        splash.close()
        wizard = SetupWizard(store)
        if wizard.exec() != SetupWizard.Accepted:
            return 0
    if store.get_setting("demo_data", "on") == "on" and not stock_service.visible_items(store):
        seed_demo_data(store)

    window = MainWindow(store)
    window.show()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
