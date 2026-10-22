"""Publish immutable aggregate research responses for the zero-cost web edition.

This is a build step, never an anonymous request handler. Every published request
has an exact normalized scope. Unsupported filters remain unsupported rather
than silently receiving a nearby statewide response.
"""
from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import os
import shutil
import tempfile
from collections import OrderedDict, defaultdict
from pathlib import Path
from threading import RLock
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from .db import Database, record_dict
from .domain import ResearchQuery, utc_now
from .public_access import public_payload
from .registry import WATCHLIST, all_states
from .settings import Settings, local_today

SCHEMA = "observatory-public-v1"
MAX_SITE_BYTES = 900_000_000
MAX_FILE_BYTES = 95_000_000
MAX_OBJECT_FILES = 19_500
EVIDENCE_BUCKET_SIZE = 512
EV_CYCLES = (2026, 2024, 2022, 2020, 2018, 2016)
BASELINES = (2022, 2024, 2020, 2018)
RESEARCH_DEFAULTS = {"cycle": 2026, "baseline": 2022, "time_basis": "reported",
                     "metric": "ballots_cast", "mode": "all", "alignment": "days_to_election"}


def _parameter(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(part) for part in value)
    return str(value)


def canonical_request(path: str, query: dict | None = None, defaults: dict | None = None) -> str:
    """Identical to URLSearchParams sorting; no unknown filter is discarded."""
    parsed = urlsplit(path)
    values = {**(defaults or {}), **{key: value for key, value in parse_qsl(parsed.query) if value}}
    for key, value in (query or {}).items():
        if value is not None and _parameter(value) != "":
            values[key] = value
    pairs = sorted((str(key), _parameter(value)) for key, value in values.items()
                   if value is not None and _parameter(value) != "")
    return parsed.path + ("?" + urlencode(pairs) if pairs else "")


def readonly_database(settings: Settings) -> Database:
    """Use existing query services without DDL, WAL setup or source publication."""
    if not settings.database_path.is_file():
        raise ValueError("Initialize or restore the evidence database before publishing")
    database = Database.__new__(Database)
    database.settings, database.lock = settings, RLock()
    database._publication_national_cache = OrderedDict()
    uri = "sqlite:///file:" + quote(str(settings.database_path), safe="/") + "?mode=ro&uri=true"
    database.engine = create_engine(uri, connect_args={"check_same_thread": False, "timeout": 60})
    database.session = sessionmaker(database.engine, expire_on_commit=False)
    return database


