from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .collector import collect_sources
from .db import Correction, Database, Job, ObservationRecord, ResearchObject, Revision, Snapshot, record_dict
from .domain import ResearchQuery, utc_now
from .exports import csv_data, html_report, manifest, pdf_report, research_bundle
from .public_access import PublicAccessMiddleware, public_capabilities, public_payload
from .registry import all_states
from .service import bootstrap, source_inventory, workspace
from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


class ResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["note", "view", "bookmark", "scenario", "report", "correction"]
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(default="", max_length=100000)
    view: dict = Field(default_factory=dict)


class RefreshInput(BaseModel):
    source_ids: list[str] | None = None
    state: str | None = None
    include_historical: bool = False


class ExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: ResearchQuery
    format: Literal["csv", "json", "html", "pdf", "zip"] = "pdf"
    sections: list[Literal["overview", "voting", "geography", "polls", "sources"]] | None = None
    title: str | None = Field(default=None, max_length=240)
    note: str = Field(default="", max_length=100000)
    include_notes: bool = False


class CorrectionInput(BaseModel):
    observation_id: int
    replacement: float = Field(ge=0, allow_inf_nan=False)
    reason: str = Field(min_length=5, max_length=2000)


def query_parameters(state: str = "NC", cycle: int = 2026, baseline: int = 2022, as_of: str | None = None,
                     time_basis: Literal["reported", "reconstructed", "final"] = "reported", revision: int | None = None,
                     metric: str = "ballots_cast", mode: str = "all", geography_ids: str = "",
                     category_dimension: str | None = None, category: str | None = None,
                     alignment: str = "days_to_election", date_window: str | None = None) -> ResearchQuery:
    state = state.upper()
    if state not in {s["code"] for s in all_states()}:
        raise HTTPException(422, "Unknown state code")
    if cycle not in {2018, 2020, 2022, 2024, 2026} or baseline not in {2018, 2020, 2022, 2024, 2026}:
        raise HTTPException(422, "Unsupported election cycle")
    if as_of:
        try:
            date.fromisoformat(as_of[:10])
        except ValueError as exc:
            raise HTTPException(422, "Cutoff must be an ISO date") from exc
    if alignment not in {"days_to_election", "days_since_open", "days_since_opening", "voting_opportunities", "calendar"}:
        raise HTTPException(422, "Unsupported alignment method")
    return ResearchQuery(state=state, cycle=cycle, baseline=baseline, as_of=as_of, time_basis=time_basis,
                         revision=revision, metric=metric, mode=mode, geography_ids=[g for g in geography_ids.split(",") if g],
                         category_dimension=category_dimension, category=category, alignment=alignment,
                         date_window=tuple(date_window.split(",")) if date_window else None)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    database = Database(settings)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="observatory-job")

    @asynccontextmanager
    async def lifespan(app):
        if not settings.public_mode:
            with database.session() as session:
                for job in session.scalars(select(Job).where(Job.status.in_(["running", "queued"]))):
                    job.status, job.error, job.finished_at = "interrupted", "Application restarted before the job completed. The previous validated evidence is intact.", utc_now()
                session.commit()
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Battleground Senate Observatory", version="0.1.0", lifespan=lifespan,
                  docs_url=None if settings.public_mode else "/docs",
                  redoc_url=None if settings.public_mode else "/redoc",
                  openapi_url=None if settings.public_mode else "/openapi.json")
    app.state.database = database
    app.state.settings = settings
    # The privacy boundary runs inside compression, so it can inspect JSON bytes.
    app.add_middleware(PublicAccessMiddleware, settings=settings)
    app.add_middleware(GZipMiddleware, minimum_size=1500, compresslevel=4)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=["GET", "POST"] if settings.public_mode else ["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_mutations(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            local_origin = str(request.base_url).rstrip("/")
            if origin and origin != local_origin and origin not in settings.allowed_origins:
                return JSONResponse({"detail": "Writes require the local Observatory origin"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "revision": database.latest_revision(), "local_only": not settings.public_mode,
                "deployment_mode": settings.deployment_mode, "public_read_only": settings.public_mode}

    @app.get("/api/v1/bootstrap")
    def get_bootstrap():
        value = bootstrap(database)
        return {**value, "app": {**value["app"], "deployment_mode": settings.deployment_mode,
                "public_read_only": settings.public_mode}, "capabilities": public_capabilities(settings)}

    @app.get("/api/v1/workspace")
    def get_workspace(query: ResearchQuery = Depends(query_parameters)):
        return workspace(database, query)

    @app.get("/api/v1/sources")
    def get_sources():
        return {"sources": source_inventory(database), "revision": database.latest_revision(), "latest_revision": database.latest_revision()}

    @app.get("/api/v1/geography/{state}")
    def get_geography(state: str):
        filename = "states.geojson" if state.upper() == "US" else f"{state.upper()}.geojson"
        if state.upper() not in {"US", *[s["code"] for s in all_states()]}:
            raise HTTPException(404, "Unknown geography")
        path = settings.project_root / "frontend" / "public" / "geography" / filename
        if not path.exists():
            raise HTTPException(503, "Official boundaries have not been downloaded. Run observatory geography.")
        from .geography import enrich_geojson
        return JSONResponse(enrich_geojson(json.loads(path.read_text()), state.upper()),
                            media_type="application/geo+json", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/v1/evidence/{observation_id}")
    def get_evidence(observation_id: int):
        with database.session() as session:
            record = session.get(ObservationRecord, observation_id)
            if not record:
                raise HTTPException(404, "Observation not found")
            snapshot = session.get(Snapshot, record.snapshot_id)
            source = next((s for s in source_inventory(database) if s["id"] == record.source_id), None)
            versions = list(session.scalars(select(ObservationRecord).where(ObservationRecord.logical_key == record.logical_key).order_by(ObservationRecord.revision)))
            corrections = list(session.scalars(select(Correction).where(Correction.observation_id == record.id)))
            validation = database.validation_for({**record.payload, "source_id": record.source_id,
                                                   "revision": record.revision})
            return {"observation": {**record.payload, "id": record.id, "revision": record.revision, "source_id": record.source_id, "snapshot_id": record.snapshot_id, "observed_at": record.observed_at},
                    "source": source, "snapshot": {k: v for k, v in record_dict(snapshot).items() if k != "path"},
                    "revisions": [{"id": r.id, "value": r.value, "revision": r.revision, "observed_at": r.observed_at} for r in versions],
                    "corrections": [record_dict(c) for c in corrections], "quality_validation": validation,
                    "calculation": record.payload.get("metadata", {}).get("derivation", "Original published aggregate; see native fields and source document."),
                    "warnings": ["A reconstructed event-date record does not prove contemporary publication."] if record.payload["time_basis"] == "reconstructed" else []}

    @app.get("/api/v1/documents/{snapshot_id}")
    def get_document(snapshot_id: int):
        with database.session() as session:
            snapshot = session.get(Snapshot, snapshot_id)
            if not snapshot or not Path(snapshot.path).is_file():
                raise HTTPException(404, "Archived document unavailable")
            path = Path(snapshot.path).resolve()
            if not path.is_relative_to(settings.archive_dir.resolve()):
                raise HTTPException(403, "Document is outside the source archive")
            return FileResponse(path, media_type=snapshot.content_type, filename=f"source-{snapshot_id}-{snapshot.sha256[:12]}", headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/research")
    def get_research(kind: str | None = None):
        with database.session() as session:
            statement = select(ResearchObject).order_by(ResearchObject.updated_at.desc())
            if kind:
                statement = statement.where(ResearchObject.kind == kind)
            return {"items": [record_dict(r) for r in session.scalars(statement)]}

    @app.post("/api/v1/research", status_code=201)
    def add_research(body: ResearchInput):
        with database.lock, database.session() as session:
            item = ResearchObject(**body.model_dump())
            session.add(item)
            session.commit()
            return record_dict(item)

    @app.put("/api/v1/research/{item_id}")
    def update_research(item_id: int, body: ResearchInput):
        with database.lock, database.session() as session:
            item = session.get(ResearchObject, item_id)
            if not item:
                raise HTTPException(404, "Research item not found")
            for key, value in body.model_dump().items():
                setattr(item, key, value)
            item.updated_at = utc_now()
            session.commit()
            return record_dict(item)

    @app.delete("/api/v1/research/{item_id}")
    def delete_research(item_id: int):
        with database.lock, database.session() as session:
            item = session.get(ResearchObject, item_id)
            if not item:
                raise HTTPException(404, "Research item not found")
            session.delete(item)
            session.commit()
            return {"deleted": True}

    @app.post("/api/v1/corrections", status_code=201)
    def add_correction(body: CorrectionInput):
        with database.lock, database.session() as session:
            observation = session.get(ObservationRecord, body.observation_id)
            if not observation:
                raise HTTPException(404, "Observation not found")
            revision = Revision(reason="Manual aggregate correction", source_id=observation.source_id)
            session.add(revision)
            session.flush()
            correction = Correction(observation_id=observation.id, revision=revision.id, original=observation.value, replacement=body.replacement, reason=body.reason)
            session.add(correction)
            session.commit()
            return record_dict(correction)

    def execute_collection(job_id: int, body: RefreshInput):
        with database.session() as session:
            job = session.get(Job, job_id)
            job.status, job.started_at = "running", utc_now()
            session.commit()
        try:
            result = collect_sources(database, source_ids=body.source_ids, state=body.state, include_historical=body.include_historical, job_id=job_id)
            with database.session() as session:
                job = session.get(Job, job_id)
                job.status, job.finished_at, job.result = "completed", utc_now(), result
                session.commit()
        except Exception as exc:
            logger.exception("Collection job failed")
            with database.session() as session:
                job = session.get(Job, job_id)
                job.status, job.finished_at, job.error = "failed", utc_now(), str(exc)
                session.commit()

    @app.post("/api/v1/refresh", status_code=202)
    def refresh(body: RefreshInput = RefreshInput()):
        with database.lock, database.session() as session:
            current = session.scalar(select(Job).where(Job.kind == "collection", Job.status.in_(["queued", "running"])))
            if current:
                return record_dict(current)
            job = Job(kind="collection", status="queued")
            session.add(job)
            session.commit()
            job_id = job.id
        executor.submit(execute_collection, job_id, body)
        return {"id": job_id, "status": "queued"}

    @app.get("/api/v1/jobs")
    def get_jobs():
        with database.session() as session:
            return {"jobs": [record_dict(j) for j in session.scalars(select(Job).order_by(Job.id.desc()).limit(30))]}

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: int):
        with database.session() as session:
            job = session.get(Job, job_id)
            if not job:
                raise HTTPException(404, "Job not found")
            return record_dict(job)

    @app.post("/api/v1/scenarios")
    def scenarios(body: dict):
        from .scenario_service import calculate_scenario
        return calculate_scenario(database, body)

    @app.get("/api/v1/polling")
    def polling(query: ResearchQuery = Depends(query_parameters), population: str = "LV", window_days: int = 21,
                include_partisan: bool = True, question_type: str = "vote_choice", ballot_type: str = "full_ballot",
                comparison_key: str | None = None):
        from .analytics import poll_analysis
        view = workspace(database, query)
        if population == "all":
            return {"status": "separate_populations", "averages": {}, "eligible": [], "excluded": [],
                    "series": [], "producer_count": 0, "revision": view["revision"], "query": view["query"],
                    "warnings": ["Choose LV or RV for a descriptive average. Different populations cannot be pooled."]}
        analysis = poll_analysis(view["polls"], as_of=view["query"]["as_of"], state=query.state, cycle=query.cycle,
            population=population, window_days=window_days, include_partisan=include_partisan,
            question_type=question_type, ballot_type=ballot_type, comparison_key=comparison_key)
        return {**analysis, "revision": view["revision"], "query": view["query"]}

    @app.get("/api/v1/forecasts")
    def forecasts(state: str = "NC", revision: int | None = None):
        return {"status": "unavailable", "reason": "No cutoff-safe historical validation dataset has been approved for live probability publication.",
                "methodology": "Empirical-Bayes polling plus a fundamentals prior, Student-t forecast error, shared national and race-specific error. Early-vote predictors are excluded until validated.",
                "validation": None, "runs": [], "requirements": ["Original historical survey releases with publication evidence", "Official historical outcomes and fundamentals", "Rolling-origin evaluation at 30, 14, 7 and 1 days", "Supported ranked-choice/runoff rules where applicable"],
                "warnings": ["Scenario arithmetic remains available. Missing calibrated probabilities are not zero probabilities."]}

    @app.post("/api/v1/forecast/backtest")
    def backtest(body: dict):
        from .analytics import backtest_forecasts
        cases = body.get("cases", [])
        if not cases or len(cases) > 10000:
            raise ValueError("Supply between 1 and 10,000 documented historical cases")
        result = backtest_forecasts(cases, seed=int(body.get("seed", 2026)), simulations=min(int(body.get("simulations", 20000)), 50000))
        with database.session() as session:
            item = ResearchObject(kind="report", title="Historical forecast backtest", body="User-supplied historical evidence; inspect temporal validity and validation coverage before promotion.", view={"result": result, "input_manifest": body.get("manifest", {})})
            session.add(item)
            session.commit()
        return result

    @app.post("/api/v1/scenarios/senate")
    def senate(body: dict):
        from .analytics import senate_scenarios
        return senate_scenarios(body.get("races", []), holdovers=body.get("holdovers", {}))

    def render_export(query: ResearchQuery, format: str, sections: list[str] | None = None,
                      include_notes: bool = False, title: str | None = None, note: str = ""):
        if settings.public_mode and (include_notes or note):
            raise HTTPException(403, "Private notes are available only in local exports")
        view = workspace(database, query)
        if settings.public_mode:
            view = public_payload(view, private_roots=(str(settings.data_dir), str(settings.project_root)))
        notes = []
        if include_notes:
            with database.session() as session:
                notes = [record_dict(n) for n in session.scalars(select(ResearchObject).where(ResearchObject.kind == "note"))]
            if note.strip():
                notes.append({"title": "Report annotation", "body": note.strip()})
        filename = f"observatory-{query.state}-{query.cycle}-r{view['revision']}.{format}"
        media = {"csv": "text/csv", "json": "application/json", "html": "text/html", "pdf": "application/pdf", "zip": "application/zip"}[format]
        if format == "csv":
            content = csv_data(view)
        elif format == "json":
            content = json.dumps({"workspace": view, "manifest": manifest(view)}, indent=2).encode()
        elif format == "html":
            content = html_report(view, sections=sections, notes=notes, title=title)
        elif format == "pdf":
            content = pdf_report(view, sections=sections, notes=notes, title=title)
        else:
            with database.session() as session:
                ids = {o["snapshot_id"] for o in view["observations"]} | {p["snapshot_id"] for p in view["polls"]}
                ids |= {reference["snapshot_id"] for reference in view.get("calendar_references", []) if reference.get("snapshot_id")}
                snapshots = [record_dict(s) for s in session.scalars(select(Snapshot).where(Snapshot.id.in_(ids)))] if ids else []
            content = research_bundle(view, extra_manifest={"source_snapshots": [{k: v for k, v in s.items() if k != "path"} for s in snapshots]}, notes=notes, sections=sections, title=title)
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/v1/exports")
    def export(format: Literal["csv", "json", "html", "pdf", "zip"] = "csv", sections: str | None = None,
               include_notes: bool = False, query: ResearchQuery = Depends(query_parameters)):
        return render_export(query, format, sections.split(",") if sections is not None else None, include_notes)

    @app.post("/api/v1/exports")
    def composed_export(body: ExportInput):
        return render_export(body.query, body.format, body.sections, body.include_notes, body.title, body.note)

    from .atlas_api import register_atlas_routes
    register_atlas_routes(app, database, executor, query_parameters)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route")
        dist = settings.project_root / "frontend" / "dist"
        target = (dist / path).resolve()
        if target.is_relative_to(dist.resolve()) and target.is_file():
            return FileResponse(target)
        index = dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"message": "Backend ready. Run the frontend dev server on http://127.0.0.1:5173 or build frontend/dist.", "api": "/docs"})

    return app


app = create_app()
