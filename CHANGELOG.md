# Changelog

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
