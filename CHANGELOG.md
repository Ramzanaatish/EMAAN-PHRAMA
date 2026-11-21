# Changelog

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
