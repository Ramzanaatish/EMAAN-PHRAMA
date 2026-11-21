"""Read-only SQL Server connector (pyodbc).

Connects to the SmilePOS database on the same Windows PC and only ever
issues SELECT statements. Any statement that is not a plain SELECT is
rejected before it reaches the server, so the assistant cannot write to,
edit or delete POS records even by mistake.

v1.2.0 fixes (the "POS data nahi aata / app hang hoti hai" faults):

1. One connection per refresh. The old code opened a NEW ODBC connection
   for every single query (11 connections per refresh: each list_columns
   + each fetch). Every connect re-resolves the named instance through
   the SQL Server Browser, so a slow or stopped Browser made the whole
   refresh hang for minutes. Now `session()` opens ONE connection and
   every fetch in a refresh reuses it, and the column cache lives for
   that session only.
2. Driver auto-detection. The driver was hardcoded to "ODBC Driver 17
   for SQL Server", so a PC with only Driver 18 (or no driver at all)
   failed every query. Now the newest installed driver is picked
   (18 -> 17 -> 13 -> "SQL Server"), and Driver 18 gets
   TrustServerCertificate=yes (its encryption default breaks self-signed
   SQLEXPRESS certificates otherwise).
3. fetch_products discovers ItemInfo columns first (like the other
   fetches already did). One missing column used to kill the whole
   import with zero data.
4. One sales query instead of three. fetch_sales_all() aggregates the
   7/30/90-day windows in a single GROUP BY with conditional SUMs.
5. Plain-language errors. A failed connect used to surface raw pyodbc
   text. Now the common failures name the actual cause and the exact
   thing to check on the PC (driver, SQL Server service, SQL Server
   Browser, TCP/IP, database name, login).

The exact SaleDetail/PurchaseDetail column names were not part of the
verified schema, so the connector inspects INFORMATION_SCHEMA first and
only then builds its aggregation queries from the columns that actually
exist. If a needed column is missing, the import fails loudly with the
real column list instead of guessing.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

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

# Newest first. Driver 18 is preferred when installed; it encrypts by
# default, so its connection string also trusts the server certificate
# (SQLEXPRESS uses a self-signed one).
DRIVER_CANDIDATES = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server",
)
DRIVER_FALLBACK = "ODBC Driver 17 for SQL Server"

# One query, three windows. The old code ran fetch_sales(30), (7) and
# (90) as three separate aggregations, each re-discovering the columns.
SALES_WINDOWS = (7, 30, 90)


def detect_driver() -> str | None:
    """Newest installed SQL Server ODBC driver, or None when pyodbc or
    every driver is missing."""
    if pyodbc is None:
        return None
    try:
        installed = pyodbc.drivers()
    except Exception:  # noqa: BLE001 - driver listing is best-effort
        return None
    for candidate in DRIVER_CANDIDATES:
        if candidate in installed:
            return candidate
    return None


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
        driver: str | None = None,
        timeout: int = 10,
    ):
        self.server = server
        self.database = database
        self.auth = auth
        self.username = username
        self.password = password
        # None = auto-detect at connect time (newest installed driver).
        # An explicit driver is used as-is.
        self.driver = driver
        self.timeout = timeout
        self._columns_cache: dict[str, list[str]] = {}

    def resolved_driver(self) -> str:
        """Driver this connector will use (detected, explicit, fallback)."""
        if self.driver:
            return self.driver
        return detect_driver() or DRIVER_FALLBACK

    def connection_string(self) -> str:
        """ODBC connection string. Passwords are never logged or stored."""
        driver = self.resolved_driver()
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={self.server}",
            f"DATABASE={self.database}",
            f"Connection Timeout={self.timeout}",
        ]
        if driver.startswith("ODBC Driver 18"):
            # Driver 18 encrypts by default; SQLEXPRESS uses a self-signed
            # certificate, so without this the handshake fails.
            parts.append("Encrypt=yes")
            parts.append("TrustServerCertificate=yes")
        if self.auth == "windows":
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={self.username}")
            parts.append(f"PWD={self.password}")
        return ";".join(parts) + ";"

    def _friendly_error(self, exc: Exception) -> ConnectorError:
        """Map the usual pyodbc failures to the cause + the exact check
        on the PC, instead of raw driver text the user cannot act on."""
        text = str(exc)
        low = text.lower()
        if pyodbc is None:
            return ConnectorError(
                "pyodbc is not available on this machine. On the Windows PC "
                "install the Microsoft ODBC Driver for SQL Server and "
                "reinstall the assistant's requirements."
            )
        if (
            "im002" in low
            or "data source name not found" in low
            or "driver" in low and "not found" in low
            or "can't open lib" in low
        ):
            return ConnectorError(
                "ODBC Driver for SQL Server is PC par installed nahi hai. "
                "Microsoft ODBC Driver 18 for SQL Server install karein "
                "(Microsoft ki site se free download), phir dobara try karein."
            )
        if (
            "08001" in text
            or "error locating server" in low
            or "named pipes provider" in low
            or "sql server network interfaces" in low
        ):
            return ConnectorError(
                f"SQL Server ({self.server}) nahi mil raha. PC par check karein: "
                "1) SQL Server (SQLEXPRESS) service chal rahi hai? "
                "(services.msc khol kar dekhein) "
                "2) SQL Server Browser service chal rahi hai? (named instance "
                "isi se milta hai) "
                "3) SQL Server Configuration Manager mein TCP/IP Enabled hai? "
                "Koi ek band ho to connection kabhi nahi banay ga."
            )
        if "28000" in text or "login failed" in low:
            return ConnectorError(
                "Login fail hua — is Windows user ko POS_DB par read access "
                "nahi hai, ya SQL login ghalat hai. SmilePOS jis user se "
                "chalta hai usi se assistant chalaien, ya Settings mein "
                "dedicated read-only SQL login lagayein."
            )
        if "08004" in text or "cannot open database" in low:
            return ConnectorError(
                f"Database '{self.database}' is server par nahi mili. "
                "Settings mein database ka naam check karein (SmilePOS ka "
                "database aam tor par POS_DB hota hai)."
            )
        if "hyt00" in text or "timeout" in low:
            return ConnectorError(
                "Connection timeout — server ka naam mil gaya lekin jawab "
                "nahi aaya. SQL Server Browser service aur TCP/IP check "
                "karein, ya server ka naam badal kar 'localhost,1433' "
                "try karein."
            )
        return ConnectorError(f"POS query failed: {exc}")

    def _connect(self):
        if pyodbc is None:
            raise ConnectorError(
                "pyodbc is not available on this machine. On the Windows PC "
                "install the Microsoft ODBC Driver for SQL Server and "
                "reinstall the assistant's requirements."
            )
        try:
            return pyodbc.connect(self.connection_string(), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - mapped to a plain cause
            raise self._friendly_error(exc) from exc

    @contextmanager
    def session(self):
        """One shared connection for a whole refresh.

        Usage: `with connector.session() as conn:` then pass conn=conn to
        every fetch. The column cache lives for this session only.
        """
        connection = self._connect()
        self._columns_cache = {}
        try:
            yield connection
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - close is best-effort
                pass
            self._columns_cache = {}

    def _query(self, sql: str, params: tuple = (), conn=None) -> list[dict]:
        ensure_select_only(sql)
        try:
            if conn is not None:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(sql, params)
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except ReadOnlyViolation:
            raise
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as ConnectorError
            raise self._friendly_error(exc) from exc

    def test_connection(self) -> str:
        rows = self._query("SELECT DB_NAME() AS db, @@VERSION AS version")
        version = (rows[0]["version"] or "").split("\n")[0].strip() if rows else ""
        return f"Connected to {self.database} on {self.server} ({version})"

    def list_columns(self, table_name: str, conn=None) -> list[str]:
        # Only cache inside a session (one refresh): a stale cache across
        # separate refreshes would hide schema changes.
        if conn is not None and table_name in self._columns_cache:
            return self._columns_cache[table_name]
        rows = self._query(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            (table_name,),
            conn=conn,
        )
        columns = [row["COLUMN_NAME"] for row in rows]
        if conn is not None:
            self._columns_cache[table_name] = columns
        return columns

    def inspect_schema(self) -> dict[str, list[str]]:
        """Actual columns of every verified table/view (no guessing)."""
        with self.session() as conn:
            return {table: self.list_columns(table, conn=conn) for table in VERIFIED_TABLES}

    def fetch_products(self, conn=None) -> list[dict]:
        """All ItemInfo rows, selecting only the columns that exist.

        A missing column used to fail the whole import with zero data;
        now it is skipped and the import continues with the rest.
        """
        columns = self.list_columns("ItemInfo", conn=conn)
        available = [name for name in PRODUCT_COLUMNS if name in columns]
        if "ItemCode" not in available or "ItemName" not in available:
            raise ConnectorError(
                "ItemInfo mein ItemCode/ItemName nahi milay. "
                f"Actual columns: {', '.join(columns)}"
            )
        selected = ", ".join(f"[{name}]" for name in available)
        rows = self._query(f"SELECT {selected} FROM [dbo].[ItemInfo]", conn=conn)
        # Normalise: callers read every PRODUCT_COLUMNS key.
        for row in rows:
            for name in PRODUCT_COLUMNS:
                row.setdefault(name, None)
        return rows

    def fetch_stock(self, conn=None) -> list[dict]:
        """Current stock from the ItemStock view (InQty - OutQty per item).

        Discovers the view's real columns first; the view's item-code
        column name was not part of the verified schema.
        """
        columns = self.list_columns("ItemStock", conn=conn)
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
            f"[{out_qty}] AS OutQty FROM [dbo].[ItemStock]",
            conn=conn,
        )

    def fetch_sales_all(self, conn=None) -> list[dict]:
        """Net sales per item for the 7/30/90-day windows in ONE query.

        One GROUP BY with conditional SUMs, instead of three separate
        aggregations that each re-discovered the columns.
        """
        detail_columns = self.list_columns("SaleDetail", conn=conn)
        qty = next((c for c in QUANTITY_CANDIDATES if c in detail_columns), None)
        item = next((c for c in ITEM_CANDIDATES if c in detail_columns), None)
        if qty is None or item is None:
            raise ConnectorError(
                "SaleDetail has no usable quantity/item columns. "
                f"Actual columns: {', '.join(detail_columns)}"
            )
        voucher_columns = self.list_columns("SaleVoucher", conn=conn)
        if "VoucherNo" not in voucher_columns or "VoucherDate" not in voucher_columns:
            raise ConnectorError(
                "SaleVoucher mein VoucherNo/VoucherDate nahi milay. "
                f"Actual columns: {', '.join(voucher_columns)}"
            )
        cases = ", ".join(
            "ISNULL(SUM(CASE WHEN v.[VoucherDate] >= DATEADD(day, -{days}, "
            "CAST(GETDATE() AS date)) THEN d.[{qty}] ELSE 0 END), 0) AS Net{days}".format(
                days=days, qty=qty
            )
            for days in SALES_WINDOWS
        )
        return self._query(
            "SELECT d.["
            + item
            + "] AS ItemCode, "
            + cases
            + " FROM [dbo].[SaleDetail] d "
            "INNER JOIN [dbo].[SaleVoucher] v ON v.[VoucherNo] = d.[VoucherNo] "
            "GROUP BY d.["
            + item
            + "]",
            conn=conn,
        )

    def fetch_sales(self, days: int, conn=None) -> list[dict]:
        """Net sales per item over the last `days` days.

        Thin wrapper over fetch_sales_all; kept for callers and tests
        that ask for one window.
        """
        key = {7: "Net7", 30: "Net30", 90: "Net90"}.get(days, "Net30")
        rows = self.fetch_sales_all(conn=conn)
        return [
            {
                "ItemCode": row["ItemCode"],
                "NetQty": int(
                    row.get(key)
                    if row.get(key) is not None
                    else row.get("NetQty", 0) or 0
                ),
            }
            for row in rows
        ]

    def fetch_suppliers(self, conn=None) -> list[dict]:
        """Supplier code + name from AccountInfo (VendorCode points here).

        Discovers the real name column first instead of assuming it.
        """
        columns = self.list_columns("AccountInfo", conn=conn)
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
            "FROM [dbo].[AccountInfo]",
            conn=conn,
        )
