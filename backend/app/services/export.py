"""CSV / PNG / PDF exports of an analysis result."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure   # object API (no pyplot) -> thread-safe


def safe_filename(a: dict, ext: str, kind: str = "") -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "-", a["region"]["name"]).strip("-")[:40] or "region"
    return f"climatesphere_{a['hazard']}_{name}_{a['period']['from']}-{a['period']['to']}{('_' + kind) if kind else ''}.{ext}"


def _cell(v):
    """Neutralise spreadsheet formula injection for text cells."""
    if isinstance(v, str) and v[:1] in "=+-@\t\r":
        return "'" + v
    return "" if v is None else v


def to_csv(a: dict, kind: str = "annual") -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    if kind == "events":
        w.writerow(["start", "end", "duration_days", "peak", "intensity", "year"])
        for e in a.get("all_events", a["events"]):
            w.writerow([e["start"], e["end"], e["duration"], e.get("peak"), e.get("intensity"), e["year"]])
        return buf.getvalue()
    s, u = a["series"], a["units"]
    w.writerow(["year", f"events ({u['frequency']})", f"hazard_days ({u['hazard_days']})", f"mean_duration ({u['duration']})",
                f"mean_intensity ({u['intensity'] or 'n/a'})", "peak", f"rolling_{a['rolling']['window']}y_hazard_days",
                "coverage_pct_tmax"])
    cov = a["data_quality"]["coverage_pct_by_year"]
    for i, y in enumerate(a["years"]):
        w.writerow([y, _cell(s["frequency"][i]), _cell(s["hazard_days"][i]), _cell(s["duration"][i]),
                    _cell(s["intensity"][i]), _cell(s["peak"][i]), _cell(a["rolling"]["hazard_days"][i]), cov.get(str(y), "")])
    return buf.getvalue()


def to_png(a: dict) -> bytes:
    fig = Figure(figsize=(9, 4.2), dpi=130, facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ys = a["years"]
    vals = [v if v is not None else float("nan") for v in a["series"]["hazard_days"]]
    ax.bar(ys, vals, color="#FF7038", alpha=.85, label=a["units"]["hazard_days"])
    ax.plot(ys, [v if v is not None else float("nan") for v in a["rolling"]["hazard_days"]], color="#0b4fa8", lw=2,
            label=f"{a['rolling']['window']}-yr rolling mean")
    ax.plot(ys, [v if v is not None else float("nan") for v in a["fit"]["hazard_days"]], color="#111", lw=1.4, ls="--",
            label="Linear trend (OLS)")
    ax.set_title(f"{a['label']} days - {a['region']['name']} ({a['period']['from']}–{a['period']['to']})", fontsize=11)
    ax.set_xlabel("Year")
    ax.set_ylabel(a["units"]["hazard_days"])
    ax.grid(alpha=.25)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def to_pdf(a: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape as esc

    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"ClimateSphere - {a['label']} - {a['region']['name']}")
    ins, t, dq = a["insight"], a["trend"]["hazard_days"], a["data_quality"]
    story = [Paragraph(f"ClimateSphere AI — {esc(a['label'])} trend report", st["Title"]),
             Paragraph(f"<b>Region:</b> {esc(a['region']['name'])} &nbsp; <b>Period:</b> {a['period']['from']}–{a['period']['to']} "
                       f"&nbsp; <b>Generated:</b> {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", st["Normal"]),
             Spacer(1, 6), Paragraph("Key finding", st["Heading2"]), Paragraph(esc(ins["headline"]), st["BodyText"])]
    for b in ins["bullets"]:
        story.append(Paragraph("• " + esc(b), st["BodyText"]))
    story += [Spacer(1, 6), Image(io.BytesIO(to_png(a)), width=178 * mm, height=83 * mm), Spacer(1, 6),
              Paragraph("Statistics", st["Heading2"])]
    mk, sen, ols = t["mann_kendall"], t["sen"], t["ols"]
    rows = [["Metric", "Value"],
            ["Events detected", str(a["event_count"])],
            ["Years analysed / excluded", f"{a['period']['years_analyzed']} / {len(a['period']['years_excluded'])}"],
            ["Mann-Kendall (hazard days)", f"tau={mk['tau']}, p={mk['p']}, {mk['trend']}"],
            ["Theil-Sen slope / decade", str(sen["slope_per_decade"])],
            ["OLS slope / decade (p)", f"{ols['slope_per_decade']} ({ols['p']})"],
            ["Data completeness", f"{dq['completeness_pct']} %"]]
    tb = Table(rows, colWidths=[70 * mm, 108 * mm])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b4fa8")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("GRID", (0, 0), (-1, -1), .25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story += [tb, Spacer(1, 8), Paragraph("Method", st["Heading2"]), Paragraph(esc(a["definition"]["text"]), st["BodyText"]),
              Paragraph("Caveats", st["Heading2"])]
    story += [Paragraph("• " + esc(c), st["BodyText"]) for c in ins["caveats"]]
    story += [Spacer(1, 6), Paragraph(f"Source: {esc(a['source']['name'])}.", st["Italic"])]
    doc.build(story)
    return buf.getvalue()
