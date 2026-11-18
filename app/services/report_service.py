"""Daily stock report: data, PDF (ReportLab), Excel (openpyxl) and HTML.

The report layout mirrors the supplied Daily Stock Report HTML: a summary,
the urgent list (usable stock cover <= 3 days), the top 5 demanding
medicines, and supplier-wise suggested purchase totals. Every report shows
the pharmacy name, the report date, the data-refresh time and the settings
used, and is flagged PREVIEW while the figures are demo data.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..core import purchase
from ..core.config import PHARMACY_NAME
from ..database.models import Override
from . import purchase_service, stock_service


def _override_map(store) -> dict[str, Override]:
    result: dict[str, Override] = {}
    with store.session() as session:
        for row in session.query(Override).order_by(Override.id).all():
            result[row.item_code] = row
    return result


def build_report_data(
    store, analysis_days: int, cover_days: int, safety_days: int
) -> dict:
    """All report sections, computed from the visible (demo or live) data."""
    purchase.validate_settings(analysis_days, cover_days, safety_days)
    items = stock_service.visible_items(store)
    overrides = _override_map(store)
    suggestions = purchase_service.suggestions(store, analysis_days, cover_days, safety_days)
    suggestion_qty = {
        row["item"].item_code: row["final_qty"] for row in suggestions
    }

    out = sum(1 for item in items if purchase.status_of(item) == purchase.STATUS_OUT)
    critical = sum(
        1 for item in items if purchase.status_of(item) == purchase.STATUS_CRITICAL
    )
    low = sum(1 for item in items if purchase.status_of(item) == purchase.STATUS_LOW)
    estimated = sum(
        row["final_qty"] * row["item"].cost for row in suggestions
    )

    urgent = [
        item
        for item in items
        if purchase.status_of(item)
        in (purchase.STATUS_OUT, purchase.STATUS_CRITICAL)
    ]
    urgent.sort(key=purchase.days_left)
    urgent_rows = [
        {
            "name": item.name,
            "supplier": item.supplier,
            "usable": purchase.usable_stock(item),
            "ads": purchase.ads(item, analysis_days),
            "order_qty": suggestion_qty.get(item.item_code, 0),
            "est_cost": suggestion_qty.get(item.item_code, 0) * item.cost,
            "override": item.item_code in overrides,
        }
        for item in urgent
    ]

    top = sorted(items, key=lambda item: item.net30, reverse=True)[:5]
    top_rows = [
        {
            "name": item.name,
            "units_sold": item.net30,
            "usable": purchase.usable_stock(item),
            "days_left": purchase.days_left(item),
        }
        for item in top
    ]

    groups: dict[str, dict] = {}
    for row in suggestions:
        item = row["item"]
        group = groups.setdefault(
            item.supplier, {"supplier": item.supplier, "items": 0, "qty": 0, "cost": 0}
        )
        group["items"] += 1
        group["qty"] += row["final_qty"]
        group["cost"] += row["final_qty"] * item.cost
    supplier_rows = [groups[key] for key in sorted(groups)]

    return {
        "pharmacy_name": PHARMACY_NAME,
        "report_date": datetime.now(),
        "refreshed_at": store.get_setting("last_fetch", ""),
        "settings_line": (
            f"Analysis {analysis_days} din · Cover {cover_days} din · "
            f"Safety {safety_days} din"
        ),
        "is_demo": stock_service.is_demo(store),
        "summary": {
            "total_items": len(items),
            "out_of_stock": out,
            "critical": critical,
            "low_stock": low,
            "estimated_purchase": estimated,
        },
        "urgent": urgent_rows,
        "top_demanding": top_rows,
        "supplier_totals": supplier_rows,
    }


def format_money(amount: int) -> str:
    return f"Rs {amount:,}"


def days_text(days: float) -> str:
    if days == float("inf"):
        return "—"
    if days < 10:
        return f"{days:.1f} din"
    return f"{round(days)} din"


def render_html(data: dict) -> str:
    """Standalone HTML report, same structure as the supplied daily report."""
    demo_flag = ""
    if data["is_demo"]:
        demo_flag = (
            '<div class="demoflag">PREVIEW ONLY — ye report sample data par bani hai. '
            "Is HTML file mein live POS_DB connection nahi hai. Desktop app mein verified "
            "POS data ke baad real PDF/Excel export implement hoga.</div>"
        )
    summary = data["summary"]
    rows = "".join(
        "<tr><td>{name}{ovr}</td><td>{supplier}</td>"
        '<td class="r mono">{usable:,}</td><td class="r mono">{ads:.1f}</td>'
        '<td class="r mono">{qty:,}</td><td class="r mono">{cost}</td></tr>'.format(
            name=row["name"],
            ovr=" (override)" if row["override"] else "",
            supplier=row["supplier"],
            usable=row["usable"],
            ads=row["ads"],
            qty=row["order_qty"],
            cost=format_money(row["est_cost"]),
        )
        for row in data["urgent"]
    )
    top_rows = "".join(
        "<tr><td>{name}</td>"
        '<td class="r mono">{sold:,}</td><td class="r mono">{usable:,}</td>'
        '<td class="r mono">{days}</td></tr>'.format(
            name=row["name"],
            sold=row["units_sold"],
            usable=row["usable"],
            days=days_text(row["days_left"]),
        )
        for row in data["top_demanding"]
    )
    supplier_rows = "".join(
        "<tr><td>{supplier}</td>"
        '<td class="r mono">{items}</td><td class="r mono">{qty:,}</td>'
        '<td class="r mono">{cost}</td></tr>'.format(
            supplier=row["supplier"],
            items=row["items"],
            qty=row["qty"],
            cost=format_money(row["cost"]),
        )
        for row in data["supplier_totals"]
    )
    date_str = data["report_date"].strftime("%a, %d %b %Y")
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Daily Stock Report — {date_str}</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;color:#14201c}}
table{{width:100%;border-collapse:collapse;margin-bottom:18px}}
th,td{{border-bottom:1px solid #d5ddd9;padding:6px 8px;font-size:13px;text-align:left}}
.r{{text-align:right}}h3{{font-size:13px;text-transform:uppercase;letter-spacing:.05em;margin:18px 0 6px}}
.sum{{display:flex;gap:28px;flex-wrap:wrap}}.sum div b{{display:block;font-size:19px}}
.rhead{{border-bottom:3px double #888;padding-bottom:10px;margin-bottom:14px}}
.foot{{color:#777;font-size:12px;border-top:1px solid #ddd;padding-top:8px}}
.demoflag{{background:#fdf0dc;color:#a35c05;padding:8px 12px;font-size:12px;font-weight:700;margin-bottom:12px}}
.empty-state{{border:1.5px dashed #cbd5d1;padding:22px;text-align:center;color:#555}}</style>
</head><body>
<div class="rhead"><div><h2>Daily Stock &amp; Purchasing Report</h2>
<div style="color:#43554e;font-size:13px">{data["pharmacy_name"]} — Pharma Purchase Assistant · SmilePOS</div></div>
<div><b>Report date:</b> {date_str}<br><b>Source:</b> POS_DB · DESKTOP-SJO68CG\\SQLEXPRESS<br>
<b>Data refreshed:</b> {data["refreshed_at"] or "—"}<br>
<b>Settings:</b> {data["settings_line"]}</div></div>
{demo_flag}
<div class="sum"><div>Total Items<b>{summary["total_items"]}</b></div>
<div>Out / Critical<b>{summary["out_of_stock"]} / {summary["critical"]}</b></div>
<div>Low Stock<b>{summary["low_stock"]}</b></div>
<div>Est. Purchase<b>{format_money(summary["estimated_purchase"])}</b></div></div>
<h3>Urgent Review — Current Usable Stock Cover ≤ 3 Days</h3>
<table><thead><tr><th>Medicine</th><th>Supplier</th><th class="r">Usable</th>
<th class="r">ADS</th><th class="r">Order Qty</th><th class="r">Est. Cost</th></tr></thead>
<tbody>{rows or '<tr><td colspan="6">Koi urgent item nahi.</td></tr>'}</tbody></table>
<h3>Top 5 Demanding Medicines (net, 30 din)</h3>
<table><thead><tr><th>Medicine</th><th class="r">Units Sold</th><th class="r">Usable Stock</th>
<th class="r">Stock chalega</th></tr></thead><tbody>{top_rows}</tbody></table>
<h3>Suggested Orders — Supplier Wise Total</h3>
<table><thead><tr><th>Supplier</th><th class="r">Items</th><th class="r">Total Qty</th>
<th class="r">Est. Cost</th></tr></thead><tbody>{supplier_rows}</tbody></table>
<div class="foot">Ye report POS_DB se read-only fetch par auto-generate hoti hai. Formula: ADS = Net Sales ÷ Analysis Days; Target Stock = (ADS × Cover Days) + Safety Stock; Suggested Purchase = max(0, Target − Usable Stock − Confirmed Incoming). Manual overrides (agar koi hain) report mein “override” likh kar nazar aate hain. Final order se pehle rate aur availability supplier se confirm karein.</div>
</body></html>"""


