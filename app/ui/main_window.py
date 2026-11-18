"""Main window: connection strip, header, KPIs, formula bar and five tabs.

Mirrors the HTML preview screen for screen: Overview, Reorder Suggestions,
All Stock, Daily Report (PDF), Settings / Backup / Audit — plus the
"Coming in v2" section. Pharmacy name: EMAN PHARMACY & VACCINE.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..connectors.sql_server import SqlServerConnector
from ..core import purchase
from ..core.config import (
    ANALYSIS_DAY_OPTIONS,
    COVER_DAY_OPTIONS,
    DEFAULT_ANALYSIS_DAYS,
    DEFAULT_COVER_DAYS,
    DEFAULT_SAFETY_DAYS,
    PHARMACY_NAME,
    resource_path,
    validate_server_address,
)
from ..core.errors import ConnectorError
from ..services import (
    audit_service,
    import_service,
    order_service,
    purchase_service,
    report_service,
    stock_service,
)
from .styles import STYLESHEET
from .widgets import EmptyState, KpiCard, format_money, format_number, status_chip


class CalculationDialog(QDialog):
    """Per-item calculation breakdown + manual override form."""

    def __init__(self, store, item, analysis_days, cover_days, safety_days, parent=None):
        super().__init__(parent)
        self.store = store
        self.item = item
        self.setWindowTitle(f"Calculation — {item.name}")
        self.setMinimumWidth(520)
        breakdown = purchase.calculation_breakdown(
            item, analysis_days, cover_days, safety_days
        )
        layout = QVBoxLayout(self)
        form = QFormLayout()
        rows = [
            ("Net sales", f"{breakdown['net_sold']:,} units ({analysis_days} din)"),
            ("Analysis days", f"{analysis_days} din"),
            ("ADS (net sales ÷ analysis days)", f"{breakdown['ads']:.2f} /din"),
            ("Cover days (target)", f"{cover_days} din"),
            ("Safety stock", f"{breakdown['safety_stock']:,} units (ADS × {safety_days} din)"),
            ("Target stock", f"{breakdown['target_stock']:,} units"),
            ("Total stock (POS)", f"{breakdown['total_stock']:,} units"),
            ("Unusable (expired / damaged)", f"− {breakdown['unusable']:,} units"),
            ("Usable stock", f"{breakdown['usable_stock']:,} units"),
            ("Confirmed incoming stock", f"− {breakdown['incoming']:,} units"),
        ]
        for label, value in rows:
            form.addRow(QLabel(label), QLabel(value))
        layout.addLayout(form)
        result = QLabel(
            f"Suggested = max(0, {breakdown['target_stock']:,} − "
            f"{breakdown['usable_stock']:,} − {breakdown['incoming']:,}) = "
            f"{breakdown['suggested_qty']:,} units"
        )
        result.setObjectName("formulaBar")
        layout.addWidget(result)

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(0, 1000000)
        self.qty_spin.setValue(breakdown["suggested_qty"])
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText(
            "Override ki wajah likhein (lazmi) — masalan: supplier ke paas pack size bara hai"
        )
        override_form = QFormLayout()
        override_form.addRow("Override quantity", self.qty_spin)
        override_form.addRow("Reason (required)", self.reason_edit)
        layout.addLayout(override_form)

        buttons = QDialogButtonBox()
        self.save_button = QPushButton("Override Save Karein")
        self.save_button.setObjectName("primary")
        self.clear_button = QPushButton("Override Khatam Karein")
        self.close_button = QPushButton("Close")
        buttons.addButton(self.save_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(self.clear_button, QDialogButtonBox.ActionRole)
        buttons.addButton(self.close_button, QDialogButtonBox.RejectRole)
        layout.addWidget(buttons)
        self.save_button.clicked.connect(self._save_override)
        self.clear_button.clicked.connect(self._clear_override)
        self.close_button.clicked.connect(self.reject)

    def _save_override(self):
        reason = self.reason_edit.text().strip()
        if not reason:
            QMessageBox.warning(
                self, "Reason lazmi hai",
                "Override ke liye wajah (reason) likhna lazmi hai.",
            )
            return
        purchase_service.save_override(
            self.store, self.item, self.qty_spin.value(), reason
        )
        self.accept()

    def _clear_override(self):
        purchase_service.clear_override(self.store, self.item)
        self.accept()


def segmented_buttons(options, current, on_change):
    """A row of toggle buttons acting as one segmented control."""
    layout = QHBoxLayout()
    layout.setSpacing(2)
    buttons = {}
    for option in options:
        button = QPushButton(str(option))
        button.setCheckable(True)
        button.setChecked(option == current)
        button.clicked.connect(lambda _checked, value=option: on_change(value))
        layout.addWidget(button)
        buttons[option] = button
    return layout, buttons


class MainWindow(QMainWindow):
    """The Pharma Purchase Assistant main window."""

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.analysis_days = store.get_int_setting("analysis_days", DEFAULT_ANALYSIS_DAYS)
        self.cover_days = store.get_int_setting("cover_days", DEFAULT_COVER_DAYS)
        self.safety_days = store.get_int_setting("safety_days", DEFAULT_SAFETY_DAYS)
        self.draft_order_id: int | None = None
        self.setWindowTitle(f"{PHARMACY_NAME} — Pharma Purchase Assistant")
        self.setStyleSheet(STYLESHEET)
        self.resize(1240, 860)
        self._build_shell()
        self.refresh_all()

    # ------------------------------------------------------------------ shell
    def _build_shell(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Connection strip
        strip = QFrame()
        strip.setObjectName("connStrip")
        strip_layout = QHBoxLayout(strip)
        self.conn_title = QLabel("Preview Mode — Not Connected")
        self.conn_title.setObjectName("connTitle")
        strip_layout.addWidget(self.conn_title)
        self.server_label = QLabel()
        strip_layout.addWidget(self.server_label)
        strip_layout.addWidget(QLabel("|"))
        self.database_label = QLabel()
        strip_layout.addWidget(self.database_label)
        strip_layout.addWidget(QLabel("|"))
        strip_layout.addWidget(QLabel("Access: Read-Only"))
        strip_layout.addStretch()
        self.last_fetch_label = QLabel("Last fetch: —")
        strip_layout.addWidget(self.last_fetch_label)
        self.refresh_button = QPushButton("↻ Refresh Data")
        self.refresh_button.clicked.connect(self._on_refresh)
        strip_layout.addWidget(self.refresh_button)
        root.addWidget(strip)

        # Content scrolls vertically only; wide tables scroll inside
        # themselves, so the window never grows a horizontal scrollbar.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_scroll = scroll
        root.addWidget(scroll)
        outer = QWidget()
        scroll.setWidget(outer)
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch()
        content = QWidget()
        content.setMaximumWidth(1320)
        self.content_widget = content
        outer_layout.addWidget(content)
        outer_layout.addStretch()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 32)

        # Header: pharmacy logo on dark green, app title, live/demo badge.
        # The logo file carries the EMAN wordmark, so no separate name label.
        header_bar = QFrame()
        header_bar.setObjectName("headerBar")
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(16, 12, 16, 12)
        self.logo_path = resource_path("eman-logo-light.png")
        self.header_logo = QLabel()
        pixmap = QPixmap(str(self.logo_path))
        if pixmap.isNull():
            wordmark = QVBoxLayout()
            name = QLabel("EMAN")
            name.setObjectName("headerWordmark")
            sub = QLabel("PHARMACY & VACCINE")
            sub.setObjectName("headerWordmarkSub")
            wordmark.addWidget(name)
            wordmark.addWidget(sub)
            header.addLayout(wordmark)
        else:
            self.header_logo.setPixmap(
                pixmap.scaledToHeight(54, Qt.SmoothTransformation)
            )
            header.addWidget(self.header_logo)
        title_box = QVBoxLayout()
        title = QLabel("Pharma Purchase Assistant")
        title.setObjectName("headerTitle")
        subtitle = QLabel(
            "SmilePOS ke data se rozana ki purchasing guide: kaun si medicine sab se "
            "zyada bik rahi hai, kahan stock khatam honay wala hai, aur kis supplier "
            "se kitna order karna hai — har suggestion ke peeche poori calculation "
            "nazar aati hai."
        )
        subtitle.setObjectName("headerSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, stretch=1)

        demo_box = QVBoxLayout()
        demo_row = QHBoxLayout()
        demo_label = QLabel("Demo Data")
        demo_label.setObjectName("headerSubtitle")
        demo_row.addWidget(demo_label)
        self.demo_toggle = QCheckBox()
        self.demo_toggle.setChecked(stock_service.is_demo(self.store))
        self.demo_toggle.toggled.connect(self._on_demo_toggled)
        demo_row.addWidget(self.demo_toggle)
        self.demo_state = QLabel("ON" if stock_service.is_demo(self.store) else "OFF")
        self.demo_state.setObjectName("liveBadge")
        demo_row.addWidget(self.demo_state)
        demo_box.addLayout(demo_row)
        self.preview_badge = QLabel("● PREVIEW — sample data dikhaya ja raha hai")
        self.preview_badge.setObjectName("demoBadge")
        self.demo_off_badge = QLabel("Demo data OFF — sirf live data dikhega")
        self.demo_off_badge.setObjectName("demoOffBadge")
        demo_box.addWidget(self.preview_badge)
        demo_box.addWidget(self.demo_off_badge)
        header.addLayout(demo_box)
        layout.addWidget(header_bar)

        # KPI cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_cards = {}
        for key, label in [
            ("total_items", "Total Items"),
            ("out_of_stock", "Out of Stock"),
            ("critical", "Critical (≤ 3 din)"),
            ("low_stock", "Low Stock"),
            ("net_units_sold", "Net Units Sold"),
            ("estimated_purchase_value", "Est. Purchase Value"),
        ]:
            card = KpiCard(label)
            self.kpi_cards[key] = card
            kpi_row.addWidget(card)
        layout.addLayout(kpi_row)

        # Formula bar
        formula = QLabel(
            "Purchase Formula (Final Recommendation):  "
            "ADS = Net Sales ÷ Analysis Days  ·  "
            "Target Stock = (ADS × Cover Days) + Safety Stock  ·  "
            "Suggested Purchase = max(0, Target Stock − Usable Stock − Confirmed Incoming)"
        )
        formula.setObjectName("formulaBar")
        formula.setWordWrap(True)
        layout.addWidget(formula)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_reorder_tab(), "Reorder Suggestions")
        self.tabs.addTab(self._build_stock_tab(), "All Stock")
        self.tabs.addTab(self._build_report_tab(), "Daily Report (PDF)")
        self.tabs.addTab(self._build_settings_tab(), "Settings / Backup / Audit")
        layout.addWidget(self.tabs)

        # V2 / later section (planned only, no working controls)
        later = QFrame()
        later.setObjectName("laterCard")
        later_layout = QVBoxLayout(later)
        later_layout.addWidget(QLabel("Coming in v2 — Later  (Not in V1)"))
        later_text = QLabel(
            "Version 1 mein ye kaam karta hai: Overview Dashboard, Reorder Suggestions, "
            "All Stock, Supplier-wise PO Draft, Daily Report (PDF/Excel) aur Settings / "
            "Backup / Audit. Neeche wali cheezein V1 se bahir hain: Goods Receiving (GRN), "
            "Invoice Matching, Payment & PO Lifecycle Tracking, Multi-Branch / Cloud "
            "Dashboard, Online Licensing, AI Prediction / Chatbot, More POS Connectors, "
            "Order Tracking."
        )
        later_text.setWordWrap(True)
        later_layout.addWidget(later_text)
        layout.addWidget(later)
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------ helpers
    def toast(self, message: str) -> None:
        self.statusBar().showMessage(message, 4000)

    def _sync_segmented(self, buttons: dict, value) -> None:
        for option, button in buttons.items():
            button.setChecked(option == value)

    def _set_analysis(self, days: int) -> None:
        self.analysis_days = days
        self.store.set_setting("analysis_days", str(days))
        self._sync_segmented(self.period_buttons, days)
        self._sync_segmented(self.reorder_period_buttons, days)
        self.refresh_all()
        self.toast(f"Sales analysis ab {days} din par hai — ADS aur suggestions dobara calculate ho gayein.")

    def _set_cover(self, days: int) -> None:
        self.cover_days = days
        self.store.set_setting("cover_days", str(days))
        self._sync_segmented(self.cover_buttons, days)
        self.draft_order_id = None
        self.refresh_all()
        self.toast(f"Suggestions {days} din cover par dobara calculate ho gayein — draft dobara banayein.")

    # ------------------------------------------------------------------ demo switch
    def _on_demo_toggled(self, checked: bool) -> None:
        if checked:
            import_service.enable_demo(self.store)
            self.toast("Demo data ON — sample data PREVIEW ke saath dikh raha hai.")
        else:
            import_service.disable_demo(self.store)
            self.draft_order_id = None
            self.toast("Demo data hata diya gaya — ab sirf live data dikhega, POS_DB connect honay ke baad.")
        self.refresh_all()

    def _on_refresh(self) -> None:
        try:
            connector = SqlServerConnector(
                server=self.store.get_setting("server"),
                database=self.store.get_setting("database"),
                auth=self.store.get_setting("auth"),
            )
            result = import_service.refresh_from_pos(self.store, connector)
            self.draft_order_id = None
            self.refresh_all()
            self.toast(f"Live data refresh ho gaya — {result['rows_imported']} items import hue.")
        except ConnectorError as exc:
            QMessageBox.warning(
                self, "Refresh fail hua",
                f"POS_DB se connect nahi ho saka:\n\n{exc}\n\n"
                "Client PC par SQL Server (SQLEXPRESS) service aur ODBC Driver "
                "check karein.",
            )

    # ------------------------------------------------------------------ refresh
    def refresh_all(self) -> None:
        demo = stock_service.is_demo(self.store)
        self.demo_toggle.setChecked(demo)
        self.demo_state.setText("ON" if demo else "OFF")
        self.preview_badge.setVisible(demo)
        self.demo_off_badge.setVisible(not demo)
        self.server_label.setText(f"Target Server  {self.store.get_setting('server')}")
        self.database_label.setText(
            f"Database  {self.store.get_setting('database')} (SmilePOS)"
        )
        self.conn_title.setText(
            "Preview Mode — Not Connected" if demo else "Not Connected — No Live Data"
        )
        last_fetch = self.store.get_setting("last_fetch", "")
        self.last_fetch_label.setText(
            f"Last fetch: {last_fetch} (sample)" if demo and last_fetch
            else f"Last fetch: {last_fetch}" if last_fetch
            else "Last fetch: — abhi tak koi live fetch nahi hua"
        )
        self._render_kpis()
        self._render_overview()
        self._render_reorder()
        self._render_stock()
        self._render_report()
        self._render_settings()

    def _render_kpis(self) -> None:
        data = stock_service.kpis(
            self.store, self.analysis_days, self.cover_days, self.safety_days
        )
        labels = {
            "total_items": ("Total Items", "catalogue"),
            "out_of_stock": ("Out of Stock", "usable stock khatam"),
            "critical": ("Critical (≤ 3 din)", "stock khatam honay wala"),
            "low_stock": ("Low Stock", "reorder level se neechay"),
            "net_units_sold": (f"Net Units Sold ({self.analysis_days} din)", "returns/cancelled hata kar"),
            "estimated_purchase_value": ("Est. Purchase Value", f"{self.cover_days} din cover ki suggestions"),
        }
        for key, card in self.kpi_cards.items():
            if not data:
                card.set_value("—", "POS_DB connect honay ke baad live figure aayega")
                continue
            value = data[key]
            text = format_money(value) if key == "estimated_purchase_value" else format_number(value)
            alert = key in ("out_of_stock", "critical") and value > 0
            card.set_value(text, labels[key][1], alert=alert)

    # ------------------------------------------------------------------ overview tab
    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        left = QVBoxLayout()
        demand_card = QFrame()
        demand_card.setObjectName("card")
        demand_layout = QVBoxLayout(demand_card)
        head = QHBoxLayout()
        head.addWidget(QLabel("Most Demanding Medicines"))
        head.addStretch()
        self.period_layout, self.period_buttons = segmented_buttons(
            ANALYSIS_DAY_OPTIONS, self.analysis_days, self._set_analysis
        )
        head.addLayout(self.period_layout)
        demand_layout.addLayout(head)
        hint = QLabel("Sab se zyada biknay wali items — net units sold ke hisab se rank.")
        hint.setObjectName("hint")
        demand_layout.addWidget(hint)
        self.demand_list = QVBoxLayout()
        demand_layout.addLayout(self.demand_list)
        demand_layout.addStretch()
        left.addWidget(demand_card)

        right = QVBoxLayout()
        attention_card = QFrame()
        attention_card.setObjectName("card")
        attention_layout = QVBoxLayout(attention_card)
        attention_layout.addWidget(QLabel("⚠ Needs Attention"))
        attention_hint = QLabel("Usable stock 3 din ya is se pehle khatam honay wala hai — pehle ye order karein.")
        attention_hint.setObjectName("hint")
        attention_layout.addWidget(attention_hint)
        self.attention_list = QVBoxLayout()
        attention_layout.addLayout(self.attention_list)
        attention_layout.addStretch()
        right.addWidget(attention_card)

        expiry_card = QFrame()
        expiry_card.setObjectName("card")
        expiry_layout = QVBoxLayout(expiry_card)
        expiry_layout.addWidget(QLabel("Near Expiry"))
        expiry_hint = QLabel("6 mah ke andar expire honay walay batches — ye quantity usable stock mein nahi gini jati.")
        expiry_hint.setObjectName("hint")
        expiry_layout.addWidget(expiry_hint)
        self.expiry_list = QVBoxLayout()
        expiry_layout.addLayout(self.expiry_list)
        expiry_layout.addStretch()
        right.addWidget(expiry_card)

        layout.addLayout(left, stretch=3)
        layout.addLayout(right, stretch=2)
        return tab

    def _clear_layout(self, layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_overview(self) -> None:
        items = stock_service.visible_items(self.store)
        self._clear_layout(self.demand_list)
        self._clear_layout(self.attention_list)
        self._clear_layout(self.expiry_list)
        if not items:
            self.demand_list.addWidget(EmptyState(
                "Live data will appear here after connecting to POS_DB.",
                "Filhal koi data nahi — demo data off hai.",
            ))
            self.attention_list.addWidget(EmptyState(
                "Live data will appear here after connecting to POS_DB.", ""))
            self.expiry_list.addWidget(EmptyState(
                "Live data will appear here after connecting to POS_DB.", ""))
            return
        ranked = stock_service.demand_ranking(self.store, self.analysis_days, limit=10)
        top_qty = purchase.net_sold(ranked[0], self.analysis_days) or 1
        for index, item in enumerate(ranked):
            qty = purchase.net_sold(item, self.analysis_days)
            row = QHBoxLayout()
            name = QLabel(f"{item.name}\n{item.pack} · {item.supplier}")
            name.setMinimumWidth(190)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(max(3, int(qty / top_qty * 100)))
            bar.setTextVisible(False)
            bar.setStyleSheet(
                "QProgressBar { background: #eef2f0; border-radius: 6px; height: 16px; }"
                "QProgressBar::chunk { background: %s; border-radius: 6px; }"
                % ("#c22e2e" if index < 3 else "#0b6e5d")
            )
            row.addWidget(name)
            row.addWidget(bar, stretch=1)
            row.addWidget(QLabel(f"{qty:,} units"))
            self.demand_list.addLayout(row)
        for item in stock_service.needs_attention(self.store):
            row = QHBoxLayout()
            row.addWidget(status_chip(purchase.status_of(item)))
            info = QLabel(f"{item.name}\n{item.supplier} · usable stock "
                          f"{purchase.usable_stock(item):,} · ADS "
                          f"{purchase.ads30(item):.1f}/din")
            row.addWidget(info, stretch=1)
            days = purchase.days_left(item)
            row.addWidget(QLabel("Khatam" if days == float("inf") else f"{days:.1f} din"))
            self.attention_list.addLayout(row)
        for item in stock_service.near_expiry(self.store):
            row = QHBoxLayout()
            row.addWidget(QLabel(
                f"{item.name}\nBatch {item.expiry_batch} · {item.expiry_qty:,} units "
                "(usable mein shaamil nahi)"
            ), stretch=1)
            row.addWidget(QLabel(f"EXP {item.expiry_date}"))
            self.expiry_list.addLayout(row)

    # ------------------------------------------------------------------ reorder tab
    def _build_reorder_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("Reorder Suggestions"))
        hint = QLabel(
            "Har suggestion ke saath poori calculation nazar aati hai — “Calculation” "
            "dabayein. Quantity ghalat lagay to manual override kar sakte hain, lekin "
            "wajah (reason) likhna lazmi hai — override audit trail mein record ho jata "
            "hai. Koi order khud nahi banta; pehle draft banta hai, phir aap approve "
            "karte hain."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        formula = QLabel(
            "Formula:  ADS = Net Sales ÷ Analysis Days  ·  "
            "Target = (ADS × Cover Days) + Safety Stock  ·  "
            "Suggested = max(0, Target − Usable Stock − Confirmed Incoming Stock)"
        )
        formula.setObjectName("formulaBar")
        formula.setWordWrap(True)
        card_layout.addWidget(formula)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Sales analysis:"))
        self.reorder_period_layout, self.reorder_period_buttons = segmented_buttons(
            ANALYSIS_DAY_OPTIONS, self.analysis_days, self._set_analysis
        )
        controls.addLayout(self.reorder_period_layout)
        controls.addWidget(QLabel("Cover chahiye:"))
        self.cover_layout, self.cover_buttons = segmented_buttons(
            COVER_DAY_OPTIONS, self.cover_days, self._set_cover
        )
        controls.addLayout(self.cover_layout)
        controls.addStretch()
        self.reorder_summary = QLabel("")
        controls.addWidget(self.reorder_summary)
        card_layout.addLayout(controls)
        self.safety_echo = QLabel(f"Safety stock: {self.safety_days} din ka ADS — Settings se tabdeel kar sakte hain.")
        self.safety_echo.setObjectName("hint")
        card_layout.addWidget(self.safety_echo)

        self.reorder_table = QTableWidget()
        self.reorder_table.setColumnCount(9)
        self.reorder_table.setHorizontalHeaderLabels([
            "Medicine", "Supplier", "Usable Stock", "ADS", "Target",
            "Incoming", "Order Qty", "Est. Cost", "",
        ])
        self.reorder_table.horizontalHeader().setStretchLastSection(True)
        self.reorder_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.reorder_table.setSelectionBehavior(QTableWidget.SelectRows)
        card_layout.addWidget(self.reorder_table)

        order_box = QFrame()
        order_box.setObjectName("card")
        order_layout = QVBoxLayout(order_box)
        order_layout.addWidget(QLabel("Supplier-wise Purchase Order — Draft"))
        self.order_status = QLabel("Status: Draft — ye order abhi kahin nahi gaya.")
        self.order_status.setObjectName("hint")
        order_layout.addWidget(self.order_status)
        self.order_body = QVBoxLayout()
        order_layout.addLayout(self.order_body)
        self.order_total_label = QLabel("")
        order_layout.addWidget(self.order_total_label)
        order_buttons = QHBoxLayout()
        self.approve_button = QPushButton("✓ Approve Draft")
        self.approve_button.setObjectName("primary")
        self.approve_button.clicked.connect(self._on_approve_order)
        self.download_order_button = QPushButton("⬇ Download Order File")
        self.download_order_button.clicked.connect(self._on_download_order)
        self.clear_order_button = QPushButton("Clear")
        self.clear_order_button.clicked.connect(self._on_clear_order)
        order_buttons.addWidget(self.approve_button)
        order_buttons.addWidget(self.download_order_button)
        order_buttons.addWidget(self.clear_order_button)
        order_buttons.addStretch()
        order_layout.addLayout(order_buttons)
        card_layout.addWidget(order_box)
        layout.addWidget(card)
        return tab

    def _render_reorder(self) -> None:
        rows = purchase_service.suggestions(
            self.store, self.analysis_days, self.cover_days, self.safety_days
        )
        table = self.reorder_table
        table.setRowCount(0)
        if not stock_service.visible_items(self.store):
            self.reorder_summary.setText("")
            table.setRowCount(1)
            table.setSpan(0, 0, 1, 9)
            empty = EmptyState(
                "Live data will appear here after connecting to POS_DB.",
                "Filhal koi data nahi — demo data off hai.",
            )
            table.setCellWidget(0, 0, empty)
            self._render_order_box()
            return
        table.setRowCount(len(rows))
        total_qty = 0
        total_cost = 0
        for row_index, row in enumerate(rows):
            item = row["item"]
            qty = row["final_qty"]
            cost = qty * item.cost
            total_qty += qty
            total_cost += cost
            table.setItem(row_index, 0, QTableWidgetItem(f"{item.name}\n{item.pack}"))
            table.setItem(row_index, 1, QTableWidgetItem(item.supplier))
            table.setItem(row_index, 2, QTableWidgetItem(f"{purchase.usable_stock(item):,}"))
            table.setItem(row_index, 3, QTableWidgetItem(f"{purchase.ads(item, self.analysis_days):.1f}"))
            table.setItem(row_index, 4, QTableWidgetItem(f"{row['breakdown']['target_stock']:,}"))
            table.setItem(row_index, 5, QTableWidgetItem(f"{item.incoming:,}"))
            qty_text = f"{qty:,}"
            if row["override_qty"] is not None:
                qty_text += f"  (override · calc: {row['breakdown']['suggested_qty']:,})"
            table.setItem(row_index, 6, QTableWidgetItem(qty_text))
            table.setItem(row_index, 7, QTableWidgetItem(format_money(cost)))
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            calc_button = QPushButton("▾ Calculation")
            calc_button.clicked.connect(
                lambda _checked, it=item: self._open_calculation(it)
            )
            in_draft = self._draft_contains(item.item_code)
            draft_button = QPushButton("✓ Draft mein hai" if in_draft else "+ Draft")
            if not in_draft:
                draft_button.setObjectName("primary")
            draft_button.clicked.connect(
                lambda _checked, it=item: self._toggle_draft(it)
            )
            actions_layout.addWidget(calc_button)
            actions_layout.addWidget(draft_button)
            table.setCellWidget(row_index, 8, actions)
        self.reorder_summary.setText(
            f"{len(rows)} items · total {total_qty:,} units · {format_money(total_cost)}"
        )
        self._render_order_box()

    def _open_calculation(self, item) -> None:
        dialog = CalculationDialog(
            self.store, item, self.analysis_days, self.cover_days, self.safety_days, self
        )
        if dialog.exec():
            self.draft_order_id = None
            self.refresh_all()
            self.toast("Override save ho gaya aur audit trail mein record hai.")

    def _draft_contains(self, item_code: str) -> bool:
        if self.draft_order_id is None:
            return False
        with self.store.session() as session:
            from ..database.models import PurchaseOrderItem

            return (
                session.query(PurchaseOrderItem)
                .filter(PurchaseOrderItem.order_id == self.draft_order_id)
                .filter(PurchaseOrderItem.item_code == item_code)
                .first()
                is not None
            )

    def _toggle_draft(self, item) -> None:
        rows = purchase_service.suggestions(
            self.store, self.analysis_days, self.cover_days, self.safety_days
        )
        if self.draft_order_id is None:
            order = order_service.build_draft(self.store, [])
            self.draft_order_id = order.id
        with self.store.session() as session:
            from ..database.models import PurchaseOrder, PurchaseOrderItem

            existing = (
                session.query(PurchaseOrderItem)
                .filter(PurchaseOrderItem.order_id == self.draft_order_id)
                .filter(PurchaseOrderItem.item_code == item.item_code)
                .first()
            )
            if existing:
                session.delete(existing)
            else:
                row = next(r for r in rows if r["item"].item_code == item.item_code)
                session.add(
                    PurchaseOrderItem(
                        order_id=self.draft_order_id,
                        item_code=item.item_code,
                        qty=row["final_qty"],
                        cost=item.cost,
                        basis="override" if row["override_qty"] is not None else "formula",
                    )
                )
            order = session.get(PurchaseOrder, self.draft_order_id)
            order.status = "draft"
            order.approved_at = None
            session.commit()
        self.refresh_all()

    def _render_order_box(self) -> None:
        self._clear_layout(self.order_body)
        if self.draft_order_id is None:
            self.order_body.addWidget(QLabel(
                "Abhi koi item draft mein nahi. Upar table se “+ Draft” dabayein — "
                "order supplier ke hisab se khud group ho jayega."
            ))
            self.order_total_label.setText("")
            self.approve_button.setEnabled(False)
            self.download_order_button.setEnabled(False)
            self.clear_order_button.setEnabled(False)
            return
        groups = order_service.order_items(self.store, self.draft_order_id)
        if not groups:
            self.order_body.addWidget(QLabel(
                "Abhi koi item draft mein nahi. Upar table se “+ Draft” dabayein."
            ))
            self.order_total_label.setText("")
            self.approve_button.setEnabled(False)
            self.download_order_button.setEnabled(False)
            self.clear_order_button.setEnabled(False)
            return
        total = 0
        for group in groups:
            group_label = QLabel(f"<b>{group['supplier'].upper()}</b>")
            self.order_body.addWidget(group_label)
            for line in group["lines"]:
                item = line["item"]
                line_cost = line["qty"] * line["cost"]
                total += line_cost
                text = (f"{item.name} ({item.pack}) — {line['qty']:,} units · "
                        f"{format_money(line_cost)}")
                if line["basis"] == "override":
                    text += "  [OVERRIDE]"
                self.order_body.addWidget(QLabel(text))
        with self.store.session() as session:
            from ..database.models import PurchaseOrder

            order = session.get(PurchaseOrder, self.draft_order_id)
            approved = order is not None and order.status == "approved"
        self.order_total_label.setText(f"Total Estimated Cost: {format_money(total)}")
        self.order_status.setText(
            "Status: Approved ✓ — ab file download kar ke supplier ko bhejein. "
            "Approval audit trail mein record hai."
            if approved
            else "Status: Draft — ye order abhi kahin nahi gaya. Quantities, rates aur "
                 "supplier details check kar ke approve karein, phir file download kar "
                 "ke supplier ko bhejein."
        )
        self.approve_button.setEnabled(not approved)
        self.download_order_button.setEnabled(True)
        self.clear_order_button.setEnabled(True)

    def _on_approve_order(self) -> None:
        if self.draft_order_id is None:
            return
        order_service.approve_order(self.store, self.draft_order_id)
        self.refresh_all()
        self.toast("Draft approve ho gaya — ab file download kar ke supplier ko bhejein.")

    def _on_download_order(self) -> None:
        if self.draft_order_id is None:
            return
        from ..services.report_service import format_money as _money

        groups = order_service.order_items(self.store, self.draft_order_id)
        if not groups:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Purchase Order Draft Save Karein",
            f"Purchase-Order-Draft-{self.draft_order_id}.html",
            "HTML Files (*.html)",
        )
        if not path:
            return
        rows_html = ""
        total = 0
        for group in groups:
            rows_html += f'<tr><td colspan="5" style="background:#eef2f0;font-weight:700">{group["supplier"]}</td></tr>'
            for line in group["lines"]:
                item = line["item"]
                line_cost = line["qty"] * line["cost"]
                total += line_cost
                rows_html += (
                    f"<tr><td>{item.name}</td><td>{item.pack}</td>"
                    f"<td style='text-align:right'>{line['qty']:,}</td>"
                    f"<td style='text-align:right'>{_money(line_cost)}</td>"
                    f"<td>{'Override' if line['basis'] == 'override' else 'Formula'}</td></tr>"
                )
        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Purchase Order — Draft</title>"
            "<style>body{font-family:Arial,sans-serif;margin:32px;color:#14201c}"
            "table{width:100%;border-collapse:collapse}"
            "th,td{border:1px solid #cbd5d1;padding:7px 9px;font-size:13px}"
            "h1{font-size:20px}</style></head><body>"
            f"<h1>Purchase Order (Draft) — {PHARMACY_NAME}</h1>"
            f"<p>Status: Draft — review pending · Analysis: {self.analysis_days} din · "
            f"Cover: {self.cover_days} din · Safety: {self.safety_days} din<br>"
            "Formula: Suggested = max(0, (ADS × Cover Days) + Safety Stock − Usable Stock "
            "− Confirmed Incoming), ADS = Net Sales ÷ Analysis Days. "
            "Source: SmilePOS POS_DB (read-only).</p>"
            "<table><tr><th style='text-align:left'>Medicine</th>"
            "<th style='text-align:left'>Pack</th><th style='text-align:right'>Qty</th>"
            "<th style='text-align:right'>Est. Cost</th><th style='text-align:left'>Basis</th></tr>"
            f"{rows_html}"
            f'<tr><td colspan="3" style="text-align:right;font-weight:700">Total</td>'
            f"<td style='text-align:right;font-weight:700'>{_money(total)}</td><td></td></tr></table>"
            "<p style='color:#666;font-size:12px'>Rates supplier se confirm karein — ye "
            "estimated purchase rates hain. Ye draft hai; bhejne ki zimmedari user ki hai.</p>"
            "</body></html>"
        )
        Path(path).write_text(html, encoding="utf-8")
        audit_service.log_audit(
            self.store, f"Purchase order draft file download ki gayi (order #{self.draft_order_id})."
        )
        self.toast("Purchase order draft download ho gaya.")

    def _on_clear_order(self) -> None:
        if self.draft_order_id is None:
            return
        order_service.clear_draft(self.store, self.draft_order_id)
        self.draft_order_id = None
        self.refresh_all()
        self.toast("Draft saaf ho gaya.")

    # ------------------------------------------------------------------ stock tab
    def _build_stock_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("Complete Stock Position"))
        hint = QLabel(
            "ItemStock view se position — purchases − sales ± returns + opening stock. "
            "“Usable” mein expired/damaged quantity shaamil nahi. Search ya supplier se filter karein."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        toolbar = QHBoxLayout()
        self.stock_search = QLineEdit()
        self.stock_search.setPlaceholderText("Medicine ka naam search karein…")
        self.stock_search.textChanged.connect(self._render_stock)
        toolbar.addWidget(self.stock_search, stretch=1)
        self.supplier_filter = QComboBox()
        self.supplier_filter.addItem("Sab Suppliers", "")
        self.supplier_filter.currentIndexChanged.connect(self._render_stock)
        toolbar.addWidget(self.supplier_filter)
        self.status_filter = QComboBox()
        for label, value in [("Sab Status", ""), ("Out of Stock", "out"),
                             ("Critical", "critical"), ("Low", "low"), ("OK", "ok")]:
            self.status_filter.addItem(label, value)
        self.status_filter.currentIndexChanged.connect(self._render_stock)
        toolbar.addWidget(self.status_filter)
        card_layout.addLayout(toolbar)
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(8)
        self.stock_table.setHorizontalHeaderLabels([
            "Medicine", "Supplier", "Stock", "Usable", "Net Sold (30 din)",
            "Stock chalega", "ReOrder / Max", "Status",
        ])
        self.stock_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        card_layout.addWidget(self.stock_table)
        self.stock_empty = QLabel("Koi item match nahi hua — search ya filter badal kar dekhein.")
        self.stock_empty.setObjectName("hint")
        card_layout.addWidget(self.stock_empty)
        layout.addWidget(card)
        return tab

    def _render_stock(self) -> None:
        suppliers = stock_service.suppliers(self.store)
        current = self.supplier_filter.currentData()
        self.supplier_filter.blockSignals(True)
        self.supplier_filter.clear()
        self.supplier_filter.addItem("Sab Suppliers", "")
        for supplier in suppliers:
            self.supplier_filter.addItem(supplier, supplier)
        index = self.supplier_filter.findData(current)
        self.supplier_filter.setCurrentIndex(index if index >= 0 else 0)
        self.supplier_filter.blockSignals(False)
        rows = stock_service.stock_rows(
            self.store,
            query=self.stock_search.text(),
            supplier=self.supplier_filter.currentData() or "",
            status=self.status_filter.currentData() or "",
        )
        table = self.stock_table
        table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            status = purchase.status_of(item)
            table.setItem(row_index, 0, QTableWidgetItem(f"{item.name}\n{item.pack}"))
            table.setItem(row_index, 1, QTableWidgetItem(item.supplier))
            table.setItem(row_index, 2, QTableWidgetItem(f"{item.stock:,}"))
            table.setItem(row_index, 3, QTableWidgetItem(f"{purchase.usable_stock(item):,}"))
            table.setItem(row_index, 4, QTableWidgetItem(f"{item.net30:,}"))
            days = purchase.days_left(item)
            days_text = "Khatam" if purchase.usable_stock(item) <= 0 else (
                "—" if days == float("inf") else
                f"{days:.1f} din" if days < 10 else f"{round(days)} din"
            )
            table.setItem(row_index, 5, QTableWidgetItem(days_text))
            table.setItem(row_index, 6, QTableWidgetItem(f"{item.reorder_level:,} / {item.max_level:,}"))
            chip = status_chip(status)
            table.setCellWidget(row_index, 7, chip)
        self.stock_empty.setVisible(
            bool(stock_service.visible_items(self.store)) and not rows
        )

    # ------------------------------------------------------------------ report tab
    def _build_report_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        report_intro = QLabel(
            "Rozana subah yahi report PDF ban kar ready milti hai — neechay usi ka preview hai."
        )
        report_intro.setWordWrap(True)
        controls.addWidget(report_intro, stretch=1)
        self.download_pdf_button = QPushButton("⬇ Download Daily Report (PDF)")
        self.download_pdf_button.setObjectName("primary")
        self.download_pdf_button.clicked.connect(self._on_download_pdf)
        self.download_excel_button = QPushButton("⬇ Download Excel")
        self.download_excel_button.clicked.connect(self._on_download_excel)
        controls.addWidget(self.download_pdf_button)
        controls.addWidget(self.download_excel_button)
        layout.addLayout(controls)
        self.report_browser = QTextBrowser()
        layout.addWidget(self.report_browser, stretch=1)
        return tab

    def _render_report(self) -> None:
        data = report_service.build_report_data(
            self.store, self.analysis_days, self.cover_days, self.safety_days
        )
        if not data["summary"]["total_items"]:
            self.report_browser.setHtml(
                "<div style='border:1.5px dashed #cbd5d1;padding:22px;text-align:center'>"
                "<b>Live data will appear here after connecting to POS_DB.</b><br>"
                "Report structure (live data aanay par): Stock Position Summary · Urgent "
                "Purchases (stock ≤ 3 din) · Top Selling Items · Supplier-wise Suggested "
                "Purchases — har report par date aur data-refresh time likha hoga.</div>"
            )
            return
        self.report_browser.setHtml(report_service.render_html(data))

    def _on_download_pdf(self) -> None:
        data = report_service.build_report_data(
            self.store, self.analysis_days, self.cover_days, self.safety_days
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Daily Report (PDF) Save Karein",
            f"Daily-Stock-Report-{data['report_date'].strftime('%Y-%m-%d')}.pdf",
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        report_service.render_pdf(data, Path(path))
        audit_service.log_audit(self.store, "Daily report PDF download ki gayi.")
        self.toast("Daily report PDF download ho gayi.")

    def _on_download_excel(self) -> None:
        data = report_service.build_report_data(
            self.store, self.analysis_days, self.cover_days, self.safety_days
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Daily Report (Excel) Save Karein",
            f"Daily-Stock-Report-{data['report_date'].strftime('%Y-%m-%d')}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        report_service.render_excel(data, Path(path))
        audit_service.log_audit(self.store, "Daily report Excel download ki gayi.")
        self.toast("Daily report Excel download ho gayi.")

    # ------------------------------------------------------------------ settings tab
    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        grid = QGridLayout()

        demo_card = QFrame()
        demo_card.setObjectName("card")
        demo_layout = QVBoxLayout(demo_card)
        demo_layout.addWidget(QLabel("Demo Data"))
        demo_hint = QLabel(
            "Demo data sirf layout samajhne ke liye hai. Jab asal software POS_DB se "
            "live data fetch karay ga, demo data hata dein taake sirf real data nazar "
            "aaye — sample rows aur figures kahin nahi rahenge."
        )
        demo_hint.setObjectName("hint")
        demo_hint.setWordWrap(True)
        demo_layout.addWidget(demo_hint)
        self.demo_status_text = QLabel("")
        demo_layout.addWidget(self.demo_status_text)
        demo_buttons = QHBoxLayout()
        self.remove_demo_button = QPushButton("Remove Demo Data")
        self.remove_demo_button.setObjectName("danger")
        self.remove_demo_button.clicked.connect(lambda: self._on_demo_toggled(False))
        self.restore_demo_button = QPushButton("Demo Data Wapas Layein")
        self.restore_demo_button.clicked.connect(lambda: self._on_demo_toggled(True))
        demo_buttons.addWidget(self.remove_demo_button)
        demo_buttons.addWidget(self.restore_demo_button)
        demo_buttons.addStretch()
        demo_layout.addLayout(demo_buttons)
        demo_layout.addStretch()
        grid.addWidget(demo_card, 0, 0)

        conn_card = QFrame()
        conn_card.setObjectName("card")
        conn_layout = QVBoxLayout(conn_card)
        conn_layout.addWidget(QLabel("POS Connection (Read-Only)"))
        conn_hint = QLabel(
            "Helper sirf parhta hai — POS_DB mein kabhi koi INSERT / UPDATE / DELETE "
            "nahi hota. Aik dafa settings save karein, phir har refresh khud connect "
            "ho jata hai."
        )
        conn_hint.setObjectName("hint")
        conn_hint.setWordWrap(True)
        conn_layout.addWidget(conn_hint)
        conn_form = QFormLayout()
        self.cfg_server = QLineEdit(self.store.get_setting("server"))
        self.cfg_db = QLineEdit(self.store.get_setting("database"))
        self.cfg_auth = QComboBox()
        self.cfg_auth.addItem("Windows Authentication (read-only)", "windows")
        self.cfg_auth.addItem("Dedicated read-only SQL login", "sql_login")
        self.cfg_auth.setCurrentIndex(
            0 if self.store.get_setting("auth") == "windows" else 1
        )
        conn_form.addRow("Server / Instance", self.cfg_server)
        conn_form.addRow("Database", self.cfg_db)
        conn_form.addRow("Authentication", self.cfg_auth)
        conn_layout.addLayout(conn_form)
        conn_buttons = QHBoxLayout()
        self.save_conn_button = QPushButton("Save Settings")
        self.save_conn_button.setObjectName("primary")
        self.save_conn_button.clicked.connect(self._on_save_connection)
        self.test_conn_button = QPushButton("Test Connection")
        self.test_conn_button.clicked.connect(self._on_test_connection)
        conn_buttons.addWidget(self.save_conn_button)
        conn_buttons.addWidget(self.test_conn_button)
        conn_buttons.addStretch()
        conn_layout.addLayout(conn_buttons)
        self.test_result = QLabel("")
        self.test_result.setObjectName("hint")
        self.test_result.setWordWrap(True)
        conn_layout.addWidget(self.test_result)
        conn_layout.addStretch()
        grid.addWidget(conn_card, 0, 1)

        calc_card = QFrame()
        calc_card.setObjectName("card")
        calc_layout = QVBoxLayout(calc_card)
        calc_layout.addWidget(QLabel("Calculation Settings"))
        calc_hint = QLabel(
            "Safety stock har item ke liye ADS ke hisab se banta hai: Safety Stock = "
            "ADS × safety days. Cover days aur analysis window Reorder Suggestions "
            "tab se badalte hain."
        )
        calc_hint.setObjectName("hint")
        calc_hint.setWordWrap(True)
        calc_layout.addWidget(calc_hint)
        calc_form = QFormLayout()
        self.cfg_safety = QSpinBox()
        self.cfg_safety.setRange(0, 30)
        self.cfg_safety.setValue(self.safety_days)
        calc_form.addRow("Safety Stock (days of ADS)", self.cfg_safety)
        calc_layout.addLayout(calc_form)
        self.save_calc_button = QPushButton("Apply")
        self.save_calc_button.setObjectName("primary")
        self.save_calc_button.clicked.connect(self._on_save_calculation)
        calc_layout.addWidget(self.save_calc_button, alignment=Qt.AlignLeft)
        calc_note = QLabel(
            "Discontinued items suggestions mein nahi aate. Supplier mapping kabhi "
            "guess nahi hoti — jis item ka supplier POS mein mapped nahi, woh "
            "“Supplier not mapped” likh kar alag nazar aata hai."
        )
        calc_note.setObjectName("hint")
        calc_note.setWordWrap(True)
        calc_layout.addWidget(calc_note)
        calc_layout.addStretch()
        grid.addWidget(calc_card, 1, 0)

        backup_card = QFrame()
        backup_card.setObjectName("card")
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.addWidget(QLabel("Backup & Restore"))
        backup_hint = QLabel(
            "Assistant ki apni local data (settings, supplier mappings, overrides, "
            "audit trail) ki backup file banti hai — POS ka data is mein shaamil nahi, "
            "woh hamesha POS_DB se fresh fetch hota hai."
        )
        backup_hint.setObjectName("hint")
        backup_hint.setWordWrap(True)
        backup_layout.addWidget(backup_hint)
        backup_buttons = QHBoxLayout()
        self.backup_button = QPushButton("⬇ Download Backup")
        self.backup_button.setObjectName("primary")
        self.backup_button.clicked.connect(self._on_download_backup)
        self.restore_button = QPushButton("Restore Backup…")
        self.restore_button.clicked.connect(self._on_restore_backup)
        backup_buttons.addWidget(self.backup_button)
        backup_buttons.addWidget(self.restore_button)
        backup_buttons.addStretch()
        backup_layout.addLayout(backup_buttons)
        backup_note = QLabel(
            "Backup mein shaamil: connection settings, safety-stock setting, manual "
            "overrides (reasons ke saath), audit trail."
        )
        backup_note.setObjectName("hint")
        backup_note.setWordWrap(True)
        backup_layout.addWidget(backup_note)
        backup_layout.addStretch()
        grid.addWidget(backup_card, 1, 1)

        layout.addLayout(grid)
        audit_card = QFrame()
        audit_card.setObjectName("card")
        audit_layout = QVBoxLayout(audit_card)
        audit_layout.addWidget(QLabel("Audit Trail"))
        audit_hint = QLabel(
            "Aham tabdeelian yahan record hoti hain — manual overrides (reason ke "
            "saath), order approvals, demo data on/off, settings changes aur backups."
        )
        audit_hint.setObjectName("hint")
        audit_hint.setWordWrap(True)
        audit_layout.addWidget(audit_hint)
        self.audit_list = QListWidget()
        audit_layout.addWidget(self.audit_list)
        layout.addWidget(audit_card)
        return tab

    def _render_settings(self) -> None:
        demo = stock_service.is_demo(self.store)
        self.demo_status_text.setText(
            "ON — sample data dikh raha hai (PREVIEW)" if demo
            else "OFF — sirf live data dikhega (POS_DB connect honay ke baad)"
        )
        self.remove_demo_button.setEnabled(demo)
        self.restore_demo_button.setEnabled(not demo)
        self.cfg_safety.setValue(self.safety_days)
        self.audit_list.clear()
        entries = audit_service.list_audit(self.store)
        if not entries:
            self.audit_list.addItem(
                "Abhi koi entry nahi — override, approval ya settings change karne par "
                "yahan record ban jayega."
            )
            return
        for entry in entries:
            self.audit_list.addItem(
                f"{entry.created_at.strftime('%d %b %Y, %I:%M %p')} — {entry.text}"
            )

    def _on_save_connection(self) -> None:
        try:
            server = validate_server_address(self.cfg_server.text())
        except ValueError as exc:
            QMessageBox.warning(
                self, "Server address ghalat hai",
                f"{exc}\n\nAccepted forms: SERVER, SERVER\\INSTANCE, IP, "
                "ya SERVER,port — masalan localhost\\SQLEXPRESS.",
            )
            return
        database = self.cfg_db.text().strip()
        if not database:
            QMessageBox.warning(self, "Missing value", "Database lazmi hai.")
            return
        self.store.set_setting("server", server)
        self.store.set_setting("database", database)
        self.store.set_setting("auth", self.cfg_auth.currentData())
        audit_service.log_audit(
            self.store,
            f"POS connection settings save huein: server “{server}”, database “{database}” (read-only).",
        )
        self.refresh_all()
        self.toast("Connection settings save ho gayein — live version inhi se connect hoga.")

    def _on_test_connection(self) -> None:
        try:
            server = validate_server_address(self.cfg_server.text())
        except ValueError as exc:
            QMessageBox.warning(
                self, "Server address ghalat hai",
                f"{exc}\n\nAccepted forms: SERVER, SERVER\\INSTANCE, IP, "
                "ya SERVER,port — masalan localhost\\SQLEXPRESS.",
            )
            return
        try:
            connector = SqlServerConnector(
                server=server,
                database=self.cfg_db.text().strip(),
                auth=self.cfg_auth.currentData(),
            )
            result = connector.test_connection()
            self.test_result.setText(f"✓ {result}")
            self.toast("Connection test kamyab raha.")
        except ConnectorError as exc:
            self.test_result.setText(
                "Connection test nahi ho saka — is machine par live POS connection "
                f"maujood nahi:\n{exc}"
            )

    def _on_save_calculation(self) -> None:
        self.safety_days = self.cfg_safety.value()
        self.store.set_setting("safety_days", str(self.safety_days))
        self.draft_order_id = None
        audit_service.log_audit(
            self.store,
            f"Calculation setting tabdeel: safety stock = ADS × {self.safety_days} din. "
            "Suggestions dobara calculate huein.",
        )
        self.refresh_all()
        self.toast(f"Safety stock ab ADS × {self.safety_days} din hai — suggestions update ho gayein.")

    def _on_download_backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Assistant Backup Save Karein",
            "Pharma-Purchase-Assistant-Backup.json",
            "JSON Files (*.json)",
        )
        if not path:
            return
        self.store.backup_to_file(Path(path))
        audit_service.log_audit(
            self.store, "Assistant data ki backup file download ki gayi (settings + overrides + audit)."
        )
        self.refresh_all()
        self.toast("Backup download ho gaya — is file ko mehfooz jagah rakhein.")

    def _on_restore_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Backup File Chunein", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            self.store.restore_from_file(Path(path))
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(
                self, "Restore nahi hua", f"Ye file sahi backup nahi lagti: {exc}"
            )
            return
        self.analysis_days = self.store.get_int_setting("analysis_days", DEFAULT_ANALYSIS_DAYS)
        self.cover_days = self.store.get_int_setting("cover_days", DEFAULT_COVER_DAYS)
        self.safety_days = self.store.get_int_setting("safety_days", DEFAULT_SAFETY_DAYS)
        self.draft_order_id = None
        audit_service.log_audit(self.store, f"Backup restore ki gayi (file: {Path(path).name}).")
        self.refresh_all()
        self.toast("Backup restore ho gayi — settings aur overrides wapas lag gaye.")