class Publication:
    def __init__(self, directory: Path, *, revision: int, as_of: str, settings: Settings,
                 states: list[str], max_bytes: int = MAX_SITE_BYTES, max_file_bytes: int = MAX_FILE_BYTES,
                 max_files: int = MAX_OBJECT_FILES):
        self.directory, self.settings = directory, settings
        self.max_bytes, self.max_file_bytes = max_bytes, max_file_bytes
        self.max_files = max_files
        self.bytes = 0
        self.files: dict[str, dict] = {}
        self._stored_by_digest: dict[str, dict] = {}
        research = {**RESEARCH_DEFAULTS, "revision": revision, "as_of": as_of}
        bounded = {"revision": revision}
        forecast = {"cycle": 2026, "revision": revision, "as_of": as_of}
        results = {"year": 2024, "office": "PRESIDENT", "baseline": 2020,
                   "geography_level": "county", "revision": revision, "offset": 0}
        self.manifest = {"schema_version": SCHEMA, "published_at": utc_now(), "data_as_of": as_of,
            "dataset_revision": revision, "states": states, "requests": {}, "available_queries": [],
            "unavailable_queries": [], "reports": {}, "catalogs": {}, "partitions": {},
            "evidence_buckets": {}, "evidence_bucket_size": EVIDENCE_BUCKET_SIZE,
            "request_defaults": {
                **{path: research for path in ("/api/v1/workspace", "/api/v2/workspace", "/api/v2/analytics", "/api/v2/trajectories")},
                "/api/v2/participation/quality": research,
                "/api/v1/forecasts": research,
                "/api/v1/polling": {**research, "window_days": 21, "population": "LV",
                    "include_partisan": True, "question_type": "vote_choice"},
                "/api/v2/forecasts/early-vote": forecast, "/api/v2/forecasts/feature-tests": forecast,
                "/api/v2/forecasts/offices": {**forecast, "office": "GOVERNOR"},
                "/api/v2/forecasts/reasoning": {**forecast, "include_polls": False,
                    "include_markets": False, "include_context": False},
                "/api/v2/early-vote/history": {**forecast, "alignment": "days_to_election",
                    "history_basis": "retrospective", "baseline_cycles": "2016,2018,2020,2022,2024"},
                "/api/v2/results": results, "/api/v2/analysis/results": results,
                "/api/v2/comparisons/results": {**results, "limit": 200},
                "/api/v2/context": bounded, "/api/v2/precincts/catalog": bounded,
                "/api/v2/precincts/map": {**bounded, "year": 2020, "office": "PRESIDENT", "lod": "overview", "limit": 20000},
                "/api/v2/catalog/contests": {**bounded, "offset": 0, "limit": 100},
                "/api/v2/catalog/elections": {**bounded, "offset": 0, "limit": 100}},
            "schedule": {"interval_hours": 2, "description": "Scheduled publication checks every two hours; free hosted jobs can be delayed or missed."},
            "capabilities": {"deployment_mode": "public-static", "public_read_only": True,
                "research_write": False, "collection": False, "raw_documents": False,
                "private_notebook": False, "aggregate_exports": True,
                "scenario_calculation": "browser", "report_composition": "browser"},
            "limitations": [
                "This free web edition serves explicitly published aggregate investigations. Unpublished cutoffs, revisions and filter combinations are unavailable; they never silently reuse different evidence.",
                "Public source outages retain the previous validated observations. Publication time is separate from the dates reported by sources.",
                "Private research objects and original voter files are excluded. Browser notes remain on this device.",
                "RCP browser captures do not refresh unattended. Their original capture date remains visible.",
                "Conditional EV calls and their sensitivity ranges remain experimental; no calibrated winner probability is implied."]}

    def safe(self, payload):
        return public_payload(payload, private_roots=(str(self.settings.data_dir), str(self.settings.project_root)))

    def _store(self, payload) -> dict:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        existing = self._stored_by_digest.get(digest)
        if existing is not None:
            # Repeated map geometry is already represented by these exact
            # canonical bytes. Retain only the descriptor, never the raw payload,
            # and avoid recompressing it for each contest and research view.
            return existing
        stored = gzip.compress(encoded, compresslevel=6, mtime=0) if len(encoded) >= 1024 else encoded
        compressed = len(stored) < len(encoded) * .95
        stored = stored if compressed else encoded
        relative = f"objects/{digest[:2]}/{digest}.json" + (".gz" if compressed else "")
        if relative in self.files:
            return self.files[relative]
        if len(self.files) >= self.max_files:
            raise ValueError("Public bundle exceeds its file-count budget; no partial publication was installed")
        if len(encoded) > self.max_file_bytes:
            raise ValueError("Aggregate response exceeds the public single-file limit; publish an explicit smaller scope")
        if self.bytes + len(stored) > self.max_bytes:
            raise ValueError("Public bundle exceeds its site budget; no partial publication was installed")
        target = self.directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stored)
        descriptor = {"path": relative, "sha256": digest, "bytes": len(stored), "uncompressed_bytes": len(encoded)}
        if compressed:
            descriptor["compression"] = "gzip"
        self.files[relative] = descriptor
        self._stored_by_digest[digest] = descriptor
        self.bytes += len(stored)
        return descriptor

    def _shared(self, value, *, root=False):
        """Deduplicate repeated exact tables, never approximate or truncate them."""
        if isinstance(value, dict):
            cooked = {key: self._shared(item) for key, item in value.items()}
        elif isinstance(value, list):
            coordinate_row = bool(value) and all(isinstance(item, list) and len(item) <= 4
                and all(isinstance(number, (int, float)) for number in item) for item in value)
            if len(value) > 128 and not coordinate_row and len(json.dumps(value, separators=(",", ":"))) >= 12_000:
                # Identical current/baseline records share chunks across views.
                chunks = [self._store([self._shared(item) for item in value[index:index + 128]])
                          for index in range(0, len(value), 128)]
                return {"$public_chunks": [{"$public_ref": chunk["path"],
                    "sha256": chunk["sha256"], "bytes": chunk["bytes"]} for chunk in chunks]}
            cooked = [self._shared(item) for item in value]
        else:
            return value
        if not root and len(json.dumps(cooked, separators=(",", ":"), ensure_ascii=False).encode()) >= 12_000:
            descriptor = self._store(cooked)
            return {"$public_ref": descriptor["path"], "sha256": descriptor["sha256"], "bytes": descriptor["bytes"]}
        return cooked

    def object(self, payload) -> dict:
        descriptor = self._store(self._shared(self.safe(payload), root=True))
        return {**descriptor, "encoding": "observatory-json-refs-v1"}

    def response(self, path: str, query: dict | None, payload) -> dict:
        defaults = self.manifest["request_defaults"].get(path, {})
        key = canonical_request(path, query, defaults)
        descriptor = self.object(payload)
        old = self.manifest["requests"].get(key)
        if old and old != descriptor:
            raise ValueError(f"Conflicting published response for {key}")
        self.manifest["requests"][key] = descriptor
        return descriptor

    def unavailable(self, path, query, reason):
        self.manifest["unavailable_queries"].append({"path": path, "query": query,
            "reason": self.safe(str(reason))})

    def finish(self):
        self.manifest["footprint"] = {"objects": len(self.files), "bytes": self.bytes,
            "maximum_site_bytes": self.max_bytes, "maximum_file_bytes": self.max_file_bytes,
            "maximum_object_files": self.max_files}
        self.manifest["objects"] = list(self.files.values())
        encoded = json.dumps(self.manifest, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        if self.bytes + len(encoded) > self.max_bytes:
            raise ValueError("Public manifest exceeds the total publication budget")
        (self.directory / "manifest.json").write_bytes(encoded)
        return self.manifest


def _combined_datasets(database, state=None):
    from .atlas import dataset_catalog
    from .participation_catalog import participation_datasets
    from .precincts import precinct_catalog
    catalog = dataset_catalog(database, state)
    precinct = [{**row, "name": row["title"], "on_demand": True, "states": [row["state"]],
        "loaded_states": [row["state"]] if row["loaded"] else [], "provider": "precinct"}
        for row in precinct_catalog(database, state=state)["datasets"]]
    return {**catalog, "datasets": catalog["datasets"] + participation_datasets(database, state) + precinct}


def _attributions(database, inventory, revision):
    """Credit attributed bridges separately from the original election authority."""
    from sqlalchemy import func

    from .db import Snapshot
    ids = {row["id"] for row in inventory if row.get("connector") in {"uf_tracker", "uf_history"}}
    with database.session() as session:
        retrieved = dict(session.execute(select(Snapshot.source_id, func.max(Snapshot.retrieved_at)).where(
            Snapshot.source_id.in_(ids), Snapshot.revision <= revision).group_by(Snapshot.source_id)).all())
    return [{"source_id": row["id"], "title": row["name"],
        "creator": "UF Election Lab; Michael P. McDonald", "cycle": row.get("cycle", 2026),
        "source_url": row.get("original_url") or row["url"],
        "about_url": row.get("about_url") or f"https://election.lab.ufl.edu/early-vote/{row.get('cycle', 2026)}-early-voting/",
        "license": "CC BY-NC-ND 4.0", "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
        "retrieved_at": retrieved[row["id"]], "data_as_of": row.get("data_as_of"),
        "transformation": "Source-native public aggregate columns normalized into separately labeled participation measures; earliest positive dated archive observations, suppressed placeholders, unreconciled totals and native-method caveats are retained or withheld under documented validation rules. No candidate votes are inferred.",
        "interpretation": "Attributed academic tracker compilation, distinct from the originating election authority. This noncommercial research display is not endorsed by the producer; report, retrieval and archival-availability dates have different meanings."}
        for row in inventory if row["id"] in retrieved]


def _geography(database, publication, states):
    from .geography import enrich_geojson
    directory = database.settings.project_root / "frontend" / "public" / "geography"
    for state in ["US", *states]:
        path = directory / ("states.geojson" if state == "US" else f"{state}.geojson")
        if path.is_file():
            publication.response(f"/api/v1/geography/{state}", {}, enrich_geojson(json.loads(path.read_text()), state))


def _evidence(database, publication, evidence, inventory):
    from .db import Snapshot
    sources = {source["id"]: source for source in inventory}
    with database.session() as session:
        snapshots = {row.id: record_dict(row) for row in session.scalars(select(Snapshot).where(
            Snapshot.id.in_({row["snapshot_id"] for row in evidence.values()})))}
    credits = {row["source_id"]: row for row in publication.manifest.get("attributions", [])}
    buckets = defaultdict(dict)
    for observation_id, row in evidence.items():
        source = dict(sources.get(row["source_id"], {}))
        if row["source_id"] in credits:
            source["attribution"] = credits[row["source_id"]]
        buckets[observation_id // EVIDENCE_BUCKET_SIZE][str(observation_id)] = {"observation": row,
            "source": source or None, "snapshot": snapshots.get(row["snapshot_id"]),
            "revisions": [], "corrections": [], "history_available": False,
            "calculation": "Published aggregate value from the exact investigation; original source URL and SHA-256 are preserved in snapshot metadata.",
            "warnings": ["This public inspector projects the selected aggregate and snapshot citation. Complete version history, native source documents and private correction annotations are available only in the local edition; an empty history here does not establish that no revision occurred."]}
    for bucket, items in sorted(buckets.items()):
        publication.manifest["evidence_buckets"][str(bucket)] = publication.object(items)


def _catalogs(database, publication, states, revision):
    from .atlas.models import BallotOption, Contest, Election, ElectionResult, GeographyVersion
    from .atlas.result_validation import invalidated_result_contests
    invalid = invalidated_result_contests(database, revision)
    with database.session() as session:
        known = set(session.scalars(select(ElectionResult.contest_id).where(
            ElectionResult.revision <= revision, ElectionResult.state.in_(states)).distinct())) - invalid
        contests = [record_dict(row) for row in session.scalars(select(Contest).where(Contest.id.in_(known)))]
        election_ids = {row["election_id"] for row in contests}
        elections = [record_dict(row) for row in session.scalars(select(Election).where(Election.id.in_(election_ids)))]
        options = [record_dict(row) for row in session.scalars(select(BallotOption).where(BallotOption.contest_id.in_(known)))]
        places = [record_dict(row) for row in session.scalars(select(GeographyVersion).where(
            GeographyVersion.state.in_(states), GeographyVersion.level != "precinct"))]
        result_groups = session.execute(select(ElectionResult.state, ElectionResult.year, ElectionResult.office,
            ElectionResult.geography_level).where(ElectionResult.revision <= revision,
            ElectionResult.state.in_(states), ~ElectionResult.contest_id.in_(invalid)).distinct()).all()
    contests.sort(key=lambda row: (-row["year"], row["office"], row["name"], row["id"]))
    elections.sort(key=lambda row: (-row["year"], row["state"], row["id"]))
    for kind, rows in (("contests", contests), ("elections", elections), ("candidates", options), ("places", places)):
        publication.manifest["catalogs"][kind] = publication.object({"revision": revision, "items": rows,
            "complete": kind != "places", "scope": "All collected contests with validated result evidence" if kind != "places"
            else "Collected county, district, municipality and state geography versions; precinct discovery uses its published map partition"})
    for state in [None, *states]:
        for kind, rows in (("contests", contests), ("elections", elections)):
            selected = [row for row in rows if not state or row["state"] == state]
            publication.response(f"/api/v2/catalog/{kind}", {"state": state},
                {"revision": revision, "total": len(selected), kind: selected[:100], "offset": 0, "limit": 100})
    return result_groups


def _workspace_responses(database, publication, query, evidence):
    from .participation_quality import participation_quality
    from .service import workspace
    value = workspace(database, query)
    args = query.model_dump()
    publication.response("/api/v1/workspace", args, value)
    publication.response("/api/v1/forecasts", args, {"status": "unavailable",
        "reason": "No cutoff-safe historical validation dataset has been approved for live probability publication.",
        "methodology": "Empirical-Bayes polling plus a fundamentals prior, Student-t forecast error, shared national and race-specific error. Early-vote predictors are excluded until validated.",
        "validation": None, "runs": [], "requirements": ["Original historical survey releases with publication evidence",
            "Official historical outcomes and fundamentals", "Rolling-origin evaluation at 30, 14, 7 and 1 days",
            "Supported ranked-choice/runoff rules where applicable"],
        "warnings": ["Scenario arithmetic remains available. Missing calibrated probabilities are not zero probabilities."]})
    compact = {key: item for key, item in value.items() if key not in {"observations", "polls", "historical"}} | {
        "historical": {key: item for key, item in value["historical"].items() if key not in {"geographies", "sources"}},
        "evidence": {"count": value["observation_scope"]["selected_count"], "complete": True,
            "detail_endpoint": "/api/v1/evidence/{id}", "omitted_from_summary": "raw observation rows and full poll records"},
        "series_by_place": value["geographic_research"].get("places", [])}
    for path in ("/api/v2/analytics", "/api/v2/workspace"):
        publication.response(path, args, compact)
    publication.response("/api/v2/trajectories", args,
        {"revision": value["revision"], "query": value["query"], "metric": value["historical"]["metric"],
         "unit": value["summary"]["unit"], **value["geographic_research"]})
    publication.response("/api/v2/participation/quality", args, participation_quality(database, query))
    publication.manifest["available_queries"].append({"path": "/api/v1/workspace", "query": args,
        "available": value["summary"]["total"] is not None, "metric_label": value["summary"]["metric_label"],
        "geographies": len(value["geographies"]), "latest_date": value["summary"]["latest_date"]})
    for row in value["observations"]:
        evidence.setdefault(row["id"], row)
    if query.cycle == 2026 and query.baseline == 2022 and query.time_basis == "reported":
        from .analytics import poll_analysis
        for window, population, partisan, question in itertools.product(
                (7, 14, 21, 30, 60), ("LV", "RV"), (False, True), ("vote_choice", "winner_expectation")):
            policy = {"window_days": window, "population": population,
                "include_partisan": partisan, "question_type": question}
            analysis = poll_analysis(value["polls"], as_of=value["query"]["as_of"], state=query.state,
                cycle=query.cycle, **policy)
            publication.response("/api/v1/polling", {**args, **policy},
                {**analysis, "revision": value["revision"], "query": value["query"]})
    return value


def _state_research(database, publication, state, revision, as_of, evidence, *, include_reports, include_forecasts):
    from .atlas import availability, context_query
    from .ev_history import stage_history
    from .precincts import precinct_catalog
    from .service import capabilities
    base = ResearchQuery(state=state, revision=revision, as_of=as_of)
    capability = capabilities(database, state, revision=revision, as_of=as_of)
    publication.response("/api/v2/catalog/availability/" + state, {"revision": revision},
        {**availability(database, state), "participation": capability})
    publication.response("/api/v2/catalog/datasets", {"state": state}, _combined_datasets(database, state))
    publication.response("/api/v2/context", {"state": state}, context_query(database, state=state, revision=revision))
    publication.response("/api/v2/precincts/catalog", {"state": state}, precinct_catalog(database, state=state, revision=revision))
    combos = database.observation_catalog(revision=revision, state=state, cutoff=as_of)
    selections = {(2026, "ballots_cast", "all", "reported")}
    selections |= {(row["cycle"], row["metric"], row["mode"], row["time_basis"]) for row in combos
        if row["cycle"] in EV_CYCLES and not row.get("category_dimension") and row["metric"] != "market_price_pct"}
    primary = None
    for cycle, metric, mode, basis in sorted(selections, reverse=True):
        for baseline in BASELINES if cycle == 2026 else (2022,):
            query = base.model_copy(update={"cycle": cycle, "baseline": baseline, "metric": metric,
                "mode": mode, "time_basis": basis})
            value = _workspace_responses(database, publication, query, evidence)
            if query == base:
                primary = value
    if primary is None:
        primary = _workspace_responses(database, publication, base, evidence)
    recommended = capability.get("recommended_selection")
    if recommended:
        publication.manifest["partitions"][state] = {"recommended_query": {**base.model_dump(),
            **{key: recommended[key] for key in ("metric", "mode", "time_basis")}},
            "default_query": base.model_dump()}
    else:
        publication.manifest["partitions"][state] = {"default_query": base.model_dump(),
            "current_participation": "No compatible current aggregate is published; historical results remain available."}
    history_modes = {(None, None)} | {(metric, mode) for cycle, metric, mode, basis in selections
        if cycle == 2026 and basis == "reported"}
    for metric, mode in history_modes:
        for alignment, basis in itertools.product(("days_to_election", "days_since_opening"), ("retrospective", "reported")):
            query = {"state": state, "cycle": 2026, "revision": revision, "as_of": as_of,
                "metric": metric, "mode": mode, "alignment": alignment, "history_basis": basis,
                "baseline_cycles": "2016,2018,2020,2022,2024"}
            publication.response("/api/v2/early-vote/history", query, stage_history(database, state=state,
                revision=revision, as_of=as_of, metric=metric, mode=mode, alignment=alignment, history_basis=basis))
    if include_reports:
        from .public_access import public_report_document
        from .report_composer import (
            SECTION_CATALOG,
            TEMPLATES,
            ReportRequest,
            ReportSection,
            ResultsScope,
            _html,
        )
        sections = [ReportSection(id=row["id"]) for row in SECTION_CATALOG
                    if row['id'] != 'office_call' and (include_forecasts or row["id"] != "ev_call")]
        request = ReportRequest(title=f"{primary['state']['name']} election research dossier", query=base,
            sections=sections, include_notes=False,
            results=ResultsScope(geography_level="state" if state == "AK" else "county"))
        document = public_report_document(database, request)
        preview = {key: item for key, item in document.items() if key != "evidence"} | {
            "html": _html(document).decode(), "templates": TEMPLATES, "catalog": SECTION_CATALOG}
        source_ids = {row.get("source_id") for row in document["sources"]}
        preview["attributions"] = [row for row in publication.manifest.get("attributions", [])
                                   if row["source_id"] in source_ids]
        publication.manifest["reports"][state] = {**publication.object(preview), "query": base.model_dump(),
            "results": request.results.model_dump(), "context_metric": request.context_metric,
            "map_metric": request.map_metric}


def _results(database, publication, groups, revision):
    from .atlas import result_query
    from .historical_comparisons import compare_results
    major = {"PRESIDENT", "US SENATE", "US HOUSE", "GOVERNOR", "GOVERNOR / LIEUTENANT GOVERNOR",
             "GOVERNOR/LIEUTENANT GOVERNOR"}
    for state, year, office, grain in sorted(groups):
        if grain == "precinct" or office not in major:
            continue  # Loaded paired precinct maps have their own exact source partition.
        baselines = {2020, 2022, year - 4} if year >= 2018 and office in major else {year - 4}
        for baseline in sorted(baselines):
            query = {"state": state, "year": year, "office": office, "geography_level": grain,
                "baseline": baseline, "revision": revision, "offset": 0}
            value = result_query(database, **query)
            publication.response("/api/v2/results", query, value)
            if year in {2024, 2022, 2020, 2018} and office in major:
                paired = compare_results(database, **query, limit=5000)
                publication.response("/api/v2/comparisons/results", {**query, "limit": 5000}, paired)
                # API's 200-place default is a different, explicitly paginated scope.
                publication.response("/api/v2/comparisons/results", {**query, "limit": 200},
                    compare_results(database, **query, limit=200))
    national = {(year, office) for _, year, office, grain in groups if grain == "state" and office in major}
    for year, office in sorted(national):
        for baseline in sorted({2020, 2022, year - 4}):
            query = {"year": year, "office": office, "geography_level": "state",
                "baseline": baseline, "revision": revision, "offset": 0}
            publication.response("/api/v2/results", query, result_query(database, **query))
    publication.manifest["result_scope"] = {"offices": sorted(major),
        "geography_levels": sorted({grain for _, _, office, grain in groups if grain != "precinct" and office in major}),
        "policy": "Federal and gubernatorial result investigations are published. Additional local, judicial and legislative contests remain in the verified catalog, with unpublished analytical queries explicitly unavailable in this free edition."}


def _forecasts(database, publication, states, revision, as_of):
    from .ev_feature_validation import build_feature_validation
    from .ev_forecast import early_vote_forecasts
    from .forecast_reasoning import forecast_reasoning
    from .office_research import office_research
    for office in ('GOVERNOR', 'US HOUSE'):
        publication.response('/api/v2/forecasts/offices', {'office': office, 'cycle': 2026, 'revision': revision, 'as_of': as_of},
            office_research(database, office=office, revision=revision, as_of=as_of))
    run = early_vote_forecasts(database, state=states[0], revision=revision, as_of=as_of)
    features = build_feature_validation(database, revision, as_of, backtesting=run["backtesting"])
    for state in states:
        query = {"state": state, "cycle": 2026, "revision": revision, "as_of": as_of}
        selected = next((call for call in run["calls"] if call["state"] == state), None)
        publication.response("/api/v2/forecasts/early-vote", query, {**run, "selected": selected,
            "selected_state": state, "selected_note": None if selected else
            "This state has no scheduled 2026 Senate contest. Its atlas and participation evidence remain available."})
        publication.response("/api/v2/forecasts/feature-tests", query, features)
        for polls, markets, context in itertools.product((False, True), repeat=3):
            if state not in WATCHLIST and (polls or markets or context):
                continue
            toggles = {"include_polls": polls, "include_markets": markets, "include_context": context}
            value = forecast_reasoning(database, **query, **toggles)
            publication.response("/api/v2/forecasts/reasoning", {**query, **toggles}, value)
            for call in [call for call in run["calls"] if call["state"] == state]:
                publication.response("/api/v2/forecasts/reasoning", {**query, **toggles, "race_id": call["race_id"]},
                    value if selected and call["race_id"] == selected["race_id"] else
                    forecast_reasoning(database, **query, **toggles, race_id=call["race_id"]))


def _precincts(database, publication, states, revision):
    from .precincts import precinct_catalog, precinct_map
    catalog = precinct_catalog(database, revision=revision)
    publication.response("/api/v2/precincts/catalog", {}, catalog)
    for source in catalog["datasets"]:
        if not source["loaded"] or source["state"] not in states:
            continue
        for office in source["offices"]:
            query = {"state": source["state"], "year": source["year"], "office": office,
                "dataset_id": source["id"], "revision": revision, "lod": "overview", "limit": 20000}
            value = precinct_map(database, **query)
            publication.response("/api/v2/precincts/map", query, value)
            # Explicit omission selects the same first loaded dataset in the service.
            default = next((row for row in catalog["datasets"] if row["state"] == source["state"]
                and row["year"] == source["year"] and row["loaded"]), None)
            if default and default["id"] == source["id"]:
                publication.response("/api/v2/precincts/map", {**query, "dataset_id": None}, value)


def publish_public_data(database: Database, output: Path, *, as_of: str | None = None,
                        revision: int | None = None, states: list[str] | None = None,
                        include_forecasts: bool = True, include_reports: bool = True,
                        include_results: bool = True, include_precincts: bool = True,
                        replace: bool = False, progress=None, max_bytes: int = MAX_SITE_BYTES,
                        max_file_bytes: int = MAX_FILE_BYTES, max_files: int = MAX_OBJECT_FILES) -> dict:
    """Build elsewhere, verify scope/budget, then atomically replace one directory."""
    from .atlas import state_catalog
    from .service import bootstrap, source_inventory
    output = Path(output).expanduser()
    if output.is_symlink():
        raise ValueError("Publication must not replace a symbolic link")
    output = output.resolve()
    if output.is_relative_to(database.settings.data_dir.resolve()):
        raise ValueError("Publication must use a separate ordinary output directory")
    if output.exists() and (not replace or not output.is_dir()):
        raise ValueError("Output exists; choose a new directory or explicitly replace its published bundle")
    known = {row["code"] for row in all_states()}
    states = sorted(set(states or known))
    if not states or not set(states) <= known:
        raise ValueError("Choose verified U.S. state codes")
    revision = database.latest_revision() if revision is None else revision
    if revision != database.latest_revision():
        raise ValueError("Publish the current validated revision; pinned historical publications are retained as immutable artifacts")
    as_of = as_of or local_today()
    ResearchQuery(state=states[0], revision=revision, as_of=as_of)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".public-data-", dir=output.parent))
    publication = Publication(stage, revision=revision, as_of=as_of, settings=database.settings,
        states=states, max_bytes=max_bytes, max_file_bytes=max_file_bytes, max_files=max_files)
    notify = progress or (lambda value: None)
    try:
        notify({"stage": "catalogs", "revision": revision})
        boot = bootstrap(database)
        inventory = source_inventory(database)
        credits = _attributions(database, inventory, revision)
        publication.manifest["attributions"] = credits
        publication.response("/api/v1/bootstrap", {}, {**boot, "capabilities": publication.manifest["capabilities"],
            "attributions": credits})
        publication.response("/api/v1/health", {}, {"status": "ok", "revision": revision,
            "local_only": False, "deployment_mode": "public-static", "published_at": publication.manifest["published_at"]})
        publication.response("/api/v1/jobs", {}, {"jobs": [], "public_read_only": True,
            "note": "Collection runs in a separate scheduled publication workflow; private worker jobs are not exposed."})
        publication.response("/api/v1/sources", {}, {"sources": inventory,
            "revision": revision, "latest_revision": revision, "attributions": credits})
        publication.response("/api/v2/catalog/states", {}, state_catalog(database))
        publication.response("/api/v2/catalog/datasets", {}, _combined_datasets(database))
        _geography(database, publication, states)
        groups = _catalogs(database, publication, states, revision)
        evidence = {}
        for index, state in enumerate(states, 1):
            notify({"stage": "state", "state": state, "completed": index - 1, "total": len(states), "bytes": publication.bytes})
            _state_research(database, publication, state, revision, as_of, evidence,
                include_reports=include_reports, include_forecasts=include_forecasts)
        # This inspection projects already-displayed aggregate value rows. It
        # deliberately omits native source payloads, corrections and raw files.
        _evidence(database, publication, evidence, inventory)
        if include_results:
            notify({"stage": "results", "scopes": len(groups)})
            _results(database, publication, groups, revision)
        if include_precincts:
            notify({"stage": "precincts"})
            _precincts(database, publication, states, revision)
        if include_forecasts:
            notify({"stage": "forecasts"})
            _forecasts(database, publication, states, revision, as_of)
        if database.latest_revision() != revision:
            raise ValueError("Evidence advanced during publication; rebuild against a stable database snapshot")
        manifest = publication.finish()
        previous = output.with_name(output.name + f".previous-{os.getpid()}")
        if output.exists():
            if previous.exists():
                raise ValueError("Previous publication staging path exists")
            output.replace(previous)
        try:
            stage.replace(output)
        except BaseException:
            if previous.exists():
                previous.replace(output)
            raise
        if previous.exists():
            shutil.rmtree(previous)
        notify({"stage": "complete", "revision": revision, "requests": len(manifest["requests"]),
            "bytes": manifest["footprint"]["bytes"]})
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
