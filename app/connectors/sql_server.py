"""Read-only SQL Server connector (pyodbc).

Connects to the SmilePOS database on the same Windows PC and only ever
issues SELECT statements. Any statement that is not a plain SELECT is
rejected before it reaches the server, so the assistant cannot write to,
edit or delete POS records even by mistake.

The exact SaleDetail/PurchaseDetail column names were not part of the
verified schema, so the connector inspects INFORMATION_SCHEMA first and
only then builds its aggregation queries from the columns that actually
exist. If a needed column is missing, the import fails loudly with the
real column list instead of guessing.
"""

from __future__ import annotations

import re

from ..core.errors import ConnectorError, ReadOnlyViolation

try:
    import pyodbc
except ImportError:  # pyodbc needs the ODBC driver manager (Windows: built in)
    pyodbc = None  # type: ignore[assignment]

from .base import PosConnector

# Column names verified live on 2026-11-18 (sqlcmd + fresh backup analysis).
VERIFIED_TABLES = (
    "ItemInfo",
    "SaleVoucher",
    "SaleDetail",
    "PurchaseVoucher",
    "PurchaseDetail",
    "ItemStock",
    "SaleExpiryItems",
    "AccountInfo",
    "StockAdjustment",
    "OpeningStock",
)

PRODUCT_COLUMNS = (
    "ItemCode",
    "ItemName",
    "ItemStock",
    "ReOrderLevel",
    "MaxLevel",
    "VendorCode",
    "Manufacturer",
    "ItemGroup",
)

# Candidate names for the columns the schema did not pin down yet. The
# connector tries them in order against INFORMATION_SCHEMA and uses the
# first one that exists; nothing is assumed.
QUANTITY_CANDIDATES = ("Qty", "Quantity", "SaleQty", "SoldQty", "NetQty")
ITEM_CANDIDATES = ("ItemCode", "Item_Code", "Code")
RATE_CANDIDATES = ("Rate", "SaleRate", "Price", "UnitRate")
BATCH_CANDIDATES = ("BatchNo", "Batch", "BatchNumber")
EXPIRY_CANDIDATES = ("ExpiryDate", "ExpDate", "Expiry")


def ensure_select_only(sql: str) -> None:
    """Reject anything that is not a single plain SELECT statement."""
    cleaned = re.sub(r"--[^\n]*", " ", sql)
    cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.S)
    cleaned = cleaned.strip()
    if not cleaned:
        raise ReadOnlyViolation("Empty statement is not allowed.")
    if ";" in cleaned.rstrip(";"):
        raise ReadOnlyViolation("Multiple statements are not allowed.")
    first = cleaned.split(None, 1)[0].upper()
    if first != "SELECT":
        raise ReadOnlyViolation(
            f"Only SELECT statements are allowed, got {first!r}. "
            "The assistant never writes to POS_DB."
        )
    forbidden = ("INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "CREATE",
                 "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE")
    tokens = re.findall(r"[A-Za-z_]+", cleaned.upper())
    for token in tokens:
        if token in forbidden:
            raise ReadOnlyViolation(
                f"Forbidden keyword {token!r} in a read-only query."
            )


