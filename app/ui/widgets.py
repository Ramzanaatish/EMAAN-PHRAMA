"""Small reusable widgets: KPI card, empty state, money formatting."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


def format_money(amount: int) -> str:
    return f"Rs {amount:,}"


def format_number(value: int) -> str:
    return f"{value:,}"


class KpiCard(QFrame):
    """One KPI card, mirroring the HTML preview's KPI grid."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self.label = QLabel(label.upper())
        self.label.setStyleSheet("font-size: 11px; font-weight: 700; color: #71827a;")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 26px; font-weight: 800;")
        self.sub = QLabel("")
        self.sub.setStyleSheet("font-size: 12px; color: #43554e;")
        self.sub.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.sub)

    def set_value(self, text: str, sub: str = "", alert: bool = False) -> None:
        self.value.setText(text)
        self.sub.setText(sub)
        self.value.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: %s;"
            % ("#c22e2e" if alert else "#14201c")
        )


class EmptyState(QLabel):
    """Dashed empty-state box shown when no data is available."""

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setText(f"<b>{title}</b><br>{detail}")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)


def status_chip(status: str) -> QLabel:
    """Coloured status chip (OUT OF STOCK / CRITICAL / LOW / OK)."""
    labels = {
        "out": ("OUT OF STOCK", "chipOut"),
        "critical": ("CRITICAL", "chipCritical"),
        "low": ("LOW", "chipLow"),
        "ok": ("OK", "chipOk"),
    }
    text, object_name = labels.get(status, ("OK", "chipOk"))
    chip = QLabel(text)
    chip.setObjectName(object_name)
    return chip
