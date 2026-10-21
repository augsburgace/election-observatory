"""Exports use the same pinned analytical workspace as the interactive UI."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import zipfile
from datetime import date
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .domain import utc_now
from .registry import METRICS
from .settings import PROJECT_ROOT

SECTIONS = ["overview", "voting", "geography", "polls", "sources"]
CYCLE_COLORS = {2026: "#087f91", 2024: "#8750c8", 2022: "#296fb8", 2020: "#9a6b06", 2018: "#61738b"}


def _sections(sections: list[str] | None) -> list[str]:
    selected = SECTIONS if sections is None else sections
    if any(section not in SECTIONS for section in selected):
        raise ValueError("Unknown report section")
    return list(dict.fromkeys(selected))


def chart_geometry(view: dict, width=900, height=300) -> dict:
    """Shared vector geometry for HTML and PDF; steps are actual observations."""
    grouped = {}
    for point in view["series"]:
        election_date = next((r["election_date"] for r in view["observations"] if r["cycle"] == point["cycle"]), None)
        x = point.get("days_to_election")
        if x is None:
            x = (date.fromisoformat(point["date"]) - date.fromisoformat(election_date)).days if election_date else date.fromisoformat(point["date"]).toordinal()
        grouped.setdefault(point["cycle"], []).append((float(x), float(point["value"])))
    values = [point for points in grouped.values() for point in points]
    if not values:
        return {"lines": [], "width": width, "height": height}
    left, top, bottom, right = 75, 30, height - 45, width - 25
    xmin, xmax = min(p[0] for p in values), max(p[0] for p in values)
    ymax = max(max(p[1] for p in values), 1) * 1.08
    lines = []
    for cycle, points in sorted(grouped.items(), reverse=True):
        coordinates = []
        for x, value in sorted(points):
            px = left + (x - xmin) / max(xmax - xmin, 1) * (right - left)
            py = bottom - value / ymax * (bottom - top)
            if coordinates:
                coordinates.append((px, coordinates[-1][1]))
            coordinates.append((px, py))
        lines.append({"cycle": cycle, "color": CYCLE_COLORS.get(cycle, "#61738b"), "points": coordinates})
    return {"lines": lines, "width": width, "height": height, "left": left, "top": top, "bottom": bottom,
            "right": right, "ymax": ymax, "xmin": xmin, "xmax": xmax}


def trajectory_svg(view: dict) -> str:
    chart = chart_geometry(view)
    if not chart["lines"]:
        return "<p>No voting trajectory is supported by this selection.</p>"
    elements = ["<svg viewBox='0 0 900 300' role='img' aria-labelledby='trajectory-title'><title id='trajectory-title'>Actual observations by cycle, aligned by days before Election Day</title>"]
    for fraction in (0, .25, .5, .75, 1):
        y = chart["bottom"] - fraction * (chart["bottom"] - chart["top"])
        elements.append(f"<line x1='75' x2='875' y1='{y}' y2='{y}' stroke='#d9e3ed'/><text x='68' y='{y + 4}' text-anchor='end'>{fraction * chart['ymax']:,.0f}</text>")
    for index, line in enumerate(chart["lines"]):
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in line["points"])
        elements.append(f"<polyline points='{coords}' fill='none' stroke='{line['color']}' stroke-width='3'/>")
        x, y = line["points"][-1]
        elements.append(f"<circle cx='{x}' cy='{y}' r='3' fill='{line['color']}'/><text x='{90 + index * 130}' y='20' fill='{line['color']}'>{line['cycle']}</text>")
    elements.append(f"<text x='75' y='282'>{-chart['xmin']:g} days before Election Day</text><text x='875' y='282' text-anchor='end'>{-chart['xmax']:g} days before</text></svg>")
    return "".join(elements)


def manifest(view: dict) -> dict:
    boundary_manifest = PROJECT_ROOT / "frontend" / "public" / "geography" / "manifest.json"
    parser_files = sorted((PROJECT_ROOT / "backend" / "observatory" / "connectors").glob("*.py"))
    build_files = sorted((PROJECT_ROOT / "backend" / "observatory").rglob("*.py"))
    return {"application": "Battleground Senate Observatory", "application_version": "0.1.0",
            "application_build_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in build_files)).hexdigest(),
            "parser_versions": {"export_runtime_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in parser_files)).hexdigest(),
                                "recorded_observation_versions": sorted({str(o.get("metadata", {}).get("parser_version")) for o in view["observations"] if o.get("metadata", {}).get("parser_version")}),
                                "note": "Runtime fingerprint identifies the export code; individual recorded parser versions identify original extraction when supplied."},
            "metric_definition": next((metric for metric in METRICS if metric["id"] == view["query"]["metric"]), None),
            "calendar_references": view.get("calendar_references", []),
            "boundary": json.loads(boundary_manifest.read_text()) if boundary_manifest.exists() else {"available": False},
            "exported_at": utc_now(), "revision": view["revision"], "query": view["query"],
            "coverage": view["coverage"], "warnings": view["warnings"],
            "sources": [{key: source.get(key) for key in ("id", "name", "url", "tier", "connector", "license", "license_url", "terms", "notes", "last_checked", "last_changed", "data_as_of", "status")} for source in view["sources"]],
            "observations": [{"id": o["id"], "snapshot_id": o["snapshot_id"], "source_id": o["source_id"], "revision": o["revision"], "observed_at": o["observed_at"]} for o in view["observations"]],
            "polls": [{"id": p["id"], "snapshot_id": p["snapshot_id"], "study_id": p["study_id"], "source_id": p["source_id"]} for p in view["polls"]],
            "limitations": ["Aggregate research output; no individual voter records.", "Source quality, cutoff chronology, geography, and voting definitions constrain comparisons."]}


def csv_data(view: dict) -> bytes:
    output = io.StringIO(newline="")
    fields = ["id", "state", "cycle", "election_date", "date", "metric", "value", "unit", "geography_id", "geography_name", "geography_type", "mode", "category_dimension", "category", "time_basis", "published_at", "observed_at", "source_id", "snapshot_id", "revision"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    query = view["query"]
    # Export current/baseline evidence, with the exact selected grain and dimensions.
    for row in view["observations"]:
        if row["cycle"] not in {query["cycle"], query["baseline"]} or row["metric"] != query["metric"] or row["mode"] != query["mode"] or row["time_basis"] != query["time_basis"]:
            continue
        if query.get("geography_ids") and row["geography_id"] not in query["geography_ids"]:
            continue
        if row.get("category_dimension") != query.get("category_dimension") or row.get("category") != query.get("category"):
            continue
        safe = {key: ("'" + value if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"} else value) for key, value in row.items()}
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")


def html_report(view: dict, *, sections: list[str] | None = None, notes: list[dict] | None = None,
                title: str | None = None) -> bytes:
    selected = _sections(sections)
    title = title or f"{view['state']['name']} Senate research dossier"

    def esc(value):
        return html.escape(str(value if value is not None else "Not published"))

    content = [f"<h1>{esc(title)}</h1><p>Evidence revision {view['revision']} · Cutoff {esc(view['query']['as_of'] or 'latest validated evidence')} · {esc(view['query']['time_basis'])}</p>"]
    for section_id in selected:
        content.append(f"<section data-section='{section_id}'>")
        if section_id == "overview":
            for section in view["brief"]:
                content.append(f"<h2>{esc(section['title'])}</h2><p>{esc(section['text'])}</p>")
        elif section_id == "voting":
            content.append("<h2>Voting trajectories</h2>" + trajectory_svg(view))
            content.append("<p>Step lines connect actual observations. Reporting gaps remain visible in the observation dates; no intervening ballot counts are estimated.</p><table><thead><tr><th>Cycle</th><th>Date</th><th>Metric</th><th>Value</th><th>Evidence</th></tr></thead><tbody>")
            for point in view["series"]:
                content.append(f"<tr><td>{point['cycle']}</td><td>{esc(point['date'])}</td><td>{esc(view['query']['metric'])}</td><td>{point['value']:,.0f}</td><td>{esc(', '.join(point['source_ids']))}</td></tr>")
            content.append("</tbody></table>")
        elif section_id == "geography":
            content.append("<h2>Geographic observations</h2><table><tr><th>Place</th><th>Value</th><th>Baseline</th><th>Date</th></tr>")
            for place in sorted(view["geographies"], key=lambda r: r["value"], reverse=True):
                content.append(f"<tr><td>{esc(place['name'])}</td><td>{place['value']:,.0f}</td><td>{esc(place['baseline_value'])}</td><td>{esc(place.get('date'))}</td></tr>")
            content.append("</table>")
        elif section_id == "polls":
            content.append("<h2>Original polling studies</h2>")
            for poll in view["polls"]:
                estimates = "; ".join(f"{e.get('candidate', e.get('name', 'Response'))}: {e.get('value')}%" for e in poll["estimates"])
                content.append(f"<p><strong>{esc(poll['producer'])}</strong> · {esc(poll['population'])} · {esc(poll['field_start'])}–{esc(poll['field_end'])}<br>{esc(poll['question'])}<br>{esc(estimates)}<br><a href='{esc(poll['source_url'])}'>Original release</a></p>")
            if not view["polls"]:
                content.append("<p>No original surveys are collected for this selection.</p>")
        elif section_id == "sources":
            content.append("<h2>Sources and coverage</h2>")
            for source in view["sources"]:
                content.append(f"<p><a href='{esc(source['url'])}'>{esc(source['name'])}</a> · {esc(source['status'])} · Data as of {esc(source.get('data_as_of'))}<br>{esc(source.get('license') or '')}</p>")
        content.append("</section>")
    if notes:
        content.append("<h2>Selected personal notes</h2><p>Researcher interpretation, separate from reported evidence.</p>")
        for note in notes:
            content.append(f"<h3>{esc(note['title'])}</h3><p>{esc(note['body'])}</p>")
    content.append("<h2>Limitations</h2><ul>" + "".join(f"<li>{esc(warning)}</li>" for warning in view["warnings"]) + "</ul>")
    report_manifest = {**manifest(view), "report": {"title": title, "sections": selected, "private_notes_included": bool(notes)}}
    content.append("<details><summary>Reproducibility manifest</summary><pre>" + esc(json.dumps(report_manifest, indent=2)) + "</pre></details>")
    style = "body{font:15px/1.6 system-ui;color:#14233b;max-width:1100px;margin:40px auto;padding:20px}h1{font-size:32px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;text-align:left;border-bottom:1px solid #d4dee9}th{background:#edf3f9}a{color:#075c8c}pre{white-space:pre-wrap;font-size:11px}svg{width:100%;font:12px system-ui}@media print{details{display:block}a{color:inherit}h2{break-after:avoid}tr{break-inside:avoid}}"
    return f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>{esc(title)}</title><style>{style}</style><body>{''.join(content)}</body></html>".encode()


def pdf_report(view: dict, *, sections: list[str] | None = None, notes: list[dict] | None = None,
               title: str | None = None) -> bytes:
    selected = _sections(sections)
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    styles["Heading2"].keepWithNext = True
    styles["Heading3"].keepWithNext = True
    story = [Paragraph(escape(title or f"{view['state']['name']} Senate research dossier"), styles["Title"]),
             Paragraph(escape(f"Evidence revision {view['revision']} | {view['query']['time_basis']} | cutoff {view['query']['as_of'] or 'latest'}"), styles["Normal"]), Spacer(1, 15)]

    def table(rows, widths=None):
        result = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102033")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("GRID", (0, 0), (-1, -1), .25, colors.lightgrey)]))
        return result

    for section_id in selected:
        if section_id == "overview":
            for section in view["brief"]:
                story += [Paragraph(escape(section["title"]), styles["Heading2"]), Paragraph(escape(section["text"]), styles["BodyText"])]
        elif section_id == "voting":
            story.append(Paragraph("Voting trajectories", styles["Heading2"]))
            chart = chart_geometry(view, 510, 220)
            if chart["lines"]:
                drawing = Drawing(510, 220)
                drawing.add(Rect(0, 0, 510, 220, fillColor=colors.white, strokeColor=None))
                for fraction in (0, .25, .5, .75, 1):
                    y = 220 - chart["bottom"] + fraction * (chart["bottom"] - chart["top"])
                    drawing.add(Line(chart["left"], y, chart["right"], y, strokeColor=colors.HexColor("#d9e3ed")))
                    drawing.add(String(68, y, f"{fraction * chart['ymax']:,.0f}", textAnchor="end", fontName="Helvetica", fontSize=8))
                for index, line in enumerate(chart["lines"]):
                    points = [coordinate for x, y in line["points"] for coordinate in (x, 220-y)]
                    drawing.add(PolyLine(points, strokeColor=colors.HexColor(line["color"]), strokeWidth=2))
                    drawing.add(String(90 + index * 75, 205, str(line["cycle"]), fillColor=colors.HexColor(line["color"]), fontName="Helvetica", fontSize=9))
                drawing.add(String(75, 18, f"{-chart['xmin']:g} to {-chart['xmax']:g} days before Election Day", fontName="Helvetica", fontSize=8))
                story += [drawing, Paragraph("Step lines connect actual observations. No intermediate ballot counts are estimated.", styles["BodyText"])]
                story.append(table([["Cycle", "Date", "Measure", "Value"]] + [[str(p["cycle"]), p["date"], view["query"]["metric"].replace("_", " "), f"{p['value']:,.0f}"] for p in view["series"]]))
            else:
                story.append(Paragraph("No voting trajectory is supported by this selection.", styles["BodyText"]))
        elif section_id == "geography":
            story.append(Paragraph("Geographic observations", styles["Heading2"]))
            rows = [["Place", "Value", "Baseline", "Date"]]
            rows += [[p["name"], f"{p['value']:,.0f}", f"{p['baseline_value']:,.0f}" if p.get("baseline_value") is not None else "Unavailable", p.get("date", "")] for p in sorted(view["geographies"], key=lambda r: r["value"], reverse=True)]
            story.append(table(rows))
        elif section_id == "polls":
            story.append(Paragraph("Original polling studies", styles["Heading2"]))
            for poll in view["polls"]:
                shares = "; ".join(f"{e.get('candidate', e.get('name', 'Response'))}: {e.get('value')}%" for e in poll["estimates"])
                story += [Paragraph(escape(poll["producer"]), styles["Heading3"]), Paragraph(escape(f"{poll['population']} | {poll['field_start']} to {poll['field_end']}"), styles["BodyText"]), Paragraph(escape(poll["question"]), styles["BodyText"]), Paragraph(escape(shares), styles["BodyText"]), Paragraph(escape(poll["source_url"]), styles["BodyText"])]
            if not view["polls"]:
                story.append(Paragraph("No original surveys collected for this selection.", styles["BodyText"]))
        elif section_id == "sources":
            story.append(Paragraph("Source appendix", styles["Heading2"]))
            for source in view["sources"]:
                story += [Paragraph(escape(source["name"]), styles["Heading3"]), Paragraph(escape(source["url"]), styles["BodyText"]), Paragraph(escape(f"Status: {source['status']} | Data date: {source.get('data_as_of') or 'unknown'} | {source.get('license') or ''}"), styles["BodyText"])]
    if notes:
        story.append(Paragraph("Selected personal notes - researcher interpretation", styles["Heading2"]))
        for note in notes:
            story += [Paragraph(escape(note["title"]), styles["Heading3"]), Paragraph(escape(note["body"]), styles["BodyText"])]
    story.append(Paragraph("Limitations", styles["Heading2"]))
    for warning in view["warnings"]:
        story.append(Paragraph(escape(warning), styles["BodyText"]))
    def footer(canvas, _document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#61738b"))
        canvas.drawString(36, 20, f"Battleground Senate Observatory | Revision {view['revision']}")
        canvas.drawRightString(A4[0] - 36, 20, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def research_bundle(view: dict, *, extra_manifest: dict | None = None, notes: list[dict] | None = None,
                    sections: list[str] | None = None, title: str | None = None) -> bytes:
    selected = _sections(sections)
    report_manifest = {**manifest(view), **(extra_manifest or {}), "report": {"title": title, "sections": selected, "private_notes_included": bool(notes)}}
    if notes:
        report_manifest["selected_notes"] = notes
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("observations.csv", csv_data(view))
        archive.writestr("workspace.json", json.dumps(view, indent=2))
        archive.writestr("manifest.json", json.dumps(report_manifest, indent=2))
        archive.writestr("report.html", html_report(view, notes=notes, sections=selected, title=title))
        archive.writestr("README.txt", "Aggregate evidence package. Query and dataset revision are pinned in manifest.json. Original sources and their hashes are documented; no voter-level data is included. Reopen this query in the local Observatory for interactive inspection.\n")
    return output.getvalue()
