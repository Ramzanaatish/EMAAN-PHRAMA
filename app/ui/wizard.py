"""First-run setup wizard: pharmacy profile, POS connection, initial data.

Runs once, on first launch. The pharmacy name is prefilled as
EMAN PHARMACY & VACCINE and the connection as localhost\\SQLEXPRESS /
POS_DB (same PC as SmilePOS), so setup is a few clicks.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from ..connectors.sql_server import SqlServerConnector
from ..core.config import (
    DEFAULT_DATABASE,
    DEFAULT_SERVER,
    PHARMACY_NAME,
    validate_server_address,
)
from ..core.errors import ConnectorError
from ..services import import_service


class _ProfilePage(QWizardPage):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setTitle("Pharmacy Profile")
        self.setSubTitle("Ye naam header, reports aur setup mein nazar aayega.")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit(store.get_setting("pharmacy_name", PHARMACY_NAME))
        layout.addRow("Pharmacy name", self.name_edit)

    def validatePage(self) -> bool:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing value", "Pharmacy name lazmi hai.")
            return False
        self.store.set_setting("pharmacy_name", name)
        return True


class _ConnectionPage(QWizardPage):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setTitle("POS Connection (Read-Only)")
        self.setSubTitle(
            "Helper aur SmilePOS aik hi PC par chalte hain — is liye server "
            "localhost hai aur Windows Authentication se connect hota hai. "
            "Helper sirf parhta hai; POS_DB mein kabhi kuch nahi likhta."
        )
        layout = QFormLayout(self)
        self.server_edit = QLineEdit(store.get_setting("server", DEFAULT_SERVER))
        self.db_edit = QLineEdit(store.get_setting("database", DEFAULT_DATABASE))
        self.auth_combo = QComboBox()
        self.auth_combo.addItem("Windows Authentication (read-only)", "windows")
        self.auth_combo.addItem("Dedicated read-only SQL login", "sql_login")
        self.auth_combo.setCurrentIndex(
            0 if store.get_setting("auth", "windows") == "windows" else 1
        )
        layout.addRow("Server / Instance", self.server_edit)
        layout.addRow("Database", self.db_edit)
        layout.addRow("Authentication", self.auth_combo)
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._test_connection)
        self.test_label = QLabel("")
        self.test_label.setWordWrap(True)
        layout.addRow(self.test_button)
        layout.addRow(self.test_label)

    def _test_connection(self):
        try:
            server = validate_server_address(self.server_edit.text())
        except ValueError as exc:
            self.test_label.setText(f"{exc}")
            return
        try:
            connector = SqlServerConnector(
                server=server,
                database=self.db_edit.text().strip(),
                auth=self.auth_combo.currentData(),
            )
            self.test_label.setText("✓ " + connector.test_connection())
        except ConnectorError as exc:
            self.test_label.setText(f"Connection fail hua: {exc}")

    def validatePage(self) -> bool:
        try:
            server = validate_server_address(self.server_edit.text())
        except ValueError as exc:
            QMessageBox.warning(
                self, "Server address ghalat hai",
                f"{exc}\n\nAccepted forms: SERVER, SERVER\\INSTANCE, IP, "
                "ya SERVER,port — masalan localhost\\SQLEXPRESS.",
            )
            return False
        database = self.db_edit.text().strip()
        if not database:
            QMessageBox.warning(self, "Missing value", "Database lazmi hai.")
            return False
        self.store.set_setting("server", server)
        self.store.set_setting("database", database)
        self.store.set_setting("auth", self.auth_combo.currentData())
        return True


class _DataPage(QWizardPage):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setTitle("Initial Data")
        self.setSubTitle(
            "Pehli dafa demo (sample) data dikhaya jata hai taake screens dekhi "
            "ja sakein. Jab live fetch ho jaye ga, demo data hata dein — phir "
            "sirf real data nazar aayega."
        )
        layout = QVBoxLayout(self)
        self.demo_check = QCheckBox("Demo (sample) data dikhayein (PREVIEW label ke saath)")
        self.demo_check.setChecked(True)
        layout.addWidget(self.demo_check)
        layout.addWidget(QLabel(
            "Live data fetch: Settings mein “Refresh Data” dabayein, ya scheduled "
            "refresh ka intezar karein. Refresh POS_DB se read-only data import "
            "karta hai."
        ))


class SetupWizard(QWizard):
    """Three-page first-run wizard; returns True when setup is complete."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Pharma Purchase Assistant — Setup")
        self.setWizardStyle(QWizard.ModernStyle)
        self.profile_page = _ProfilePage(store)
        self.connection_page = _ConnectionPage(store)
        self.data_page = _DataPage(store)
        self.addPage(self.profile_page)
        self.addPage(self.connection_page)
        self.addPage(self.data_page)

    def accept(self):
        if self.data_page.demo_check.isChecked():
            import_service.enable_demo(self.store)
        else:
            self.store.set_setting("demo_data", "off")
        self.store.set_setting("setup_done", "on")
        super().accept()
