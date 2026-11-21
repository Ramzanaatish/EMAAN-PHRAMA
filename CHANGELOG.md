# Changelog

## v1.3.4 — 2026-11-21

TRY_CONVERT crash fix (Nelson, 21 Nov 2026, live screenshot: naya
v1.3.3 server chalaya to Refresh fail — "'TRY_CONVERT' is not a
recognized built-in function name (195)").

- **Root cause:** TRY_CONVERT needs SQL Server 2012+ AND a database
  compatibility level of 110+. POS_DB (old SmilePOS database) runs
  below that level, so the v1.3.3 date probe failed the whole
  refresh (POST /api/refresh 503) and the dashboard fell back to
  stale data. The v1.3.0 server worked because it never called
  TRY_CONVERT.
- **Fix:** the date expression now parses with plain CONVERT + CASE
  + LIKE only (available since SQL Server 2000): real dates and ISO
  strings via style 120, dd/mm/yyyy strings (1- or 2-digit day/month,
  time suffix ok) via style 103, 'Nov 21 2026' strings via plain
  CONVERT, anything else -> NULL, never an error. Same probe, same
  urgency sort, same diagnostics — only the SQL function changed.
- **Tests:** 148 passed (147 + 1 new v1.3.4 regression test: no
  TRY_CONVERT/TRY_CAST/TRY_PARSE in any generated sales query).

## v1.3.3 — 2026-11-21

Out-of-stock-first urgency sort + suggestions audit (Nelson, 21 Nov
2026, live screenshot: proxy filter ke baad TOTAL ITEMS 2,535 lekin
OUT OF STOCK 0 — proxy ne out-of-stock medicines hi chhupa di thin).

- **Root cause (proxy):** out-of-stock medicine ke sab fields 0 hote
  hain (stock/net30/reorder/max/incoming/unusable) — /api/data ke
  fields mein koi nishan nahi — is liye proxy use "catalogue filler"
  samajh kar chhupa deta tha. Asal fix server-side exact filter hai
  (PurchaseDetail/OpeningStock, v1.3.1): khareedi hui item chahe
  fields zero hon, import mein rehti hai. Is release mein us filter
  ka test hai (zero-field item with purchase entry kept).
- **Urgency sort:** All Stock, Reorder Suggestions, attention list aur
  report ki Urgent table mein ab usable stock 0 wali medicines pehle,
  phir sab se recent sale wali pehle (per-item last sale date, MAX
  sale date — server bhejta hai, HTML `lastSale` par sort karta hai,
  purana server na bheje to days-left fallback). Phir expiry jald wali
  pehle, phir kam din ka cover pehle. Formula (ADS/Target/Suggested)
  nahi badla — sirf order badla. "Aakhri sale" tareekh row mein nazar
  aati hai. Research: pharmacy reorder triage (inventory-reorder-crew),
  expiry categories (PharmaGuard), ABC/FSN velocity (MedXtore, ABC-XYZ)
  — detail CHANGELOG ke neeche aur report mein.
- **Suggestions audit:** date probe ab JOINED SaleDetail rows ginta
  hai (voucher mein recent date ho lekin VoucherNo join rows giraye to
  pehle probe phir bhi column chun leta tha), aur tareekh dd/mm/yyyy
  strings ke liye style 103 fallback hai. Last-sale diagnostics bhi
  server log mein aati hain (items with last sale). Agar live mein
  phir bhi 0 ho to `[refresh]` line saaf bataye gi (joined rows /
  in-window rows) ke data mein sale nahi hai — kuch fake nahi kiya.
- **Store migration:** purani SQLite file kholne par missing columns
  (jaise last_sale_date) khud ADD COLUMN ho jate hain.
- **GitHub research (21 Nov 2026):** inventory-reorder-crew
  (Namitha-C-Anto) — triage: expired → replacement, <15 din expiry →
  urgent, <30 din → expiring-soon; priority assignment + human approval
  (LLM/agents stack nahi liya — offline PC, API keys nahi). PharmaGuard
  (AHMED-TECH-01) — expiry categories + ROP = ADS × lead time + safety
  stock (hamare formula jaisa — formula nahi badla). MedXtorePharmacyV2
  — ABC 70/20/10 revenue + turnover (cost 0 hai live, is liye revenue
  ABC nahi ho saka; units-based FSN recency sort mein hi aa gaya).
  KinetiRx (Raktim94) — shortage book → supplier-wise PO (hamara
  draft PO jaisa — shortage-first order apnaya). ABC-XYZ article
  (NaijaDataProfessor) — demand consistency AX/AY/AZ (sales aate hi
  recency + fraction_7/90 se milta hai). Curo/ShbairPharma — fast/slow
  + expiry alerts (same FSN/expiry conclusion). ML forecasting
  (Tata 1mg) aur SupplyNetPy simulation — offline single pharmacy ke
  liye heavy, reject.
- Tests: 147 passed (136 + 11 naye v1.3.3 tests) + Node se HTML ke
  apne sort functions ke 7 functional checks pass.

## v1.3.2 — 2026-11-21

All Stock memory cap (Nelson: "ye file run hony pr memory q consume
krta h itna..?"). HTML All Stock tab saari rows aik saath render karta
tha — 32,952 items = hazaron DOM rows, browser ki memory bhar jati thi
(desktop app mein 200 rows ki cap pehle se hai).

- **50-row cap:** All Stock mein aik waqt mein sirf 50 rows dikhti
  hain; neeche "Show more" button har dafa mazeed 50 dikhata hai, aur
  count batata hai ("50 / 3,240 dikhaye ja rahe hain"). Search ya
  filter badle to dobara 50 se shuru hota hai.
- Tests: 136 passed (135 + 1 naya v1.3.2 test).

## v1.3.1 — 2026-11-21

Stock-entry filter + suggestions fix (Nelson, 21 Nov 2026, live HTML
screenshots: 32,952 catalogue items, OUT OF STOCK 30,416, lekin NET
UNITS SOLD (30 din) 0 aur 0 reorder suggestions).

- **Stock-entry filter:** sirf wo medicines dikhti hain jin ki stock
  entry pehle kam-az-kam 1 dafa hui ho. "Stock entry" = PurchaseDetail
  line (purchase / goods received) ya OpeningStock row. Server import
  par exact filter lagata hai (KPIs, All Stock, suggestions, report,
  desktop app — sab mein), aur HTML mein proxy filter bhi hai jo
  /api/data ke fields se kaam karta hai (stock > 0 ya net30 > 0 ya
  reorder/max level set ya incoming/unusable > 0). Server ne filter
  laga diya ho to HTML proxy dobara nahi lagta. Filter fail-open hai:
  entries na milen to sab kuch import hota hai, chhupaya nahi jata.
- **Suggestions fix:** sales query ab tareekh wala column assume nahi
  karti — har candidate column ko pichle 90 din ki rows ke liye probe
  karti hai aur pehla column jis mein asal data ho use karti hai
  (VoucherDate fallback). Saath mein diagnostics: SaleDetail rows,
  joined rows, 90-day window rows, items with sales — server window
  mein Refresh ke baad nazar aate hain, aur `/api/data` mein bhi.
- **Ghalat khaali message theek:** suggestions khaali hon to page ab
  saaf batata hai ke sales data 0 hai (ADS 0 → target 0) ya waqai
  stock kaafi hai. Filter se sab chhup jayein to bhi saaf message
  hai — "koi data nahi" nahi.
- Tests: 135 passed (125 + 10 naye v1.3.1 tests). Shart: akele HTML file
  SQL Server se nahi jud sakti — server chalta rehna lazmi hai.

## v1.3.0 — 2026-11-21

HTML file + server connector ("html file ho and sath main server connector
ho, kia ye work kry ga?" — Nelson, 21 Nov 2026). Jawab: haan — Flask
server (`app/web.py`) pehle se hi server connector hai (POS_DB read-only
+ JSON API); is version mein HTML file us se judne ke qabil ban gayi.

- **CORS on:** server har API jawab par `Access-Control-Allow-Origin: *`
  (GET/POST/OPTIONS) bhejta hai — file:// se khuli page ab
  `http://127.0.0.1:5000/api/...` call kar sakti hai. Server se serve
  hui page same-origin hi rehti hai.
- **HTML mein API base:** file:// se khole to base
  `http://127.0.0.1:5000`, warna same-origin. Saari 6 fetch calls
  (`/api/data`, `/api/health`, `/api/refresh`, `/api/settings`,
  `/api/test-connection`) is base se hoti hain. Server band ho to
  Roman-Urdu mein kehta hai: "Server nahi chal raha — PharmaServer.exe
  chalao".
- **Server port 5000:** `server.py` ka default port 8080 se 5000 hua —
  HTML, README aur run instructions mein bhi wahi port hai.
- **One-click launcher:** `start-server.bat` (plain CMD) — PharmaServer.exe
  chalata hai, phir HTML file browser mein kholta hai.
- **PharmaServer.exe:** `server.spec` (PyInstaller onefile, console) —
  pharmacy PC par Python install nahi chahiye. CI ab desktop Setup ke
  saath `PharmaServer` artifact bhi banata hai.
- **Desktop app waisa ka waisa hai** — ye setup us ka alternate tareeqa
  hai, replacement nahi.
- Tests: 125 passed (118 + 7 naye HTML/server tests). Shart yaad rakhein:
  akele HTML file SQL Server se nahi jud sakti — server chalta rehna
  lazmi hai, warna demo data dikhta hai.

## v1.2.1 — 2026-11-21

Smooth startup ("load hony main time ly rha hai, preview main issue hai,
RAM par ziada bojh na daalo" — Nelson, 21 Nov 2026).

- **Window pehle, data baad mein:** pehle poora refresh + paanchon tabs
  bharne ke baad window khulti thi, to khaali screen par wait karna
  parta tha. Ab pehle splash screen (EMAN logo + Loading…) aati hai,
  window foran khulti hai, aur pehla refresh uske baad hota hai.
- **Lazy tabs:** sirf wohi tab render hota hai jo screen par hai —
  baaki chaar tabs pehli dafa kholne par bharte hain. 3,000 items par
  startup par banne wale table rows 200 + 200 se 0 ho gaye, report
  HTML tab kholne tak banti hi nahi.
- **Halki RAM:** startup par peak RAM 3,000 items par 142 MB se 126 MB;
  window banne ka time 0.70 s se 0.13 s.
- **Table fill ek repaint mein:** reorder/stock tables bharte waqt
  har row par repaint band — bari list par scroll/render smooth.
- Tests: 118 passed (114 + 4 naye startup tests).

## v1.2.0 — 2026-11-21

POS fetch + loading fix ("proper work nahi kar raha, heavy hai, data
fetch nahi karta" — Nelson, 21 Nov 2026).

- **POS data ab aata hai:** connector ek refresh mein 11 alag ODBC
  connections kholta tha (har list_columns + har fetch apna connection)
  — har connect named instance ko SQL Server Browser se dobara
  dhoondta tha, to slow/stopped Browser par refresh minutes hang ho
  kar fail hota tha. Ab poora refresh **ek connection** par hota hai
  (session + column cache), aur 7/30/90 din ki sales **ek query**
  mein aati hain.
- **Driver auto-detect:** driver "ODBC Driver 17" hardcoded tha — PC
  par sirf Driver 18 ho (ya koi driver na ho) to har query fail hoti
  thi. Ab newest installed driver pick hota hai (18 → 17 → 13 →
  "SQL Server"); Driver 18 ke liye TrustServerCertificate lagta hai
  (SQLEXPRESS ka self-signed certificate warna handshake fail karta
  hai).
- **ItemInfo columns discover hoti hain:** fetch_products saare 8
  columns assume karta tha — ek column missing ho to poora import
  zero data par fail hota tha. Ab sirf maujood columns select hote
  hain.
- **Saaf errors:** fail honay par raw pyodbc text ki jagah asal wajah
  + PC par check karne ki cheez milti hai (driver missing, SQL Server
  / Browser service band, TCP/IP off, database naam ghalat, login
  fail, timeout).
- **UI freeze khatam:** Refresh aur Test Connection ab QThread worker
  par chalte hain — window refresh ke doran responsive rehti hai,
  button "Refreshing…" dikhata hai.
- **Heavy rendering khatam:** refresh_all() products ek dafa load kar
  ke har tab ko pass karta hai (pehle ~10 dafa full SELECT * hota
  tha); All Stock aur Reorder tables max 200 rows render karte hain
  (sab se urgent pehle; baaqi ka count label mein); search 250 ms
  debounce ke saath hai; supplier list sirf tabdeel honay par banti
  hai; draft check aur override reasons ab per-row query nahi (ek
  query). 3,000 items par refresh_all() 24 s → 0.54 s (headless
  measurement).
- **Version fix:** installer ka version ab 1.2.0 hai (.iss + CI
  artifact — pehle code v1.1.0 tha lekin Setup.exe ka naam 1.0.0 tha).
- Tests: 97 → 114 (17 naye: driver detection, column discovery,
  single-query sales, friendly errors, one-connection refresh +
  legacy fallback, single-load views).

## v1.1.0 — 2026-11-18

- Header redesign: dark-green header bar with the EMAN light logo
  (`assets/eman-logo-light.png`, white text for dark backgrounds), app
  title, demo/live badge; falls back to a text wordmark if the logo file
  is missing (PyInstaller builds resolve assets via `resource_path()`).
- Layout: content centred at max 1320 px; vertical scrolling only — no
  horizontal scrollbar at 1000–1240 px widths (the "Coming in v2" card
  no longer forces the window wide); wide tables scroll internally.
- Server address validated with `validate_server_address()` before Save
  or Test Connection (Settings tab and setup wizard): invalid input
  shows the accepted forms and is never saved or tested. The refresh
  path keeps using the saved address from the store, and the header
  strip now reflects the saved server/database after a save.
- Fixed Overview demand bars and Settings cards being pushed out of
  view by stretched hint labels (trailing stretch in card layouts).
- 97 pytest tests green (73 before + 24 new: server validation,
  `resource_path`, header logo/fallback, save/test validation).

## v1.0.0 — 2026-11-18

- First release. Desktop app (Python + PySide6) for EMAN PHARMACY & VACCINE.
- Overview dashboard, Reorder Suggestions, All Stock, Daily Report (PDF +
  Excel + HTML), Settings / Backup / Audit — matching the HTML preview.
- Cover-day options 7 / 14 / 21 / 30 (7 days added vs the HTML preview);
  sales views stay 7 / 30 / 90 days.
- Formula: ADS = Net Sales ÷ Analysis Days; Target = (ADS × Cover) +
  Safety Stock (ADS × safety days, default 5); Suggested = max(0, Target
  − Usable − Confirmed Incoming). Per-item calculation breakdown dialog.
- Read-only POS integration: SELECT-only guard, Windows Authentication,
  `localhost\SQLEXPRESS` / POS_DB; own SQLite database; manual refresh.
- Demo data switch (same 18 sample medicines as the HTML, labelled
  PREVIEW); off removes every sample row and figure.
- First-run setup wizard (pharmacy profile, POS connection test, demo
  choice). Manual overrides require a reason and are audit-logged.
- 55 pytest tests green, including a headless Qt UI smoke test.
