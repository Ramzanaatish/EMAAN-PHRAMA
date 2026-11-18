# Pharma Purchase Assistant — Run Instructions (Windows PC)

Pharmacy: **EMAN PHARMACY & VACCINE**. The helper and SmilePOS run on the
**same Windows PC**. The helper only reads POS_DB (read-only); it never
writes to it.

## 1. Prerequisites (install once)

1. **Python 3.12** (python.org → Downloads → Windows installer). Tick
   **"Add python.exe to PATH"** during install.
2. **Microsoft ODBC Driver 17 for SQL Server** (or 18) — download from
   Microsoft, install with defaults. The helper needs this to talk to SQL
   Server. Without it, the app starts but live refresh shows a clear error.
3. **SQL Server (SQLEXPRESS) running** with database **POS_DB** (the same
   instance SmilePOS already uses). Check: open `services.msc` →
   `SQL Server (SQLEXPRESS)` → Status **Running**.
4. **Git** (optional, for updates) — or just copy this project folder.

## 2. Install the app

Open **Command Prompt** in the project folder and run:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Run the tests (recommended, takes ~5 seconds)

```bat
.venv\Scripts\python -m pytest tests\ -q
```

Expected: **66 passed**. If a test fails, do not deploy — send the output.

## 4. Run the app

```bat
.venv\Scripts\python run.py
```

First launch shows the **Setup Wizard** (3 pages):

1. **Pharmacy Profile** — name is prefilled: `EMAN PHARMACY & VACCINE`.
   Press **Next**.
2. **POS Connection** — Server `localhost\SQLEXPRESS`, Database `POS_DB`,
   Authentication **Windows Authentication (read-only)**. Press
   **Test Connection** — you should see a success line. Press **Next**.
3. **Initial Data** — leave **Demo (sample) data** ticked for now, press
   **Finish**. The dashboard opens with the sample data (labelled PREVIEW).

## 5. Connect live data (real POS_DB figures)

1. In the app, click **↻ Refresh Data** (top bar).
2. The app imports products, stock and sales from POS_DB (read-only) into
   its own local database. After the first successful refresh the demo data
   switches off automatically — from then on only live data is shown.
3. Check the **Daily Report (PDF)** tab: the report now shows real figures
   and the PREVIEW flag is gone.
4. If refresh fails, the error is shown plainly (server stopped, permission
   denied, or a missing column with the real column list). Fix the cause
   and press Refresh again.

## 6. Daily use

- **Overview** — most-demanding medicines (7 / 30 / 90 din), needs-attention
  list, near-expiry batches.
- **Reorder Suggestions** — cover days **7 / 14 / 21 / 30** (default 21).
  Click **Calculation** on any row to see every input; override a quantity
  only with a written reason (it is recorded in the audit trail).
- **All Stock** — search, supplier and status filters.
- **Daily Report (PDF)** — **Download Daily Report (PDF)** and
  **Download Excel** produce genuine files with real data.
- **Settings / Backup / Audit** — connection settings, safety-stock days,
  backup download/restore, and the audit trail.
- **Demo Data switch** (top right) — turns the sample data off/on. When
  off, every sample row and figure disappears and empty states say live
  data will appear after connecting to POS_DB.

## 7. Build the Windows installer (optional)

```bat
.venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name PharmaPurchaseAssistant run.py
```

Then open `installer\pharma-purchase-assistant.iss` in **Inno Setup 6** and
compile it. The installer puts the app in
`C:\Program Files\Pharma Purchase Assistant\`. The app keeps its own data
in `%LOCALAPPDATA%\PharmaPurchaseAssistant\data\pharma_purchase.db`.

## 8. Live HTML dashboard (browser version)

The same dashboard as a web page. A small local server (Flask) serves the
page and fetches live POS_DB data for it — the page alone (opened as a
file) still works, but only with demo data.

Start it (in the project folder, after step 2 install):

```bat
.venv\Scripts\python server.py
```

Then open **http://localhost:8080/** in the browser. Use another port with
`python server.py --port 8090` (then open http://localhost:8090/).

How to tell live from demo:

- Green **● LIVE — POS_DB se real data** badge + "Live — POS_DB Connected"
  in the top strip = real POS_DB data.
- Amber **● PREVIEW** badge = demo (sample) data.
- A red error banner under the top strip = live data could not be fetched
  (server/DB down, or the page opened as a file). The banner states the
  reason; the page keeps showing demo data until live data works.

- **↻ Refresh Data** fetches live data again from POS_DB (read-only).
- **Settings → Test Connection** checks the POS_DB connection for real.
- The server and the desktop app share the same local database file, so a
  refresh in one shows up in the other.
- Note: live items have no purchase cost yet (the import does not capture
  the purchase rate), so the reorder "Est. Purchase" total is Rs 0 for
  live items. The suggested quantities are still correct.

## Assumptions (3 lines)

1. Same PC: helper + SmilePOS run on one Windows PC; server `localhost\SQLEXPRESS`, database `POS_DB`, Windows Authentication.
2. Usable stock = total stock − expired/damaged (HTML rule); the supplied Daily Report file's Aslam/City supplier totals used full stock for future-expiry batches, so the app's totals there differ — see `tests/test_reports.py`.
3. SaleDetail / PurchaseDetail / ItemStock-view column names beyond the verified list are discovered at runtime via INFORMATION_SCHEMA; if a needed column is missing, refresh fails with the real column list instead of guessing.

## What was verified on the build machine (and what was NOT)

- **Verified:** 66 pytest tests green (55 desktop + 11 live-server tests:
  formula against the HTML figures, cover 7/14/21/30, override + reason,
  demo on/off, read-only guard, backup/restore, report totals, PDF/Excel
  generation, headless UI smoke test with Qt offscreen, server endpoints
  with a mocked database, and the HTML calling the right API URLs).
- **Verified:** the live server runs and serves the dashboard at `/`
  (HTTP 200); `/api/health`, `/api/data` and `/api/refresh` fail plainly
  (HTTP 503 + clear error) when SQL Server is unreachable, instead of
  silently showing demo data as live.
- **NOT verified here (must be tested on the client PC):** the live SQL
  Server connection and a real data refresh (this VM has no SQL Server and
  no ODBC driver), the HTML showing live data in a real browser, and the
  app running on a real Windows desktop. On the PC, start `server.py`,
  open http://localhost:8080/ and look for the green LIVE badge; if the
  badge stays on PREVIEW, read the red error banner for the reason.
