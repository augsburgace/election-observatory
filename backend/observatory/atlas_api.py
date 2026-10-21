"""Versioned atlas interfaces; legacy investigations keep their original contracts."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import zipfile
from html import escape
from typing import Literal

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, cast, func, select

from .atlas import (
    availability,
    context_query,
    core_install,
    dataset_catalog,
    load_dataset,
    result_query,
    search,
    state_catalog,
)
from .atlas.models import BallotOption, Contest, Election, ElectionResult, GeographyVersion, ensure_schema
from .atlas.result_validation import invalidated_result_contests, result_validation_warnings
from .atlas_analysis import result_analysis
from .collector import collect_sources
from .db import Job, Snapshot, record_dict
from .domain import ResearchQuery, utc_now
from .ev_forecast import early_vote_forecasts
from .ev_history import stage_history
from .forecast_reasoning import forecast_reasoning
from .historical_comparisons import compare_results
from .participation_catalog import participation_datasets
from .participation_quality import participation_quality
from .precincts import load_precinct_dataset, precinct_catalog, precinct_map
from .public_access import public_payload, public_report_document
from .registry import all_states
from .report_composer import ReportRequest, compose_report, export_report
from .service import capabilities, compact_workspace, per_place_series, workspace
from .settings import PROJECT_ROOT

logger = logging.getLogger(__name__)


class DatasetLoadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str | None = None


def result_parameters(state: str | None = None, year: int = 2024, office: str = "PRESIDENT",
                      contest_id: str | None = None, baseline: int | None = 2020,
                      geography_level: Literal["state", "county", "district", "municipality", "precinct"] = "county",
                      revision: int | None = Query(default=None, ge=0), geography_ids: str = "",
                      offset: int = Query(0, ge=0), limit: int | None = Query(None, ge=1, le=200)) -> dict:
    if not 1700 <= year <= 2100 or (baseline is not None and not 1700 <= baseline <= 2100):
        raise ValueError("Choose a documented election year")
    if state:
        state = state.upper()
        if state not in {s["code"] for s in all_states()}:
            raise ValueError("Unknown state")
    return {"state": state, "year": year, "office": office.upper(), "contest_id": contest_id,
            "baseline": baseline, "geography_level": geography_level, "revision": revision,
            "geography_ids": [p for p in geography_ids.split(",") if p], "offset": offset, "limit": limit}


def _public_sources(view):
    return [{k: v for k, v in s.items() if k != "path"} for s in view.get("sources", [])]


def _result_export(view, format, presentation=None):
    """Exports use exactly the same calculation as the renderer and table."""
    view = {**view, "sources": _public_sources(view)}
    reproducibility = {"schema": "observatory-atlas-research-v1", "created_at": utc_now(),
        "dataset_revision": view["revision"], "query": view["query"], "unit": "candidate votes",
        "source_snapshots": view["sources"], "margin_definitions": view["margin_definition"],
        "coverage": view["coverage"], "limitations": view["warnings"],
        "application": "Battleground Senate Observatory", "private_notes_included": False}
    reproducibility["presentation"] = presentation or {}
    from .atlas.ingest import PARSER_VERSION
    code_files = sorted((PROJECT_ROOT / "backend" / "observatory").rglob("*.py"))
    reproducibility.update({"application_version": "0.1.0",
        "application_build_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in code_files)).hexdigest(),
        "export_runtime_parser_version": PARSER_VERSION,
        "parser_version_note": "Runtime version; historical rows without a recorded extraction version remain unknown.",
        "metric_definition": "Published candidate or ballot-option votes in a particular contest and round; not ballots cast or unique voters.",
        "visualization_note": "This package reproduces aggregate calculations. Exported chart and map images retain their visible legends separately."})
    reproducibility["boundary_assets"] = {}
    for name in ("manifest.json", "cities-manifest.json"):
        path = PROJECT_ROOT / "frontend" / "public" / "geography" / name
        if path.exists():
            reproducibility["boundary_assets"][name] = json.loads(path.read_text())
    reproducibility["result_sha256"] = hashlib.sha256(json.dumps(view, sort_keys=True).encode()).hexdigest()
    stream = io.StringIO(newline="")
    fields = ["geography_id", "geography_name", "contest_id", "option_id", "option", "party", "votes", "share_pct", "total_candidate_votes", "dem_margin_pp", "swing_pp"]
    def safe_csv(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for area in view["geographies"]:
        for option in area["options"]:
            writer.writerow(dict(zip(fields, [safe_csv(value) for value in [area["id"], area["name"], area["contest_id"], option["id"],
                option["name"], option["party"], option["votes"], option["share_pct"], area["total_votes"],
                area["dem_margin_pp"], area["swing_pp"]]])))
    csv_bytes = stream.getvalue().encode("utf-8-sig")
    body_rows = "".join("<tr>" + "".join(f"<td>{escape(str(v if v is not None else 'Unavailable'))}</td>" for v in
        [r["name"], r["total_votes"], r["winner"]["name"] if r["winner"] else None,
         round(r["dem_margin_pp"], 2) if r["dem_margin_pp"] is not None else None,
         round(r["swing_pp"], 2) if r["swing_pp"] is not None else None]) + "</tr>" for r in view["geographies"])
    title = f"{view['query']['state'] or 'United States'} · {view['query']['year']} {view['query']['office']}"
    manifest_json = json.dumps(reproducibility).replace("<", "\\u003c")
    from .atlas_reporting import report_footer, result_figures_svg, result_pdf_figures
    html = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{escape(title)}</title>'
        '<style>body{font:16px system-ui;color:#142539;max-width:1100px;margin:40px auto;padding:20px}h1{font-family:Georgia}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:10px;border-bottom:1px solid #d6dfe7}th{background:#e9f4f2}li{margin:8px 0}@media print{body{margin:0}}</style>'
        f'<h1>{escape(title)}</h1><p>Dataset revision {view["revision"]}. Unit: candidate votes. Final results are historical election context.</p>' + result_figures_svg(view) +
        '<table><thead><tr><th>Place</th><th>Candidate votes</th><th>Leading option</th><th>D − R, pp</th><th>Change in D − R, pp</th></tr></thead>'
        f'<tbody>{body_rows}</tbody></table><h2>Evidence and limitations</h2><ul>' +
        ''.join(f'<li>{escape(w)}</li>' for w in view['warnings']) + '</ul><h2>Original records</h2><ul>' +
        ''.join(f'<li>Snapshot {s["id"]} · SHA-256 {escape(s["sha256"])} · <a href="{escape(s["url"])}">Source</a></li>' for s in view['sources']) +
        f'</ul><script type="application/json" id="research-manifest">{manifest_json}</script></html>')
    if format == "csv":
        return csv_bytes, "text/csv"
    if format == "html":
        return html.encode(), "text/html"
    if format == "json":
        return json.dumps({"results": view, "manifest": reproducibility}, indent=2).encode(), "application/json"
    if format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        output = io.BytesIO()
        styles = getSampleStyleSheet()
        story = [Paragraph(escape(title), styles["Title"]), Paragraph(f"Revision {view['revision']} · Final candidate returns", styles["Normal"]), Spacer(1, 14)]
        story.extend(result_pdf_figures(view))
        table_rows = [["Place", "Candidate votes", "D - R (pp)"]]
        table_rows += [[r["name"], f"{r['total_votes']:,.0f}", f"{r['dem_margin_pp']:+.2f}" if r['dem_margin_pp'] is not None else "Unavailable"] for r in view["geographies"]]
        table = Table(table_rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e0f2ef")), ("FONTNAME", (0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),9), ("BOTTOMPADDING",(0,0),(-1,-1),8), ("LINEBELOW",(0,0),(-1,-1),0.3,colors.lightgrey)]))
        story.extend([table, Spacer(1,16), Paragraph("Evidence and limitations", styles["Heading2"])])
        story += [Paragraph(escape(w), styles["Normal"]) for w in view["warnings"]]
        story += [Paragraph(escape(f"Snapshot {s['id']} | {s['url']} | SHA256 {s['sha256']}"), styles["Normal"]) for s in view["sources"]]
        def footer(canvas, doc):
            report_footer(canvas, doc, view['revision'])
        SimpleDocTemplate(output, title=title, author="Battleground Senate Observatory").build(story,onFirstPage=footer,onLaterPages=footer)
        return output.getvalue(), "application/pdf"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(reproducibility, indent=2))
        archive.writestr("results.json", json.dumps(view, indent=2))
        archive.writestr("results.csv", csv_bytes)
        archive.writestr("report.html", html)
        archive.writestr("saved_view.json", json.dumps({"revision": view["revision"], "query": view["query"],
                                                     "presentation": presentation or {}}, indent=2))
    return output.getvalue(), "application/zip"


def register_atlas_routes(app, database, executor, query_dependency):
    ensure_schema(database)
    public_mode = database.settings.public_mode

    def state_code(value):
        value = value.upper() if value else value
        if value and value not in {row["code"] for row in all_states()}:
            raise ValueError("Unknown state")
        return value

    def revision_bound(value):
        latest = database.latest_revision()
        if value is not None and (value < 0 or value > latest):
            raise ValueError("The requested dataset revision does not exist")
        return latest if value is None else value

    def public_view(value):
        value = {**value, "sources": _public_sources(value)} if "sources" in value else value
        return public_payload(value) if public_mode else value

    def presentation_state(value):
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("View state must be a JSON object") from exc
        if not isinstance(parsed, dict) or len(parsed) > 100:
            raise ValueError("View state must be a bounded JSON object")
        allowed = {"layer", "option_id", "legend", "selected_geographies", "viewport", "sort", "layout"}
        safe_prefixes = ("ui_atlas_", "ui_results_", "ui_result_", "ui_context_", "ui_map_", "ui_geo_", "ui_history_", "ui_comparison_", "ui_precinct_")
        def public_key(key):
            return key.startswith(safe_prefixes) or key in {"ui_question", "ui_density", "ui_place", "ui_entity"}
        output = {k: v for k, v in parsed.items() if public_key(k) or k in allowed}
        if isinstance(output.get("layout"), dict):
            output["layout"] = {k: v for k, v in output["layout"].items() if public_key(k)}
        return output

    def combined_datasets(state=None):
        catalog = dataset_catalog(database, state)
        precinct = [{**s, "name": s["title"], "on_demand": True, "states": [s["state"]],
            "loaded_states": [s["state"]] if s["loaded"] else [], "provider": "precinct"}
            for s in precinct_catalog(database, state=state)["datasets"]]
        return {**catalog, "datasets": catalog["datasets"] + participation_datasets(database, state) + precinct}

    @app.get("/api/v2/participation/quality")
    def ev_quality(query: ResearchQuery = Depends(query_dependency)):
        return participation_quality(database, query)

    @app.get("/api/v2/forecasts/early-vote")
    def ev_calls(state: str = "NC", revision: int | None = None, as_of: str | None = None, cycle: int = 2026):
        return early_vote_forecasts(database, state=state_code(state), revision=revision_bound(revision), as_of=as_of, cycle=cycle)

    @app.get("/api/v2/forecasts/reasoning")
    def ev_reasoning(state: str = "OH", revision: int | None = None, as_of: str | None = None,
                     cycle: int = 2026, include_polls: bool = False, include_markets: bool = False,
                     include_context: bool = False, race_id: str | None = None):
        return forecast_reasoning(database, state=state_code(state), revision=revision_bound(revision),
            as_of=as_of, cycle=cycle, include_polls=include_polls, include_markets=include_markets,
            include_context=include_context, race_id=race_id)

    @app.get("/api/v2/forecasts/feature-tests")
    def ev_feature_tests(state: str = "OH", revision: int | None = None, as_of: str | None = None, cycle: int = 2026):
        from .ev_feature_validation import build_feature_validation
        run = early_vote_forecasts(database, state=state_code(state), revision=revision_bound(revision), as_of=as_of, cycle=cycle)
        return build_feature_validation(database, run["revision"], run["as_of"], backtesting=run["backtesting"])

    @app.get("/api/v2/early-vote/history")
    def ev_stage_history(state: str = "NC", cycle: int = Query(2026, ge=1976, le=2100),
                         revision: int | None = None, as_of: str | None = None,
                         metric: str | None = None, mode: str | None = None,
                         alignment: Literal["days_to_election", "days_since_opening"] = "days_to_election",
                         history_basis: Literal["retrospective", "reported"] = "retrospective",
                         baseline_cycles: str = "2016,2018,2020,2022,2024"):
        return stage_history(database, state=state_code(state), cycle=cycle, revision=revision_bound(revision),
            as_of=as_of, metric=metric, mode=mode, alignment=alignment, history_basis=history_basis,
            baseline_cycles=[int(value) for value in baseline_cycles.split(",") if value.strip()])

    @app.post("/api/v2/reports/preview")
    def report_preview(body: ReportRequest):
        if public_mode:
            from .report_composer import SECTION_CATALOG, TEMPLATES, _html
            document = public_report_document(database, body)
            return {k: v for k, v in document.items() if k != "evidence"} | {
                "html": _html(document).decode(), "templates": TEMPLATES, "catalog": SECTION_CATALOG}
        return compose_report(database, body)

    @app.post("/api/v2/reports/exports")
    def report_exports(body: ReportRequest, format: Literal["html", "pdf", "csv", "json", "zip"] = "pdf"):
        if public_mode:
            from .report_composer import _render_export
            content, mime = _render_export(public_report_document(database, body), format)
        else:
            content, mime = export_report(database, body, format)
        return Response(content, media_type=mime, headers={"Content-Disposition":
            f'attachment; filename="research-report-{body.query.state}.{format}"'})

    @app.get("/api/v2/precincts/catalog")
    def precinct_inventory(state: str | None = None, year: int | None = None, revision: int | None = None):
        return precinct_catalog(database, state=state_code(state), year=year, revision=revision_bound(revision))

    @app.get("/api/v2/precincts/map")
    def native_precincts(state: str, year: int = 2020, office: str = "PRESIDENT", dataset_id: str | None = None,
                        revision: int | None = None, bbox: str | None = None,
                        lod: Literal["overview", "detail", "full"] = "overview", contest_id: str | None = None,
                        limit: int = Query(20000, ge=1, le=20000)):
        return precinct_map(database, state=state_code(state), year=year, office=office.upper(), dataset_id=dataset_id,
            revision=revision_bound(revision), bbox=bbox, lod=lod, contest_id=contest_id, limit=limit)

    @app.post("/api/v2/precincts/{dataset_id}/load", status_code=202)
    def download_precincts(dataset_id: str):
        source = next((s for s in precinct_catalog(database)["datasets"] if s["id"] == dataset_id), None)
        if not source:
            raise HTTPException(404, "Unknown verified precinct source")
        return download(dataset_id, DatasetLoadInput(state=source["state"]))

    @app.get("/api/v2/comparisons/results")
    def historical_pairs(state: str, year: int = 2024, baseline: int = 2020, office: str = "PRESIDENT",
                         geography_level: Literal["state", "county", "district", "municipality", "precinct"] = "county",
                         revision: int | None = None, contest_id: str | None = None, geography_ids: str = "",
                         limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
        return compare_results(database, state=state_code(state), year=year, baseline=baseline, office=office.upper(),
            geography_level=geography_level, revision=revision_bound(revision), contest_id=contest_id,
            geography_ids=[p for p in geography_ids.split(",") if p], limit=limit, offset=offset)

    @app.get("/api/v2/catalog/states")
    def states():
        return state_catalog(database)

    @app.get("/api/v2/catalog/datasets")
    def datasets(state: str | None = None):
        return combined_datasets(state_code(state))

    @app.get("/api/v2/catalog/availability/{state}")
    def available(state: str, revision: int | None = None):
        state = state_code(state)
        return {**availability(database, state), "participation": capabilities(database, state, revision=revision_bound(revision))}

    @app.get("/api/v2/catalog/elections")
    def elections(state: str | None = None, year: int | None = None, revision: int | None = None,
                  offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        state = state_code(state)
        bound = revision_bound(revision)
        known = select(ElectionResult.id).join(Contest, Contest.id == ElectionResult.contest_id).where(
            Contest.election_id == Election.id, ElectionResult.revision <= bound).exists()
        invalidated = invalidated_result_contests(database, bound)
        if invalidated:
            known = select(ElectionResult.id).join(Contest, Contest.id == ElectionResult.contest_id).where(
                Contest.election_id == Election.id, ElectionResult.revision <= bound,
                Contest.id.not_in(invalidated)).exists()
        statement = select(Election).where(known)
        if state:
            statement = statement.where(Election.state == state.upper())
        if year:
            statement = statement.where(Election.year == year)
        with database.session() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = [record_dict(r) for r in session.scalars(statement.order_by(Election.year.desc(), Election.state).offset(offset).limit(limit))]
        return {"revision": bound, "total": total, "elections": rows, "offset": offset, "limit": limit}

    @app.get("/api/v2/catalog/contests")
    def contests(state: str | None = None, year: int | None = None, office: str | None = None,
                 q: str = "", revision: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        state = state_code(state)
        bound = revision_bound(revision)
        known = select(ElectionResult.id).where(ElectionResult.contest_id == Contest.id,
            ElectionResult.revision <= bound).exists()
        statement = select(Contest).where(known)
        invalidated = invalidated_result_contests(database, bound)
        if invalidated:
            statement = statement.where(Contest.id.not_in(invalidated))
        if state:
            statement = statement.where(Contest.state == state.upper())
        if year:
            statement = statement.where(Contest.year == year)
        if office:
            statement = statement.where(Contest.office == office.upper())
        if q:
            statement = statement.where(Contest.name.ilike(f"%{q[:100]}%"))
        with database.session() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = [record_dict(r) for r in session.scalars(statement.order_by(Contest.year.desc(), Contest.office, Contest.name).offset(offset).limit(limit))]
        return {"revision": bound, "total": total, "contests": rows, "offset": offset, "limit": limit}

    @app.get("/api/v2/search")
    def find(q: str = "", state: str | None = None, limit: int = Query(30, ge=1, le=100)):
        return search(database, q, state_code(state), limit, include_research=not public_mode)

    @app.get("/api/v2/results")
    def results(query: dict = Depends(result_parameters)):
        query["revision"] = revision_bound(query["revision"])
        return public_view(result_query(database, **query))

    @app.get("/api/v2/analysis/results")
    def results_analysis(query: dict = Depends(result_parameters)):
        query["revision"] = revision_bound(query["revision"])
        return public_view(result_analysis(database, **query))

    @app.get("/api/v2/results/exports")
    def results_export(format: Literal["csv", "json", "html", "pdf", "zip"] = "csv", query: dict = Depends(result_parameters),
                       view_state: str | None = Query(None, max_length=32768)):
        query["revision"] = revision_bound(query["revision"])
        view = result_query(database, **query)
        if public_mode:
            view = public_payload(view)
        content, media = _result_export(view, format, presentation_state(view_state))
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="atlas-{query["state"] or "US"}-{query["year"]}-r{view["revision"]}.{format}"'})

    @app.get("/api/v2/context")
    def context(state: str | None = None, geography_id: str | None = None, metric: str | None = None, revision: int | None = None):
        return public_view(context_query(database, state_code(state), geography_id, metric, revision_bound(revision)))

    @app.get("/api/v2/context/exports")
    def context_export(format: Literal["csv", "json", "html", "pdf", "zip"] = "csv",
                       state: str | None = None, geography_id: str | None = None,
                       metric: str | None = None, revision: int | None = None,
                       view_state: str | None = Query(None, max_length=32768)):
        from .atlas_reporting import context_export as render_context
        view = context_query(database, state_code(state), geography_id, metric, revision_bound(revision))
        if public_mode:
            view = public_payload(view)
        content, media = render_context(view, format, presentation_state(view_state))
        return Response(content, media_type=media, headers={"Content-Disposition":
            f'attachment; filename="census-context-{state or "US"}-r{view["revision"]}.{format}"'})

    @app.get("/api/v2/geographies")
    def geographies(state: str, level: str | None = None, vintage: str | None = None,
                    q: str = "", revision: int | None = None,
                    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        state, bound = state_code(state), revision_bound(revision)
        # Materialize known pairs once. A correlated EXISTS can repeatedly scan
        # hundreds of thousands of state rows for each geographic version.
        known = select(ElectionResult.geography_id.label("geography_id"), ElectionResult.year.label("year")).where(
            ElectionResult.state == state, ElectionResult.revision <= bound).distinct().subquery()
        statement = select(GeographyVersion).join(known,
            (GeographyVersion.geography_id == known.c.geography_id) &
            (cast(GeographyVersion.vintage, Integer) == known.c.year)).where(GeographyVersion.state == state)
        if level:
            statement = statement.where(GeographyVersion.level == level)
        if vintage:
            statement = statement.where(GeographyVersion.vintage == vintage)
        if q:
            statement = statement.where(GeographyVersion.name.ilike(f"%{q[:100]}%"))
        with database.session() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = [record_dict(g) for g in session.scalars(statement.order_by(GeographyVersion.level,
                GeographyVersion.name, GeographyVersion.vintage.desc()).offset(offset).limit(limit))]
        return {"revision": bound, "state": state, "geographies": rows, "total": total,
                "offset": offset, "limit": limit,
                "boundary_service": f"/api/v1/geography/{state}", "boundary_vintage": "2024",
                "warnings": ["Precinct result identifiers do not establish boundary matches.",
                    "Older geographic versions may be inspectable without a matching current polygon."]}

    @app.get("/api/v2/denominators")
    def denominators(state: str, revision: int | None = None, as_of: str | None = None):
        state, bound = state_code(state), revision_bound(revision)
        rows = database.observations(state=state, revision=bound, metric="registered_voters", cutoff=as_of)
        rows = [r for r in rows if not r.get("category_dimension")]
        return {"revision": bound, "state": state, "as_of": as_of, "denominators": rows,
                "status": "available" if rows else "unavailable",
                "warnings": ["Registration counts retain their publication date and active/all definition.",
                    "ACS resident population and historical final candidate votes are not current registration denominators."]}

    @app.get("/api/v2/workspace")
    @app.get("/api/v2/analytics")
    def analytics(query: ResearchQuery = Depends(query_dependency)):
        view = compact_workspace(database, query)
        places = view.get("geographic_research") or per_place_series(database, query)
        return {**view, "geographic_research": places, "series_by_place": places.get("places", [])}

    @app.get("/api/v2/trajectories")
    def trajectories(query: ResearchQuery = Depends(query_dependency)):
        return per_place_series(database, query)

    @app.get("/api/v2/observations")
    def observations(query: ResearchQuery = Depends(query_dependency), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        view = workspace(database, query)
        selected_ids = set(view["observation_scope"]["mode_context_ids"])
        rows = [row for row in view["observations"] if row["id"] not in selected_ids]
        return {"revision": view["revision"], "query": view["query"], "total": len(rows),
                "offset": offset, "limit": limit, "observations": rows[offset:offset + limit],
                "scope": "Selected current and aligned baseline observations; separately labeled mode-context rows are excluded.",
                "warnings": view["warnings"]}

    @app.get("/api/v2/places/{geography_id:path}")
    def place(geography_id: str, state: str, year: int = 2024, revision: int | None = None,
              office: str = "PRESIDENT", history_offset: int = Query(0, ge=0),
              participation_query: ResearchQuery = Depends(query_dependency),
              history_limit: int = Query(8, ge=1, le=20)):
        state, revision = state_code(state), revision_bound(revision)
        level = geography_id.split(":", 1)[0]
        if level not in {"state", "county", "district", "municipality", "precinct"}:
            level = "municipality"
        with database.session() as session:
            years = list(session.scalars(select(ElectionResult.year).where(
                ElectionResult.geography_id == geography_id, ElectionResult.state == state,
                ElectionResult.office == office.upper(), ElectionResult.revision <= revision
            ).distinct().order_by(ElectionResult.year.desc())))
            versions = [record_dict(g) for g in session.scalars(select(GeographyVersion).where(
                GeographyVersion.geography_id == geography_id, GeographyVersion.state == state
            ).order_by(GeographyVersion.vintage)) if str(g.vintage).isdigit() and int(g.vintage) in years]
        page_years = years[history_offset:history_offset + history_limit]
        history = [public_view(result_query(database, state=state, year=y, office=office, baseline=None,
            geography_level=level, revision=revision, geography_ids=[geography_id])) for y in page_years]
        participation = per_place_series(database, participation_query.model_copy(update={
            "state": state, "geography_ids": [geography_id], "revision": revision}))
        context = public_view(context_query(database, state=state, geography_id=geography_id, revision=revision))
        return {"revision": revision, "geography_id": geography_id, "state": state, "year": year, "office": office.upper(),
                "versions": versions, "history": history, "history_page": {"total": len(years), "offset": history_offset,
                    "limit": history_limit, "years": page_years, "has_more": history_offset + history_limit < len(years)},
                "context": context, "participation": participation,
                "warnings": ["Historical candidate returns, current participation, and resident context describe separate quantities.",
                    "History is paginated by observed election year; use history_offset to retrieve earlier evidence."]}

    @app.get("/api/v2/contests/{contest_id}")
    def contest(contest_id: str, revision: int | None = None):
        revision = revision_bound(revision)
        with database.session() as session:
            record = session.get(Contest, contest_id)
            if not record:
                raise HTTPException(404, "Contest not found in collected evidence")
            meta = record_dict(record)
            options = [record_dict(o) for o in session.scalars(select(BallotOption).where(BallotOption.contest_id == contest_id))]
        results = public_view(result_query(database, state=meta['state'], year=meta['year'], office=meta['office'],
            contest_id=contest_id, baseline=None, geography_level='state', revision=revision))
        if not results["geographies"]:
            for grain in ("district", "municipality", "county", "precinct"):
                fallback = public_view(result_query(database, state=meta['state'], year=meta['year'], office=meta['office'],
                    contest_id=contest_id, baseline=None, geography_level=grain, revision=revision))
                if fallback["geographies"]:
                    results = fallback
                    break
        if not results["geographies"]:
            raise HTTPException(404, "Contest has no result evidence in the requested revision")
        allowed_options = {option["id"] for area in results["geographies"] for option in area["options"]}
        return {"revision": revision, "contest": meta, "options": [o for o in options if o["id"] in allowed_options], "results": results}

    @app.get("/api/v2/candidates/{option_id}")
    def candidate(option_id: str, revision: int | None = None):
        revision = revision_bound(revision)
        with database.session() as session:
            record = session.get(BallotOption, option_id)
            available = session.scalar(select(ElectionResult.id).where(ElectionResult.option_id == option_id,
                ElectionResult.revision <= revision).limit(1))
            if not record or available is None:
                raise HTTPException(404, "Ballot option not found in collected evidence")
            meta = record_dict(record)
            contest_meta = record_dict(session.get(Contest, record.contest_id))
        detail = contest(meta["contest_id"], revision=revision)
        results = detail["results"]
        option_results = [{"geography_id": area["id"], "geography_name": area["name"],
                           "level": area["level"], "unit": area["unit"], "round": area["round"],
                           "result": option}
                          for area in results["geographies"] for option in area["options"] if option["id"] == option_id]
        return {"revision": revision, "option": meta, "contest": contest_meta,
                "results": option_results, "sources": results["sources"], "warnings": results["warnings"],
                "coverage": results["coverage"],
                "identity_scope": "Party and ballot identity belong to this particular contest; similarly named people are not automatically merged."}

    @app.get("/api/v2/evidence/results/{result_id}")
    def result_evidence(result_id: int, revision: int | None = None):
        bound = revision_bound(revision)
        with database.session() as session:
            row = session.get(ElectionResult, result_id)
            if row is None or row.revision > bound:
                raise HTTPException(404, "Result evidence is unavailable at this revision")
            record = record_dict(row)
            snapshot = record_dict(session.get(Snapshot, row.snapshot_id))
            snapshot.pop("path", None)
            option = record_dict(session.get(BallotOption, row.option_id))
            contest_meta = record_dict(session.get(Contest, row.contest_id))
            versions = [record_dict(r) for r in session.scalars(select(ElectionResult).where(
                ElectionResult.logical_key == row.logical_key, ElectionResult.revision <= bound).order_by(ElectionResult.revision))]
        return {"revision": bound, "result": record, "option": option, "contest": contest_meta,
                "source_snapshot": snapshot, "revisions": versions,
                "archived_document": f"/api/v1/documents/{snapshot['id']}",
                "calculation": "Native reporting-unit candidate records are normalized by contest, option, method and geography. A published TOTAL supersedes its components; otherwise disjoint published components are summed. Suppressed counts remain incomplete.",
                "warnings": ["Candidate votes are not ballots cast or measured early-voter support.",
                    "Geographic aggregates retain their original source coverage and may differ from dedicated statewide compilations."]
                    + result_validation_warnings(database, [record], bound)}

    def run_load(job_id, dataset_id, body):
        def progress(payload):
            with database.session() as session:
                job = session.get(Job, job_id)
                update = dict(payload)
                if update.get("dataset_id") and update["dataset_id"] != job.progress.get("dataset_id"):
                    update["active_dataset_id"] = update.pop("dataset_id")
                job.progress = {**job.progress, **update}
                session.commit()
        with database.session() as session:
            job = session.get(Job, job_id)
            job.status, job.started_at = "running", utc_now()
            session.commit()
        try:
            progress({"stage": "collecting", "message": "Archiving and validating the original dataset. Existing evidence remains usable."})
            if dataset_id == "national_core":
                result = core_install(database, progress=progress)
                if result.get("datasets") and all(row.get("status") == "error" for row in result["datasets"]):
                    raise ValueError("All national reference downloads failed; previous validated evidence remains available")
            elif dataset_id.startswith("uf-fallback-"):
                result = collect_sources(database, source_ids=[dataset_id], job_id=job_id)
                if not result.get("successful"):
                    errors = "; ".join(row.get("error") or row.get("status", "unavailable") for row in result.get("sources", []))
                    raise ValueError(errors or "No validated participation observations were collected")
            elif any(s["id"] == dataset_id for s in precinct_catalog(database)["datasets"]):
                result = load_precinct_dataset(database, dataset_id, progress=progress)
            else:
                result = load_dataset(database, dataset_id, state=body.state, progress=progress)
            with database.session() as session:
                job = session.get(Job, job_id)
                job.status, job.finished_at, job.result = "completed", utc_now(), result
                job.progress = {**job.progress, "stage": "completed", "completed": 1, "total": 1}
                session.commit()
        except Exception as exc:
            logger.exception("Atlas collection failed")
            with database.session() as session:
                job = session.get(Job, job_id)
                job.status, job.finished_at, job.error = "failed", utc_now(), str(exc)[:2000]
                job.progress = {**job.progress, "stage": "failed", "message": "Previous validated evidence remains available."}
                session.commit()

    @app.post("/api/v2/datasets/{dataset_id}/load", status_code=202)
    def download(dataset_id: str, body: DatasetLoadInput = DatasetLoadInput()):
        selected_state = state_code(body.state)
        listed = combined_datasets()["datasets"]
        families = {source.get("family") for source in listed if source.get("family")}
        if dataset_id in families:
            if not selected_state:
                raise ValueError("Choose a state before downloading a state-level precinct dataset")
            dataset_id = f"{dataset_id}_{selected_state}"
        inventory = {source["id"]: source for source in listed}
        source = inventory.get(dataset_id)
        if not source and dataset_id != "national_core":
            raise HTTPException(404, "Dataset is not in the verified source inventory")
        if source and source.get("state"):
            if selected_state and selected_state != source["state"]:
                raise ValueError("The selected state does not match this dataset")
            selected_state = source["state"]
        else:
            selected_state = None  # A nationwide source is one job regardless of the current UI state.
        body = DatasetLoadInput(state=selected_state)
        with database.lock, database.session() as session:
            for active in session.scalars(select(Job).where(Job.kind == "atlas_download", Job.status.in_(["queued", "running"]))):
                if active.progress.get("dataset_id") == dataset_id and active.progress.get("state") == body.state:
                    return record_dict(active)
            job = Job(kind="atlas_download", status="queued", progress={"dataset_id": dataset_id, "state": body.state,
                      "stage": "queued", "message": "Waiting for the local collection worker"})
            session.add(job)
            session.commit()
            response, job_id = record_dict(job), job.id
        executor.submit(run_load, job_id, dataset_id, body)
        return response