class SqlServerConnector(PosConnector):
    """pyodbc connector to POS_DB on localhost\\SQLEXPRESS."""

    def __init__(
        self,
        server: str = r"localhost\SQLEXPRESS",
        database: str = "POS_DB",
        auth: str = "windows",
        username: str = "",
        password: str = "",
        driver: str = "ODBC Driver 17 for SQL Server",
        timeout: int = 10,
    ):
        self.server = server
        self.database = database
        self.auth = auth
        self.username = username
        self.password = password
        self.driver = driver
        self.timeout = timeout

    def connection_string(self) -> str:
        """ODBC connection string. Passwords are never logged or stored."""
        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={self.server}",
            f"DATABASE={self.database}",
            f"Connection Timeout={self.timeout}",
        ]
        if self.auth == "windows":
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={self.username}")
            parts.append(f"PWD={self.password}")
        return ";".join(parts) + ";"

    def _connect(self):
        if pyodbc is None:
            raise ConnectorError(
                "pyodbc is not available on this machine. On the Windows PC "
                "install the Microsoft ODBC Driver for SQL Server and "
                "reinstall the assistant's requirements."
            )
        return pyodbc.connect(self.connection_string(), timeout=self.timeout)

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        ensure_select_only(sql)
        try:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(sql, params)
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except ReadOnlyViolation:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as ConnectorError
            raise ConnectorError(f"POS query failed: {exc}") from exc

    def test_connection(self) -> str:
        rows = self._query("SELECT DB_NAME() AS db, @@VERSION AS version")
        version = (rows[0]["version"] or "").split("\n")[0].strip() if rows else ""
        return f"Connected to {self.database} on {self.server} ({version})"

    def list_columns(self, table_name: str) -> list[str]:
        rows = self._query(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (table_name,),
        )
        return [row["COLUMN_NAME"] for row in rows]

    def inspect_schema(self) -> dict[str, list[str]]:
        """Actual columns of every verified table/view (no guessing)."""
        return {table: self.list_columns(table) for table in VERIFIED_TABLES}

    def fetch_products(self) -> list[dict]:
        columns = ", ".join(f"[{name}]" for name in PRODUCT_COLUMNS)
        return self._query(f"SELECT {columns} FROM [dbo].[ItemInfo]")

    def fetch_stock(self) -> list[dict]:
        """Current stock from the ItemStock view (InQty - OutQty per item).

        Discovers the view's real columns first; the view's item-code
        column name was not part of the verified schema.
        """
        columns = self.list_columns("ItemStock")
        item = next((c for c in ITEM_CANDIDATES if c in columns), None)
        in_qty = "InQty" if "InQty" in columns else None
        out_qty = "OutQty" if "OutQty" in columns else None
        if item is None or in_qty is None or out_qty is None:
            raise ConnectorError(
                "ItemStock view has no usable item/InQty/OutQty columns. "
                f"Actual columns: {', '.join(columns)}"
            )
        return self._query(
            f"SELECT [{item}] AS ItemCode, [{in_qty}] AS InQty, "
            f"[{out_qty}] AS OutQty FROM [dbo].[ItemStock]"
        )

    def fetch_sales(self, days: int) -> list[dict]:
        """Net sales per item over the last `days` days.

        Discovers the real SaleDetail quantity/item columns first, then
        aggregates SaleDetail joined to SaleVoucher for the date window.
        """
        detail_columns = self.list_columns("SaleDetail")
        qty = next((c for c in QUANTITY_CANDIDATES if c in detail_columns), None)
        item = next((c for c in ITEM_CANDIDATES if c in detail_columns), None)
        if qty is None or item is None:
            raise ConnectorError(
                "SaleDetail has no usable quantity/item columns. "
                f"Actual columns: {', '.join(detail_columns)}"
            )
        return self._query(
            "SELECT d.["
            + item
            + "] AS ItemCode, SUM(d.["
            + qty
            + "]) AS NetQty "
            "FROM [dbo].[SaleDetail] d "
            "INNER JOIN [dbo].[SaleVoucher] v ON v.[VoucherNo] = d.[VoucherNo] "
            "WHERE v.[VoucherDate] >= DATEADD(day, ?, CAST(GETDATE() AS date)) "
            "GROUP BY d.["
            + item
            + "]",
            (-days,),
        )

    def fetch_suppliers(self) -> list[dict]:
        """Supplier code + name from AccountInfo (VendorCode points here).

        Discovers the real name column first instead of assuming it.
        """
        columns = self.list_columns("AccountInfo")
        code = next(
            (c for c in ("AccountCode", "Code", "VendorCode") if c in columns), None
        )
        name = next(
            (
                c
                for c in ("AccountName", "AccountTitle", "Name", "Title", "SupplierName")
                if c in columns
            ),
            None,
        )
        if code is None or name is None:
            raise ConnectorError(
                "AccountInfo has no usable code/name columns. "
                f"Actual columns: {', '.join(columns)}"
            )
        return self._query(
            f"SELECT [{code}] AS AccountCode, [{name}] AS AccountName "
            "FROM [dbo].[AccountInfo]"
        )