def render_pdf(data: dict, path: Path) -> Path:
    """Genuine PDF report via ReportLab, same sections as the HTML report."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"Daily Stock Report — {data['pharmacy_name']}",
    )
    elements = [
        Paragraph("Daily Stock &amp; Purchasing Report", styles["Title"]),
        Paragraph(
            f"{data['pharmacy_name']} — Pharma Purchase Assistant · SmilePOS",
            styles["Normal"],
        ),
        Paragraph(
            f"Report date: {data['report_date'].strftime('%a, %d %b %Y')} · "
            f"Data refreshed: {data['refreshed_at'] or '—'} · {data['settings_line']}",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
    ]
    if data["is_demo"]:
        elements.append(
            Paragraph(
                "PREVIEW ONLY — this report is built on sample data.",
                styles["Normal"],
            )
        )
    summary = data["summary"]
    summary_table = Table(
        [[
            f"Total Items\n{summary['total_items']}",
            f"Out / Critical\n{summary['out_of_stock']} / {summary['critical']}",
            f"Low Stock\n{summary['low_stock']}",
            f"Est. Purchase\n{format_money(summary['estimated_purchase'])}",
        ]],
        colWidths=[38 * mm, 38 * mm, 38 * mm, 52 * mm],
    )
    summary_table.setStyle(
        TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
    )
    elements += [summary_table, Spacer(1, 6 * mm)]

    def section_table(header: list[str], rows: list[list], widths: list[float]):
        table = Table([header] + rows, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b6e5d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ])
        )
        return table

    elements.append(Paragraph("Urgent — usable stock cover ≤ 3 days", styles["Heading2"]))
    urgent_rows = [
        [
            row["name"] + (" (override)" if row["override"] else ""),
            row["supplier"],
            f"{row['usable']:,}",
            f"{row['ads']:.1f}",
            f"{row['order_qty']:,}",
            format_money(row["est_cost"]),
        ]
        for row in data["urgent"]
    ]
    elements.append(section_table(
        ["Medicine", "Supplier", "Usable", "ADS", "Order Qty", "Est. Cost"],
        urgent_rows or [["Koi urgent item nahi.", "", "", "", "", ""]],
        [52 * mm, 38 * mm, 18 * mm, 16 * mm, 22 * mm, 28 * mm],
    ))
    elements.append(Paragraph("Top 5 Demanding Medicines (net, 30 din)", styles["Heading2"]))
    elements.append(section_table(
        ["Medicine", "Units Sold", "Usable Stock", "Stock chalega"],
        [
            [row["name"], f"{row['units_sold']:,}", f"{row['usable']:,}",
             days_text(row["days_left"])]
            for row in data["top_demanding"]
        ],
        [70 * mm, 32 * mm, 32 * mm, 40 * mm],
    ))
    elements.append(Paragraph("Suggested Orders — Supplier Wise Total", styles["Heading2"]))
    elements.append(section_table(
        ["Supplier", "Items", "Total Qty", "Est. Cost"],
        [
            [row["supplier"], str(row["items"]), f"{row['qty']:,}", format_money(row["cost"])]
            for row in data["supplier_totals"]
        ],
        [70 * mm, 25 * mm, 32 * mm, 47 * mm],
    ))
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        "Formula: ADS = Net Sales ÷ Analysis Days; Target Stock = (ADS × Cover Days) + "
        "Safety Stock; Suggested Purchase = max(0, Target − Usable Stock − Confirmed "
        "Incoming). Final order se pehle rate aur availability supplier se confirm karein.",
        styles["Normal"],
    ))
    doc.build(elements)
    return Path(path)


def render_excel(data: dict, path: Path) -> Path:
    """Excel workbook with one sheet per report section."""
    from openpyxl import Workbook

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary.append(["Pharmacy", data["pharmacy_name"]])
    summary.append(["Report date", data["report_date"].strftime("%a, %d %b %Y")])
    summary.append(["Data refreshed", data["refreshed_at"] or "—"])
    summary.append(["Settings", data["settings_line"]])
    summary.append(["Demo data (PREVIEW)" if data["is_demo"] else "Live data", ""])
    summary.append([])
    summary.append(["Total Items", data["summary"]["total_items"]])
    summary.append(["Out of Stock", data["summary"]["out_of_stock"]])
    summary.append(["Critical", data["summary"]["critical"]])
    summary.append(["Low Stock", data["summary"]["low_stock"]])
    summary.append(["Est. Purchase", data["summary"]["estimated_purchase"]])

    urgent = workbook.create_sheet("Urgent")
    urgent.append(["Medicine", "Supplier", "Usable", "ADS", "Order Qty", "Est. Cost", "Override"])
    for row in data["urgent"]:
        urgent.append([row["name"], row["supplier"], row["usable"], round(row["ads"], 1),
                       row["order_qty"], row["est_cost"], "yes" if row["override"] else "no"])

    top = workbook.create_sheet("Top Demanding")
    top.append(["Medicine", "Units Sold", "Usable Stock", "Days Left"])
    for row in data["top_demanding"]:
        days = row["days_left"]
        top.append([row["name"], row["units_sold"], row["usable"],
                    None if days == float("inf") else round(days, 1)])

    suppliers = workbook.create_sheet("Supplier Totals")
    suppliers.append(["Supplier", "Items", "Total Qty", "Est. Cost"])
    for row in data["supplier_totals"]:
        suppliers.append([row["supplier"], row["items"], row["qty"], row["cost"]])

    workbook.save(path)
    return Path(path)
