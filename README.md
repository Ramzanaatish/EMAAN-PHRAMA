# Pharma Purchase Assistant

Windows desktop app (Python + PySide6) for pharmacy stock intelligence and
purchase planning. Pharmacy: **EMAN PHARMACY & VACCINE**.

The app reads the existing SmilePOS database (**POS_DB** on
`localhost\SQLEXPRESS`, same Windows PC) **read-only** and answers one
question reliably: **what needs to be purchased, how much, and from which
supplier?**

## Formula (shown plainly in the app, with a per-item breakdown)

```
ADS = Net Sales ÷ Analysis Days
Target Stock = (ADS × Cover Days) + Safety Stock
Suggested Purchase = max(0, Target Stock − Usable Stock − Confirmed Incoming)
```

- Cover days: **7 / 14 / 21 / 30** (default 21). Sales views: 7 / 30 / 90 days.
- Safety stock: ADS × safety days (default 5, changeable in Settings).
- Net sales exclude returns and cancelled sales. Usable stock excludes
  expired/damaged quantities. Manual quantity overrides require a written
  reason and are recorded in the audit trail. No order is ever placed
  automatically — a supplier-wise draft is built, reviewed and approved.

## V1 scope (Final Recommendation)

1. POS read-only integration (pyodbc, SELECT-only guard, Windows auth)
2. Product & supplier data (never guesses a supplier mapping)
3. Overview dashboard (KPIs, most-demanding, needs-attention, near-expiry)
4. Stock & sales analysis (7/30/90-day views)
5. Smart reorder suggestions (formula + overrides + audit)
6. Supplier-wise purchase order draft (PDF/HTML export, approve flow)
7. Daily report — genuine PDF (ReportLab) + Excel (openpyxl) + HTML
8. Settings, backup & audit (JSON backup/restore, audit trail)

Demo data: the 18 sample medicines from the HTML preview, labelled
PREVIEW. A Demo Data switch removes them; after a live fetch only live
data is shown. Goods receiving, invoice matching, PO lifecycle tracking,
cloud/multi-branch, licensing and AI features are V2 (listed in the app
as planned-only).

## Project layout (blueprint section 7)

```
run.py                  Launch: python run.py
requirements.txt
run_instruction.md      Exact Windows run steps
app/
  main.py               Qt entry point
  bootstrap.py          Logging + store creation
  core/                 config, purchase formula, errors
  database/             SQLAlchemy models, SQLite store, demo seed
  connectors/           base interface + read-only SQL Server (pyodbc)
  services/             import/refresh, stock, purchase, orders, reports, audit
  ui/                   styles, widgets, main window (5 tabs), setup wizard
tests/                  pytest (formula, demo data, connector guard, store,
                        purchase service, reports, headless UI smoke)
installer/              Inno Setup script
```

## Run

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
.venv\Scripts\python -m pytest tests\ -q
.venv\Scripts\python run.py
```

See `run_instruction.md` for the full Windows steps, including the
first-run wizard and the live-connection check.

## Verified schema (live, 2026-11-18)

Server `DESKTOP-SJO68CG\SQLEXPRESS` (SQL Server 2017 Express), database
`POS_DB`, last sale 2026-11-18, 5,021 sale vouchers. ItemInfo columns:
ItemCode, ItemName, ItemStock, ReOrderLevel, MaxLevel, VendorCode,
Manufacturer, ItemGroup. SaleVoucher: VoucherNo, VoucherDate. Views:
ItemStock (InQty/OutQty), JournalEntries. Suppliers seen in real data:
Premier Agencies, Aslam Traders, Madina Medicine Co.

## Troubleshooting — POS connection (v1.2.0)

The app only reads POS_DB (SELECT). When Refresh or Test Connection
fails, the message now names the cause and the check:

| Message says | Check on the PC |
|---|---|
| ODBC Driver … installed nahi hai | Install **Microsoft ODBC Driver 18 for SQL Server** (free, Microsoft site), then retry. The app picks the newest installed driver itself. |
| SQL Server (…) nahi mil raha | 1) **SQL Server (SQLEXPRESS)** service running? (services.msc) 2) **SQL Server Browser** service running? (named instance isi se milta hai) 3) SQL Server Configuration Manager → TCP/IP **Enabled**? |
| Login fail hua | SmilePOS jis Windows user se chalta hai usi se assistant chalaien, ya Settings mein dedicated read-only SQL login lagayein. |
| Database '…' nahi mili | Settings → Database ka naam check karein (aam tor par `POS_DB`). |
| Connection timeout | Server ka naam mil gaya lekin jawab nahi — Browser/TCP check karein, ya server `localhost,1433` try karein. |

Notes: a refresh uses **one** ODBC connection for all queries, so a
slow Browser no longer multiplies the wait. The window stays
responsive during a refresh (worker thread). All Stock / Reorder
tables show at most 200 rows at a time (most urgent first); the full
count is in the summary line.
