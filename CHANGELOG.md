# Changelog

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
