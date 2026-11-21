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

# Sales date column: SmilePOS does not pin the date column name down,
# and a column that merely EXISTS may hold no usable dates (v1.3.0
# showed net sales 0 for every item although vouchers exist). The
# connector probes each candidate for rows inside the last 90 days and
# uses the first one that actually has data; VoucherDate stays the
# fallback so behaviour never changes when it is the real column.
DATE_CANDIDATES = (
    "VoucherDate",
    "Date",
    "SaleDate",
    "VchDate",
    "Voucher_Date",
    "EntryDate",
    "CreatedDate",
)


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
        # Diagnostics from the last sales / stock-entry fetch (counts
        # only, never item data) — read by the import for the server log.
        self.last_sales_diag: dict | None = None
        self.last_stock_entry_diag: dict | None = None

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

    def _count(self, sql: str, conn=None) -> int:
        """Single COUNT(*) query, as an int (0 when the result is empty)."""
        rows = self._query(sql, conn=conn)
        return int(rows[0]["n"]) if rows else 0

    def _sale_date_expr(self, column: str) -> str:
        """A date expression that also parses dd/mm/yyyy strings.

        SmilePOS date columns are usually real dates (the style is then
        ignored), but a varchar date in dd/mm/yyyy form only parses with
        style 103. TRY_CONVERT returns NULL instead of failing, so an
        unparseable value simply does not count. The voucher alias `v`
        is used because every caller joins SaleVoucher as `v`.
        """
        return (
            f"COALESCE(TRY_CONVERT(date, v.[{column}]), "
            f"TRY_CONVERT(date, v.[{column}], 103))"
        )

    def _recent_joined_count(self, column: str, days: int, conn=None) -> int:
        """SaleDetail rows whose voucher date falls in the last `days` days.

        v1.3.3: the probe counts JOINED detail rows, not vouchers alone.
        A date column can hold recent vouchers while the VoucherNo join
        drops every detail row (format/type mismatch) — counting vouchers
        would then pick a column whose sales still come back 0. Counting
        the join proves the whole pipeline (join + date parse + window).
        """
        return self._count(
            "SELECT COUNT(*) AS n FROM [dbo].[SaleDetail] d "
            "INNER JOIN [dbo].[SaleVoucher] v "
            "ON v.[VoucherNo] = d.[VoucherNo] "
            "WHERE {expr} >= DATEADD(day, -{days}, "
            "CAST(GETDATE() AS date))".format(
                expr=self._sale_date_expr(column), days=days
            ),
            conn=conn,
        )

    def _pick_sales_date_column(self, voucher_columns, conn=None):
        """First date column with actual JOINED sales in the last 90 days.

        Falls back to VoucherDate when no candidate has recent data, so
        a database with genuinely no recent sales behaves exactly as
        before (all windows 0) instead of failing. Returns None when
        no date column exists at all.
        """
        present = [c for c in DATE_CANDIDATES if c in voucher_columns]
        for column in present:
            try:
                if self._recent_joined_count(column, 90, conn=conn) > 0:
                    return column
            except Exception:  # noqa: BLE001 - probe is best-effort
                continue
        if "VoucherDate" in voucher_columns:
            return "VoucherDate"
        return present[0] if present else None

    def fetch_sales_all(self, conn=None) -> list[dict]:
        """Net sales per item for the 7/30/90-day windows in ONE query.

        One GROUP BY with conditional SUMs, instead of three separate
        aggregations that each re-discovered the columns.

        v1.3.3: the probe counts JOINED detail rows (not vouchers alone)
        and dates parse with a dd/mm/yyyy fallback (style 103), so a
        column with recent vouchers but a broken join, or varchar dates,
        no longer silently yields 0. The query also returns each item's
        last sale date (MAX over all vouchers, not just 90 days) — the
        "most recently out of stock first" sort signal. Counts land in
        self.last_sales_diag (detail rows, joined rows, rows in the
        90-day window, items with sales, items with a last-sale date)
        for the server log.
        """
        detail_columns = self.list_columns("SaleDetail", conn=conn)
        qty = next((c for c in QUANTITY_CANDIDATES if c in detail_columns), None)
        item = next((c for c in ITEM_CANDIDATES if c in detail_columns), None)
        if qty is None or item is None:
            raise ConnectorError(
                "SaleDetail has no usable quantity/item columns. "
                f"Actual columns: {', '.join(detail_columns)}"
            )
        if "VoucherNo" not in detail_columns:
            raise ConnectorError(
                "SaleDetail mein VoucherNo nahi mila — sale ko voucher se "
                f"jora nahi ja sakta. Actual columns: {', '.join(detail_columns)}"
            )
        voucher_columns = self.list_columns("SaleVoucher", conn=conn)
        if "VoucherNo" not in voucher_columns:
            raise ConnectorError(
                "SaleVoucher mein VoucherNo nahi mila. "
                f"Actual columns: {', '.join(voucher_columns)}"
            )
        date_column = self._pick_sales_date_column(voucher_columns, conn=conn)
        if date_column is None:
            raise ConnectorError(
                "SaleVoucher mein koi tareekh (date) column nahi mila. "
                f"Actual columns: {', '.join(voucher_columns)}"
            )
        diag = {
            "date_column": date_column,
            "qty_column": qty,
            "item_column": item,
            "detail_rows": None,
            "joined_rows": None,
            "in_window_90d": None,
            "items_with_sales": 0,
            "items_with_last_sale": 0,
        }
        self.last_sales_diag = diag
        date_expr = self._sale_date_expr(date_column)
        try:
            diag["detail_rows"] = self._count(
                "SELECT COUNT(*) AS n FROM [dbo].[SaleDetail]", conn=conn
            )
        except Exception:  # noqa: BLE001 - diagnostics are best-effort
            pass
        try:
            diag["joined_rows"] = self._count(
                "SELECT COUNT(*) AS n FROM [dbo].[SaleDetail] d "
                "INNER JOIN [dbo].[SaleVoucher] v "
                "ON v.[VoucherNo] = d.[VoucherNo]",
                conn=conn,
            )
        except Exception:  # noqa: BLE001 - diagnostics are best-effort
            pass
        try:
            diag["in_window_90d"] = self._count(
                "SELECT COUNT(*) AS n FROM [dbo].[SaleDetail] d "
                "INNER JOIN [dbo].[SaleVoucher] v "
                "ON v.[VoucherNo] = d.[VoucherNo] "
                "WHERE {expr} >= DATEADD(day, -90, "
                "CAST(GETDATE() AS date))".format(expr=date_expr),
                conn=conn,
            )
        except Exception:  # noqa: BLE001 - diagnostics are best-effort
            pass
        cases = ", ".join(
            "ISNULL(SUM(CASE WHEN {expr} >= "
            "DATEADD(day, -{days}, CAST(GETDATE() AS date)) "
            "THEN d.[{qty}] ELSE 0 END), 0) AS Net{days}".format(
                days=days, qty=qty, expr=date_expr
            )
            for days in SALES_WINDOWS
        )
        rows = self._query(
            "SELECT d.["
            + item
            + "] AS ItemCode, "
            + cases
            + ", MAX({expr}) AS LastSale".format(expr=date_expr)
            + " FROM [dbo].[SaleDetail] d "
            "INNER JOIN [dbo].[SaleVoucher] v ON v.[VoucherNo] = d.[VoucherNo] "
            "GROUP BY d.["
            + item
            + "]",
            conn=conn,
        )
        diag["items_with_sales"] = sum(
            1 for row in rows if int(row.get("Net30") or 0) > 0
        )
        diag["items_with_last_sale"] = sum(
            1 for row in rows if row.get("LastSale")
        )
        return rows

    def fetch_stock_entries(self, conn=None) -> dict[str, int]:
        """{ItemCode: entry_count} — purchase lines + opening-stock rows.

        v1.3.1: "stock entry" = the medicine was actually stocked at
        least once: a PurchaseDetail line (purchase / goods received)
        or an OpeningStock row. A missing table or item column
        contributes 0 and never fails the refresh; the breakdown lands
        in self.last_stock_entry_diag for the server log.
        """
        entries: dict[str, int] = {}
        diag = {
            "purchase_items": 0,
            "opening_items": 0,
            "purchase_rows": 0,
            "opening_rows": 0,
            "items_with_entry": 0,
        }
        self.last_stock_entry_diag = diag
        for table, key in (("PurchaseDetail", "purchase"), ("OpeningStock", "opening")):
            try:
                columns = self.list_columns(table, conn=conn)
            except Exception:  # noqa: BLE001 - a missing table gives 0
                continue
            item = next((c for c in ITEM_CANDIDATES if c in columns), None)
            if item is None:
                continue
            try:
                rows = self._query(
                    "SELECT [{item}] AS ItemCode, COUNT(*) AS EntryCount "
                    "FROM [dbo].[{table}] GROUP BY [{item}]".format(
                        item=item, table=table
                    ),
                    conn=conn,
                )
            except Exception:  # noqa: BLE001 - a bad table gives 0
                continue
            codes = 0
            total = 0
            for row in rows:
                code = row.get("ItemCode")
                if code is None:
                    continue
                count = int(row.get("EntryCount") or 0)
                entries[str(code)] = entries.get(str(code), 0) + count
                codes += 1
                total += count
            diag[key + "_items"] = codes
            diag[key + "_rows"] = total
        diag["items_with_entry"] = len(entries)
        return entries

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
