"""Tests for the read-only SQL Server connector guard."""

from __future__ import annotations

import pytest

from app.connectors.sql_server import SqlServerConnector, ensure_select_only
from app.core.errors import ConnectorError, ReadOnlyViolation


def test_select_statements_pass():
    ensure_select_only("SELECT ItemCode FROM ItemInfo")
    ensure_select_only("  select a, b from t where x = 1  ")
    ensure_select_only("-- comment\nSELECT DB_NAME() AS db")


def test_write_statements_are_rejected():
    for sql in (
        "INSERT INTO ItemInfo VALUES (1)",
        "UPDATE ItemInfo SET ItemStock = 0",
        "DELETE FROM SaleVoucher",
        "DROP TABLE ItemInfo",
        "ALTER TABLE ItemInfo ADD COLUMN X INT",
        "CREATE TABLE Foo (id INT)",
        "TRUNCATE TABLE SaleDetail",
        "EXEC sp_something",
        "SELECT * FROM ItemInfo; DELETE FROM ItemInfo",
        "",
        "   ",
    ):
        with pytest.raises(ReadOnlyViolation, match="(?i)select|allowed|empty"):
            ensure_select_only(sql)


def test_connection_string_windows_auth_has_no_password():
    connector = SqlServerConnector(server=r"localhost\SQLEXPRESS", database="POS_DB")
    text = connector.connection_string()
    assert "Trusted_Connection=yes" in text
    assert "PWD=" not in text
    assert r"localhost\SQLEXPRESS" in text
    assert "POS_DB" in text


def test_connection_string_sql_login():
    connector = SqlServerConnector(auth="sql_login", username="pos_reader", password="s3cret")
    text = connector.connection_string()
    assert "UID=pos_reader" in text
    assert "Trusted_Connection" not in text


def test_test_connection_fails_clearly_without_pyodbc():
    connector = SqlServerConnector()
    with pytest.raises(ConnectorError):
        connector.test_connection()


class StubConnector(SqlServerConnector):
    """Connector with a canned _query, so discovery logic is testable."""

    def __init__(self, canned):
        super().__init__()
        self.canned = canned
        self.seen = []

    def _query(self, sql, params=(), conn=None):
        self.seen.append(sql)
        return self.canned.pop(0)


def test_fetch_sales_discovers_quantity_column():
    connector = StubConnector([
        [{"COLUMN_NAME": "ID"}, {"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "ItemCode"},
         {"COLUMN_NAME": "Quantity"}],
        [{"COLUMN_NAME": "VoucherNo"}, {"COLUMN_NAME": "VoucherDate"}],
        [{"n": 5}],   # date probe: VoucherDate has recent rows
        [{"n": 10}],  # diag: SaleDetail rows
        [{"n": 10}],  # diag: rows joined with a voucher
        [{"n": 8}],   # diag: rows inside the 90-day window
        [{"ItemCode": "A", "Net7": 2, "Net30": 10, "Net90": 25}],
    ])
    rows = connector.fetch_sales(30)
    assert rows == [{"ItemCode": "A", "NetQty": 10}]
    assert "Quantity" in connector.seen[-1]
    assert "SaleDetail" in connector.seen[-1]


def test_fetch_sales_fails_loudly_without_quantity_column():
    connector = StubConnector([
        [{"COLUMN_NAME": "ID"}, {"COLUMN_NAME": "VoucherNo"}],
    ])
    with pytest.raises(ConnectorError, match="no usable quantity"):
        connector.fetch_sales(30)
