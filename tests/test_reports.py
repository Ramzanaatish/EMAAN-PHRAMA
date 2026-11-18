"""Tests for the daily report (data, HTML, PDF, Excel).

Note on one deliberate difference from the supplied Daily Stock Report
file: that file's supplier totals count future-expiry batches as usable
stock (Arinac/Disprin/Velosef), while the HTML preview — the behaviour
reference — excludes all unusable stock from usable stock. This app
follows the HTML rule everywhere, so Aslam/City totals differ from the
report file (Aslam 1215 units / Rs 320,020 here vs 1155 / Rs 316,420
there; City 1034 / Rs 97,258 vs 959 / Rs 88,798). Premier and Madina
match the report file exactly.
"""

from __future__ import annotations

from app.services import report_service


def test_report_summary_matches_html(demo_store):
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    assert data["pharmacy_name"] == "EMAN PHARMACY & VACCINE"
    assert data["summary"]["total_items"] == 18
    assert data["summary"]["out_of_stock"] == 2
    assert data["summary"]["critical"] == 7
    assert data["summary"]["low_stock"] == 4
    assert data["summary"]["estimated_purchase"] == 1008784
    assert data["is_demo"] is True


def test_report_urgent_list(demo_store):
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    assert len(data["urgent"]) == 9
    names = [row["name"] for row in data["urgent"]]
    assert names[0] == "Brufen 400mg"
    panadol = next(row for row in data["urgent"] if row["name"] == "Panadol Extra 500mg")
    assert panadol["order_qty"] == 970
    assert panadol["est_cost"] == 40740


def test_report_top_5_demanding(demo_store):
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    names = [row["name"] for row in data["top_demanding"]]
    assert names == [
        "Panadol Extra 500mg", "Disprin", "Risek 20mg", "Strepsils", "Augmentin 625mg",
    ]
    assert data["top_demanding"][0]["units_sold"] == 1860


def test_report_supplier_totals(demo_store):
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    totals = {row["supplier"]: row for row in data["supplier_totals"]}
    assert totals["Premier Agencies"] == {
        "supplier": "Premier Agencies", "items": 6, "qty": 3195, "cost": 502980,
    }
    assert totals["Madina Medicine Co."] == {
        "supplier": "Madina Medicine Co.", "items": 4, "qty": 1350, "cost": 88526,
    }
    assert totals["Aslam Traders"]["qty"] == 1215
    assert totals["Aslam Traders"]["cost"] == 320020
    assert totals["City Distributors"]["qty"] == 1034
    assert totals["City Distributors"]["cost"] == 97258


def test_report_html_contains_pharmacy_and_preview_flag(demo_store):
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    html = report_service.render_html(data)
    assert "EMAN PHARMACY &amp; VACCINE" in html or "EMAN PHARMACY & VACCINE" in html
    assert "PREVIEW ONLY" in html
    assert "Panadol Extra 500mg" in html
    assert "ADS = Net Sales" in html


def test_report_pdf_is_a_real_pdf(tmp_path, demo_store):
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    path = report_service.render_pdf(data, tmp_path / "report.pdf")
    assert path.exists()
    assert path.read_bytes()[:5] == b"%PDF-"
    assert path.stat().st_size > 1000


def test_report_excel_has_all_sections(tmp_path, demo_store):
    from openpyxl import load_workbook

    data = report_service.build_report_data(demo_store, 30, 21, 5)
    path = report_service.render_excel(data, tmp_path / "report.xlsx")
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Summary", "Urgent", "Top Demanding", "Supplier Totals"]
    summary = workbook["Summary"]
    assert summary["A1"].value == "Pharmacy"
    assert summary["B1"].value == "EMAN PHARMACY & VACCINE"
    urgent = workbook["Urgent"]
    assert urgent.max_row == 10  # header + 9 urgent items
    assert urgent.cell(row=2, column=1).value == "Brufen 400mg"


def test_report_empty_when_demo_off(demo_store):
    from app.services import import_service

    import_service.disable_demo(demo_store)
    data = report_service.build_report_data(demo_store, 30, 21, 5)
    assert data["summary"]["total_items"] == 0
    assert data["urgent"] == []
    assert data["top_demanding"] == []
    assert data["supplier_totals"] == []
