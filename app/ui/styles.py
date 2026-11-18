"""Qt stylesheet, mirroring the HTML preview's teal theme."""

from __future__ import annotations

STYLESHEET = """
QMainWindow { background: #f4f6f5; }
QWidget { font-family: "Segoe UI", "Manrope", sans-serif; font-size: 14px; color: #14201c; }
QLabel#appTitle { font-size: 26px; font-weight: 800; }
QLabel#pharmacyName { font-size: 14px; font-weight: 700; color: #0b6e5d; }
QLabel#subtitle { font-size: 13px; color: #43554e; }
QFrame#connStrip { background: #084f43; border: none; }
QFrame#connStrip QLabel { color: #eafff8; font-size: 13px; }
QFrame#connStrip QLabel#connTitle { font-weight: 800; }
QFrame#card { background: #ffffff; border: 1px solid #dde5e1; border-radius: 12px; }
QFrame#card QLabel#cardTitle { font-size: 16px; font-weight: 800; }
QLabel#hint { font-size: 13px; color: #43554e; }
QPushButton { border: 1px solid #dde5e1; background: #ffffff; border-radius: 8px;
    padding: 7px 14px; font-weight: 600; font-size: 13px; }
QPushButton:hover { border-color: #0b6e5d; }
QPushButton#primary { background: #0b6e5d; border-color: #0b6e5d; color: #ffffff; }
QPushButton#danger { border-color: #c22e2e; color: #c22e2e; }
QPushButton:disabled { color: #9aa8a2; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { padding: 9px 14px; font-weight: 700; font-size: 14px; color: #43554e;
    border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #084f43; border-bottom: 3px solid #0b6e5d; }
QTableWidget { background: #ffffff; border: 1px solid #dde5e1; border-radius: 8px;
    gridline-color: #dde5e1; selection-background-color: #e2f1ec; }
QTableWidget::item { padding: 4px 8px; }
QHeaderView::section { background: #eef2f0; font-size: 11px; font-weight: 700;
    text-transform: uppercase; color: #71827a; padding: 6px 8px; border: none; }
QLineEdit, QComboBox, QSpinBox { border: 1px solid #dde5e1; border-radius: 8px;
    padding: 7px 10px; background: #ffffff; }
QLabel#demoBadge { background: #fdf0dc; color: #a35c05; border: 1px solid #a35c05;
    border-radius: 10px; padding: 4px 10px; font-size: 12px; font-weight: 700; }
QLabel#demoOffBadge { background: #eef2f0; color: #43554e; border: 1px solid #dde5e1;
    border-radius: 10px; padding: 4px 10px; font-size: 12px; font-weight: 700; }
QLabel#formulaBar { background: #e2f1ec; color: #084f43; border-radius: 10px; padding: 10px 14px; }
QLabel#emptyState { border: 1.5px dashed #cbd5d1; border-radius: 10px; padding: 22px;
    color: #43554e; }
QLabel#chipOut { background: #fbe9e7; color: #c22e2e; border-radius: 9px; padding: 2px 9px;
    font-size: 11px; font-weight: 800; }
QLabel#chipCritical { background: #fbe9e7; color: #c22e2e; border-radius: 9px; padding: 2px 9px;
    font-size: 11px; font-weight: 800; }
QLabel#chipLow { background: #fdf0dc; color: #a35c05; border-radius: 9px; padding: 2px 9px;
    font-size: 11px; font-weight: 800; }
QLabel#chipOk { background: #e5f3e8; color: #1d7a3a; border-radius: 9px; padding: 2px 9px;
    font-size: 11px; font-weight: 800; }
QLabel#chipOverride { background: #e2f1ec; color: #084f43; border-radius: 9px; padding: 2px 9px;
    font-size: 11px; font-weight: 800; }
QFrame#laterCard { background: #eef2f0; border: 1px dashed #cbd5d1; border-radius: 12px; }
"""
