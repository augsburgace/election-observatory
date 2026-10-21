"""Archived, publisher-paired precinct cartography, never guessed Census VTD joins.

VEST's public 2020 release pairs each geometry and its returns in the same DBF
record. Its adjustments/allocations remain prominent methodology, not observed
early voting. North Carolina uses archived election-year NCSBE shapes and only
unique county + precinct identifiers from the original MEDSL records.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid, transform
from shapely.geometry import mapping, shape
from sqlalchemy import insert, select

from .archive import Fetcher
from .atlas.ingest import _publish, election_day, normal_party, number, stable_id
from .atlas.models import DatasetState, GeographicCrosswalk, ensure_schema
from .atlas.store import _geographies, _rows
from .db import Revision, Snapshot, record_dict
from .domain import utc_now
from .geography import county_match
from .registry import all_states
from .settings import PROJECT_ROOT

PARSER_VERSION = "precinct-paired-2"
REGISTRY_PATH = PROJECT_ROOT / "config" / "precinct_sources.json"
VEST_METADATA = "https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/K7760H"
LOD_TOLERANCE = {"overview": 0.002, "detail": 0.0002, "full": 0.0}
OFFICES = {"PRE": "PRESIDENT", "USS": "US SENATE", "GOV": "GOVERNOR", "ATG": "ATTORNEY GENERAL",
    "LTG": "LIEUTENANT GOVERNOR", "SOS": "SECRETARY OF STATE", "TRE": "TREASURER",
    "AUD": "AUDITOR", "AGR": "COMMISSIONER OF AGRICULTURE", "INS": "COMMISSIONER OF INSURANCE",
    "LAB": "COMMISSIONER OF LABOR", "LND": "LAND COMMISSIONER", "PSC": "PUBLIC SERVICE COMMISSIONER",
    "RRC": "RAILROAD COMMISSIONER", "SPI": "SUPERINTENDENT OF PUBLIC INSTRUCTION",
    "SSC": "STATE SUPREME COURT", "SAC": "STATE APPEALS COURT", "SCC": "STATE CRIMINAL APPEALS COURT",
    "COC": "CORPORATION COMMISSIONER", "SBE": "STATE BOARD OF EDUCATION", "UBR": "UNIVERSITY BOARD MEMBER",
    "COU": "COUNCIL MEMBER", "DEL": "US HOUSE"}
PARTIES = {"D": "DEM", "R": "REP", "L": "LIB", "G": "GRN", "I": "IND"}
HISTORICAL_WARNING = "Historical candidate returns are election context, not current early ballots, voter demographics, or contemporaneous election-night reporting."
RETROSPECTIVE_WARNING = "This is a retrospective publisher-harmonized election-geography release; it is not a contemporaneous 2020 source snapshot."


def precinct_sources() -> list[dict]:
    sources = json.loads(REGISTRY_PATH.read_text())["sources"]
    for year, stamp in ((2020, "20201018"), (2022, "20220831"), (2024, "20240723")):
        sources.append({"id": f"ncsbe_precinct_{year}", "state": "NC", "year": year,
            "title": f"North Carolina {year} official precinct boundaries and matched reported returns",
            "provider": "ncsbe", "source_tier": 1,
            "url": f"https://s3.amazonaws.com/dl.ncsbe.gov/ShapeFiles/Precinct/SBE_PRECINCTS_{stamp}.zip",
            "source_url": "https://www.ncsbe.gov/results-data/voting-maps-redistricting",
            "documentation_url": "https://www.ncsbe.gov/results-data/election-results/historical-election-results-data",
            "result_dataset_id": f"medsl_{year}_NC", "vintage": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}",
            "years": [year], "restricted": False})
    return sources


def _root(database, dataset_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_]+", dataset_id):
        raise ValueError("Invalid precinct dataset identifier")
    return database.settings.data_dir / "geometry" / dataset_id


def _manifest(database, dataset_id: str, revision: int) -> dict | None:
    root = _root(database, dataset_id)
    candidates = []
    if root.exists():
        for path in root.glob("r*/manifest.json"):
            try:
                number = int(path.parent.name[1:])
                if number <= revision:
                    candidates.append((number, path))
            except ValueError:
                continue
    if not candidates:
        return None
    _, path = max(candidates)
    data = json.loads(path.read_text())
    return {**data, "directory": str(path.parent)}


def precinct_catalog(database, *, state: str | None = None, year: int | None = None,
                     revision: int | None = None) -> dict:
    bound = _bound(database, revision)
    if state and state.upper() not in {s["code"] for s in all_states()}:
        raise ValueError("Unknown state")
    output = []
    for source in precinct_sources():
        if state and source["state"] != state.upper() or year and source["year"] != year:
            continue
        manifest = _manifest(database, source["id"], bound)
        output.append({**source, "source": source["provider"], "loaded": manifest is not None,
            "status": "loaded" if manifest else "not_loaded", "revision": manifest["revision"] if manifest else None,
            "offices": manifest.get("offices", []) if manifest else [],
            "coverage": manifest.get("coverage") if manifest else None,
            "warnings": list(dict.fromkeys((manifest.get("warnings", []) if manifest else [HISTORICAL_WARNING]) +
                ([RETROSPECTIVE_WARNING] if source["provider"] == "vest" else []))),
            "license": "CC BY 4.0" if source["provider"] == "vest" else "Public election-authority records"})
    return {"revision": bound, "datasets": output,
        "coverage_policy": "All 50 states have an original-producer 2020 paired-boundary inventory. Only downloaded and validated bundles are map-ready; no national precinct geometry is loaded at startup."}


def _bound(database, revision):
    latest = database.latest_revision()
    bound = latest if revision is None else revision
    if isinstance(bound, bool) or not isinstance(bound, int) or not 0 <= bound <= latest:
        raise ValueError("Dataset revision is outside the available evidence range")
    return bound


def _shape_records(path: str):
    """Transform the declared source CRS; absent CRS is a validation failure."""
    with zipfile.ZipFile(path) as archive:
        stems = [n[:-4] for n in archive.namelist() if n.lower().endswith(".shp") and not n.startswith("__MACOSX")]
        if len(stems) != 1:
            raise ValueError("A precinct bundle must contain exactly one explicit shapefile")
        stem = stems[0]
        prj = archive.read(stem + ".prj").decode("utf-8-sig")
        transformer = Transformer.from_crs(CRS.from_wkt(prj), CRS.from_epsg(4326), always_xy=True)
        reader = shapefile.Reader(shp=io.BytesIO(archive.read(stem + ".shp")),
            shx=io.BytesIO(archive.read(stem + ".shx")), dbf=io.BytesIO(archive.read(stem + ".dbf")),
            encoding="utf-8", encodingErrors="replace")
        for index, item in enumerate(reader.iterShapeRecords()):
            geometry = transform(shape(item.shape.__geo_interface__), transformer.transform, interleaved=False)
            repaired = False
            if not geometry.is_valid:
                geometry = make_valid(geometry)
                repaired = True
            if geometry.geom_type == "GeometryCollection":
                from shapely.ops import unary_union
                geometry = unary_union([g for g in geometry.geoms if g.geom_type in {"Polygon", "MultiPolygon"}])
            if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError(f"Source record {index + 1} has no defensible polygon")
            if not all(math.isfinite(value) for value in geometry.bounds):
                raise ValueError("Non-finite projected coordinates")
            yield index, item.record.as_dict(), geometry, repaired


def _state_documentation(text: str, state: str) -> str:
    names = {s["name"]: s["code"] for s in all_states()}
    chunks = re.split(r"(?m)^([A-Z][A-Za-z ]+)\r?\n[-]{3,}\r?\n", text)
    for i in range(1, len(chunks), 2):
        if names.get(chunks[i]) == state:
            return chunks[i] + "\n" + chunks[i + 1]
    raise ValueError(f"Publisher methodology for {state} was not found")


def _vest_fields(documentation: str) -> dict[str, dict]:
    output = {}
    paragraph_codes = {}
    for paragraph in re.split(r"\n\s*\n", documentation):
        entries = re.findall(r"(?m)^([GCSR]20[A-Z0-9]{7})\s+-\s+(.+)$", paragraph)
        for code, _ in entries:
            group = [field for field, _ in entries if field[:6] == code[:6]]
            paragraph_codes[code] = stable_id(*sorted(group))
    for code, label in re.findall(r"(?m)^([GCSR]20[A-Z0-9]{7})\s+-\s+(.+)$", documentation):
        office_code, party_code = code[3:6], code[6]
        office = "US HOUSE" if re.fullmatch(r"H(\d\d|AL)", office_code) else OFFICES.get(office_code)
        if not office:
            continue
        name = re.sub(r"\s*\([^)]*\)\s*$", "", label.strip()).strip()
        party_label = re.search(r"\(([^()]*)\)\s*$", label)
        party = PARTIES.get(party_code)
        if party_code not in {"D", "R"} and party_label:
            party = normal_party(party_label.group(1).removesuffix(" Party"))
        output[code] = {"name": name, "party": party or "OTHER", "office": office,
            "district": office_code[1:] if office == "US HOUSE" and office_code.startswith("H") else "STATEWIDE",
            "stage": {"G": "GEN", "C": "RECOUNT", "S": "GEN", "R": "RUNOFF"}[code[0]],
            "special": code[0] == "S", "recount": code[0] == "C", "office_code": office_code,
            "documented_option_set": paragraph_codes[code]}
    return output


def _vest_bundle(source, document, documentation: str):
    state, year = source["state"], source["year"]
    state_text = _state_documentation(documentation, state)
    fields = _vest_fields(state_text)
    if not any(value["office"] == "PRESIDENT" for value in fields.values()):
        raise ValueError("Publisher candidate codebook does not establish presidential options")
    groups = defaultdict(set)
    for option in fields.values():
        groups[(option["stage"], option["special"], option["office"], option["district"])].add(option["documented_option_set"])
    invalidated = []
    for key, values in groups.items():
        if len(values) > 1:
            invalidated.append("contest:" + stable_id(source["id"], *key))
    features, rows, repaired_count = [], [], 0
    unknown_vote_fields = set()
    for index, properties, geometry, repaired in _shape_records(document.path):
        repaired_count += int(repaired)
        # Record identity belongs to this archived publisher bundle, not to a
        # Census VTD or a supposedly unchanged precinct in another election.
        native_id = f"record:{index + 1:06d}"
        geo_id = f"precinct:VEST:{state}:{year}:{document.sha256[:12]}:{index + 1:06d}"
        name = str(next((properties[k] for k in ("NAME", "NAME20", "PRECINCT", "PRECINCTNA", "PCTNAME", "PREC", "PCT", "VTDNAME", "VTDST", "VTDST20", "CNTYVTD", "PCTKEY", "GEOID20", "GEOID") if properties.get(k)), native_id))
        county = str(properties.get("COUNTYFP", properties.get("COUNTYFP20", properties.get("CNTY", ""))))
        if county.isdigit() and len(county) <= 3:
            county = county.zfill(3)
        county_fips = next(s["fips"] for s in all_states() if s["code"] == state) + county if re.fullmatch(r"\d{3}", county) else None
        county_info = county_match(state, county_fips) if county_fips else None
        props = {"id": geo_id, "name": name, "state": state, "year": year, "native_id": native_id,
            "county_code": county, "county_id": county_info["canonical_id"] if county_info else None,
            "county_name": county_info["name"] if county_info else None, "boundary_vintage": str(year), "join_status": "publisher_paired_record",
            "geometry_repaired": repaired, "bounds": list(geometry.bounds)}
        features.append({"type": "Feature", "id": geo_id, "properties": props, "geometry": mapping(geometry)})
        for field, votes in properties.items():
            if re.fullmatch(r"[GCSR]20[A-Z0-9]{7}", field) and field not in fields:
                unknown_vote_fields.add(field)
            if field not in fields:
                continue
            option = fields[field]
            group_key = (option["stage"], option["special"], option["office"], option["district"])
            multiple_option_sets = len(groups[group_key]) > 1
            contest_id = "contest:" + stable_id(source["id"], *group_key,
                *([option["documented_option_set"]] if multiple_option_sets else []))
            group_names = [value["name"] for value in fields.values() if value["documented_option_set"] == option["documented_option_set"]]
            contest_detail = " · option set: " + " / ".join(group_names) if multiple_option_sets else ""
            # Offices whose multiple seats are not established by this schema
            # retain response shares but never establish a unique winner.
            magnitude = 2 if option["office_code"] in {"COC", "SBE", "UBR", "COU"} else 1
            amount = number(votes)
            rows.append({"state": state, "year": year, "office": option["office"], "contest_id": contest_id,
                "contest_name": f"{option['office'].title()} · {option['district']}{contest_detail} · VEST historical context" + (" · recount" if option["recount"] else ""),
                "district": option["district"], "stage": option["stage"], "special": option["special"],
                "date": election_day(year), "magnitude": magnitude, "kind": "candidate", "candidate": option["name"],
                "party": option["party"], "option_id": "option:" + stable_id(contest_id, field), "geography_id": geo_id,
                "geography_level": "precinct", "geography_name": name, "votes": amount, "mode": "TOTAL", "round": "reported",
                "source_modes": ["PUBLISHER PAIRED TOTAL"], "parties": [option["party"]],
                "partial_suppression": amount is None, "writein": "write" in option["name"].lower()})
    warnings = [HISTORICAL_WARNING,
        RETROSPECTIVE_WARNING,
        "VEST harmonizes precinct boundaries and returns. Some non-geographic absentee/provisional returns are allocated or estimated by the producer; these are not independently observed resident-precinct votes. Read the state methodology.",
        "Source-record IDs are tied to the archived bundle. They do not establish a cross-election precinct crosswalk."]
    if unknown_vote_fields:
        warnings.append("Fields without a supported, named publisher codebook entry are withheld: " + ", ".join(sorted(unknown_vote_fields)))
    return features, rows, {"warnings": warnings, "methodology": state_text, "geometry_repairs": repaired_count,
        "offices": sorted({r["office"] for r in rows}), "unknown_vote_fields": sorted(unknown_vote_fields),
        "invalidated_contest_ids": invalidated, "precinct_parser_version": PARSER_VERSION,
        "temporal_basis": "retrospective_publisher_harmonization"}


def _numeric_padding(value: str) -> str:
    """Reviewed identifier equivalence: 0003 and 3; punctuation/letters stay exact."""
    text = str(value).strip().upper()
    return str(int(text)) if re.fullmatch(r"\d+", text) else text


def _nc_native_index(path: str, year: int):
    index = defaultdict(dict)
    with zipfile.ZipFile(path) as archive:
        for filename in archive.namelist():
            if not filename.lower().endswith(".csv") or filename.startswith("__MACOSX"):
                continue
            for row in csv.DictReader(io.TextIOWrapper(archive.open(filename), encoding="utf-8-sig")):
                parent = row.get("jurisdiction_fips") or row.get("jurisdiction_name") or row.get("county_fips")
                precinct = str(row.get("precinct") or "UNSPECIFIED")
                geo_id = f"precinct:NC:{year}:{stable_id(parent, precinct)}"
                county = county_match("NC", str(row.get("county_fips", "")), str(row.get("county_name", "")))
                if county:
                    index[(county["canonical_id"], _numeric_padding(precinct))][geo_id] = {"id": geo_id, "name": precinct,
                        "county_id": county["canonical_id"], "raw_precinct": precinct}
    return index


def _nc_bundle(database, source, document, *, progress=None, offline=False):
    from .atlas.ingest import load_dataset
    source_id = source["result_dataset_id"]
    with database.session() as session:
        dataset = session.get(DatasetState, source_id)
        snapshot = session.get(Snapshot, dataset.payload.get("snapshot_id")) if dataset and dataset.payload.get("snapshot_id") else None
    if not snapshot:
        if progress:
            progress({"stage": "results", "message": "Downloading the original-producer precinct returns needed for a validated join"})
        load_dataset(database, source_id, deep=True, offline=offline, progress=progress)
        with database.session() as session:
            dataset = session.get(DatasetState, source_id)
            snapshot = session.get(Snapshot, dataset.payload["snapshot_id"])
    index = _nc_native_index(snapshot.path, source["year"])
    features, crosswalks, unmatched, ambiguous, repairs = [], [], [], [], 0
    seen = set()
    for record_index, props, geometry, repaired in _shape_records(document.path):
        repairs += int(repaired)
        county = county_match("NC", name=str(props.get("county_nam", props.get("county_name", ""))))
        key = (county["canonical_id"], _numeric_padding(str(props.get("prec_id", "")))) if county else None
        candidates = index.get(key, {})
        original_id = str(props.get("id", record_index + 1))
        if len(candidates) != 1:
            record = {"native_boundary_id": original_id, "county": props.get("county_nam"),
                "precinct": props.get("prec_id"), "reason": "ambiguous_native_key" if candidates else "no_matching_published_precinct"}
            (ambiguous if candidates else unmatched).append(record)
            continue
        match = next(iter(candidates.values()))
        if match["id"] in seen:
            raise ValueError("More than one boundary record matched the same precinct; a reviewed union is required")
        seen.add(match["id"])
        properties = {**match, "state": "NC", "year": source["year"], "native_id": original_id,
            "native_precinct": str(props.get("prec_id", "")), "official_name": props.get("enr_desc"),
            "boundary_vintage": source["vintage"], "join_status": "unique_county_and_native_precinct_id",
            "join_method": "exact_identifier_with_numeric_zero_padding_only", "bounds": list(geometry.bounds),
            "geometry_repaired": repaired}
        features.append({"type": "Feature", "id": match["id"], "properties": properties, "geometry": mapping(geometry)})
        crosswalks.append({"id": stable_id(source["id"], document.sha256, original_id), "source_id": source["id"],
            "source_geography_id": f"ncsbe:{source['vintage']}:{original_id}", "target_geography_id": match["id"],
            "status": "exact_native_identifier", "payload": {"source_snapshot_sha256": document.sha256,
                "result_snapshot_id": snapshot.id, "method": properties["join_method"], "county_id": match["county_id"],
                "native_precinct": properties["native_precinct"], "result_precinct": match["raw_precinct"], "vintage": source["vintage"]}})
    metadata = {"offices": dataset.payload.get("offices", []), "geometry_repairs": repairs,
        "result_snapshot_id": snapshot.id, "result_dataset_id": source_id,
        "unmatched_boundaries": unmatched, "ambiguous_boundaries": ambiguous,
        "coverage": {"source_boundary_records": len(features) + len(unmatched) + len(ambiguous),
            "matched_boundaries": len(features), "unmatched_boundary_count": len(unmatched),
            "ambiguous_boundary_count": len(ambiguous), "result_native_units": sum(len(v) for v in index.values())},
        "warnings": [HISTORICAL_WARNING,
            "Only uniquely matched physical precincts are mapped. Administrative absentee, early-voting-site, provisional, transfer, and unmatched returns remain in the evidence table, never allocated to residential polygons.",
            "Mapped precinct returns can exclude substantial non-geographic voting methods. Map totals are not statewide turnout or a complete picture of resident precinct voting.",
            "Numeric precinct identifiers may differ only by zero padding. Letters and punctuation are never fuzzily matched.",
            "The election-year boundary snapshot is dated explicitly; later precinct changes are not projected backward."]}
    return features, crosswalks, metadata


def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))
    pending.replace(path)


def load_precinct_dataset(database, dataset_id: str, *, progress=None, offline=False, force=False) -> dict:
    ensure_schema(database)
    source = next((s for s in precinct_sources() if s["id"] == dataset_id), None)
    if not source:
        raise ValueError("Unknown verified precinct boundary dataset")
    if source.get("restricted"):
        raise ValueError("Restricted publisher data are unavailable for unattended download")
    previous = _manifest(database, dataset_id, database.latest_revision())
    if previous and not force and previous.get("parser_version") == PARSER_VERSION:
        return {"status": "unchanged", "dataset_id": dataset_id, "revision": previous["revision"],
            "record_count": previous["coverage"]["matched_boundaries"], "warnings": previous["warnings"]}
    fetcher = Fetcher(database.settings, offline=offline)
    try:
        if progress:
            progress({"stage": "download", "message": f"Archiving {source['title']}", "dataset_id": dataset_id})
        document = fetcher.fetch(source["url"])
        documentation = fetcher.fetch(source["documentation_url"])
        if source["provider"] == "vest":
            metadata_document = fetcher.fetch(VEST_METADATA)
            if progress:
                progress({"stage": "geometry", "message": "Transforming the declared CRS and validating paired publisher records"})
            features, rows, metadata = _vest_bundle(source, document, Path(documentation.path).read_text())
            if not features or not rows:
                raise ValueError("No valid paired precinct geometry and named returns")
            result = _publish(database, {**source, "tier": 3}, document, rows, metadata)
            revision, snapshot_id = result["revision"], result["snapshot_id"]
            metadata["coverage"] = {"source_boundary_records": len(features), "matched_boundaries": len(features),
                "unmatched_boundary_count": 0, "ambiguous_boundary_count": 0, "result_native_units": len(features)}
            crosswalks = []
            extra_documents = [documentation, metadata_document]
        else:
            features, crosswalks, metadata = _nc_bundle(database, source, document, progress=progress, offline=offline)
            if not features:
                raise ValueError("No precinct had a unique defensible identifier join")
            with database.lock, database.session() as session, session.begin():
                revision_row = Revision(reason=f"Validated precinct boundaries: {source['title']}", source_id=source["id"])
                session.add(revision_row)
                session.flush()
                revision = revision_row.id
                snapshot = Snapshot(source_id=source["id"], url=document.url, sha256=document.sha256,
                    path=document.path, content_type=document.content_type, retrieved_at=document.retrieved_at,
                    byte_count=document.byte_count, revision=revision)
                session.add(snapshot)
                session.flush()
                snapshot_id = snapshot.id
            extra_documents = [documentation]
        # Original files are immutable. Each processed LOD and its manifest is
        # versioned; pinned investigations never pick a later geometry revision.
        directory = _root(database, dataset_id) / f"r{revision}"
        for lod, tolerance in LOD_TOLERANCE.items():
            if progress:
                progress({"stage": "geometry", "message": f"Caching {lod} geometry", "completed": len(features), "total": len(features)})
            selected = []
            for feature in features:
                geometry = shape(feature["geometry"])
                simplified = geometry.simplify(tolerance, preserve_topology=True) if tolerance else geometry
                selected.append({**feature, "geometry": mapping(simplified)})
            _write_json(directory / f"{lod}.geojson", {"type": "FeatureCollection", "features": selected})
        with database.lock, database.session() as session, session.begin():
            refs = [{"snapshot_id": snapshot_id, "source_id": source["id"], "url": document.url,
                "sha256": document.sha256, "revision": revision, "archive_path": document.path}]
            for doc in extra_documents:
                archived = Snapshot(source_id=source["id"] + "_methodology", url=doc.url, sha256=doc.sha256,
                    path=doc.path, content_type=doc.content_type, retrieved_at=doc.retrieved_at,
                    byte_count=doc.byte_count, revision=revision)
                session.add(archived)
                session.flush()
                refs.append({"snapshot_id": archived.id, "source_id": archived.source_id, "url": doc.url,
                    "sha256": doc.sha256, "revision": revision, "archive_path": doc.path})
            if metadata.get("result_snapshot_id"):
                original = session.get(Snapshot, metadata["result_snapshot_id"])
                refs.append({"snapshot_id": original.id, "source_id": original.source_id, "url": original.url,
                    "sha256": original.sha256, "revision": original.revision, "archive_path": original.path})
            if crosswalks:
                session.execute(insert(GeographicCrosswalk).prefix_with("OR IGNORE"), crosswalks)
            manifest = {"dataset_id": dataset_id, "state": source["state"], "year": source["year"],
                "title": source["title"], "provider": source["provider"], "source_url": source["source_url"],
                "parser_version": PARSER_VERSION, "revision": revision, "created_at": utc_now(),
                "boundary_vintage": source.get("vintage", str(source["year"])), "source_sha256": document.sha256,
                "source_refs": refs, "lods": {key: {"tolerance_degrees": value, "topology_preserving": True} for key, value in LOD_TOLERANCE.items()},
                **metadata}
            manifest["files"] = {key: {"filename": f"{key}.geojson", "sha256": hashlib.sha256((directory / f"{key}.geojson").read_bytes()).hexdigest()} for key in LOD_TOLERANCE}
            dataset = session.get(DatasetState, dataset_id)
            if not dataset:
                dataset = DatasetState(id=dataset_id, dataset_id=dataset_id, state=source["state"], status="loaded")
                session.add(dataset)
            dataset.status, dataset.revision, dataset.checked_at, dataset.error = "loaded", revision, utc_now(), None
            dataset.record_count = len(features)
            dataset.payload = {"parser_version": PARSER_VERSION, "snapshot_id": snapshot_id, "offices": metadata["offices"],
                "coverage": metadata["coverage"], "manifest": str(directory / "manifest.json"), "warnings": metadata["warnings"]}
        _write_json(directory / "manifest.json", manifest)
        _geometry_file.cache_clear()
        _precinct_values.cache_clear()
        return {"status": "loaded", "dataset_id": dataset_id, "revision": revision, "record_count": len(features),
            "coverage": metadata["coverage"], "warnings": metadata["warnings"]}
    finally:
        fetcher.close()


@lru_cache(maxsize=8)
def _geometry_file(path: str, digest: str) -> dict:
    content = Path(path).read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Cached precinct geometry failed its manifest checksum; reload the archived source")
    return json.loads(content)


@lru_cache(maxsize=16)
def _precinct_values(database, state, year, office, revision, contest_id):
    from .atlas.models import BallotOption, Contest
    rows = _rows(database, state=state, years=[year], office=office, level="precinct", revision=revision,
        contest_id=contest_id)
    with database.session() as session:
        options = {r.id: record_dict(r) for r in session.scalars(select(BallotOption).where(BallotOption.id.in_({r["option_id"] for r in rows})))}
        contests = {r.id: record_dict(r) for r in session.scalars(select(Contest).where(Contest.id.in_({r["contest_id"] for r in rows})))}
    values = _geographies(rows, options, contests)
    return values, contests


def parse_bbox(value: str | list[float] | None) -> tuple[float, float, float, float] | None:
    if value is None or value == "":
        return None
    try:
        parts = [float(x) for x in (value.split(",") if isinstance(value, str) else value)]
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox must contain west,south,east,north") from exc
    if len(parts) != 4 or not all(math.isfinite(x) for x in parts):
        raise ValueError("bbox must contain four finite coordinates")
    west, south, east, north = parts
    if not -180 <= west <= 180 or not -180 <= east <= 180 or not -90 <= south < north <= 90:
        raise ValueError("bbox is outside longitude/latitude bounds")
    return west, south, east, north


def _intersects(bounds, bbox):
    west, south, east, north = bbox
    minx, miny, maxx, maxy = bounds
    vertical = maxy >= south and miny <= north
    return vertical and (maxx >= west and minx <= east if west <= east else maxx >= west or minx <= east)


def precinct_map(database, *, state: str, year: int = 2020, office: str = "PRESIDENT",
                 dataset_id: str | None = None, revision: int | None = None, bbox=None,
                 lod: str = "overview", contest_id: str | None = None, limit: int = 20000) -> dict:
    bound = _bound(database, revision)
    state = state.upper()
    if state not in {s["code"] for s in all_states()}:
        raise ValueError("Unknown state")
    if lod not in LOD_TOLERANCE:
        raise ValueError("lod must be overview, detail, or full")
    if isinstance(limit, bool) or not 1 <= limit <= 20000:
        raise ValueError("Precinct geometry limit must be between 1 and 20000")
    bounds = parse_bbox(bbox)
    catalog = precinct_catalog(database, state=state, year=year, revision=bound)["datasets"]
    source = next((s for s in catalog if s["id"] == dataset_id), None) if dataset_id else next((s for s in catalog if s["loaded"]), catalog[0] if catalog else None)
    if dataset_id and not source:
        raise ValueError("The precinct dataset does not belong to the selected state and election year")
    query = {"state": state, "year": year, "office": office.upper(), "dataset_id": source["id"] if source else dataset_id,
        "revision": bound, "bbox": bounds, "lod": lod, "contest_id": contest_id, "limit": limit}
    base = {"type": "FeatureCollection", "features": [], "revision": bound, "query": query,
        "coverage": {}, "sources": [], "warnings": [HISTORICAL_WARNING],
        "availability": {"status": "not_loaded" if source else "unavailable", "dataset_id": source["id"] if source else None,
            "reason": "Open the verified source bundle to download and validate its boundaries." if source else "No verified paired precinct geometry is catalogued for this state and year. Try the public 2020 bundle or county context."}}
    if not source or not source["loaded"]:
        return base
    manifest = _manifest(database, source["id"], bound)
    if office.upper() not in manifest["offices"]:
        return {**base, "availability": {"status": "unsupported_office", "dataset_id": source["id"], "offices": manifest["offices"],
            "reason": "This source bundle does not contain named, supported results for that office."}, "warnings": manifest["warnings"], "sources": manifest["source_refs"]}
    descriptor = manifest["files"][lod]
    geojson = _geometry_file(str(Path(manifest["directory"]) / descriptor["filename"]), descriptor["sha256"])
    values, contests = _precinct_values(database, state, year, office.upper(), bound, contest_id)
    # A source owns its own exact paired identifiers. Other producers' native
    # precinct records cannot be attached merely because their labels resemble it.
    mapped_ids = {feature["id"] for feature in geojson["features"]}
    by_id = defaultdict(list)
    for row in values:
        by_id[row["id"]].append(row)
    features, available_geometries = [], 0
    for feature in geojson["features"]:
        if bounds and not _intersects(feature["properties"]["bounds"], bounds):
            continue
        available_geometries += 1
        if len(features) >= limit:
            continue
        matches = by_id.get(feature["id"], [])
        current = matches[0] if len(matches) == 1 else None
        suppressed = bool(current and current.get("partial_suppression"))
        properties = {**feature["properties"], "total_votes": current["total_votes"] if current and not suppressed else None,
            "reported_total_lower_bound": current["total_votes"] if suppressed else None,
            "dem_share_pct": current["dem_share_pct"] if current else None, "rep_share_pct": current["rep_share_pct"] if current else None,
            "dem_margin_pp": current["dem_margin_pp"] if current else None, "rep_margin_pp": current["rep_margin_pp"] if current else None,
            "margin_pp": current["rep_margin_pp"] if current else None, "options": current["options"] if current else [],
            "source_refs": current["source_refs"] if current else [], "contest_id": current["contest_id"] if current else None,
            "data_status": ("incomplete" if suppressed else "reported") if current else ("choose_contest" if len(matches) > 1 else "missing"),
            "partial_suppression": suppressed,
            "available_contest_ids": [row["contest_id"] for row in matches],
            "winner_status": current["winner_status"] if current else "unavailable",
            "election_system": current["election_system"] if current else None, "round": current["round"] if current else None}
        features.append({**feature, "properties": properties})
    mapped = [r for r in values if r["id"] in mapped_ids]
    unmatched = [r for r in values if r["id"] not in mapped_ids]
    compatible_totals = len({r["contest_id"] for r in values}) <= 1
    partial = any(r.get("partial_suppression") for r in values)
    total = sum(r["total_votes"] for r in values) if compatible_totals and not partial else None
    mapped_total = sum(r["total_votes"] for r in mapped) if compatible_totals and not partial else None
    visible_total = sum(f["properties"]["total_votes"] or 0 for f in features) if compatible_totals and not partial else None
    coverage = {**manifest["coverage"], "loaded_boundary_revision": manifest["revision"],
        "reported_result_areas": len({r["id"] for r in values}), "matched_result_areas": len({r["id"] for r in mapped}),
        "unmapped_result_areas": len({r["id"] for r in unmatched}), "all_reported_candidate_votes": total,
        "mapped_candidate_votes": mapped_total, "unmapped_candidate_votes": total - mapped_total if total is not None else None,
        "mapped_votes_pct": 100 * mapped_total / total if total else None, "visible_candidate_votes": visible_total,
        "visible_features": len(features), "bbox_available_features": available_geometries,
        "partial_suppression_count": len([r for r in values if r.get("partial_suppression")]),
        "truncated": available_geometries > len(features), "scope": "source-native candidate returns, not election participation"}
    warnings = list(manifest["warnings"])
    if source["provider"] == "vest" and RETROSPECTIVE_WARNING not in warnings:
        warnings.append(RETROSPECTIVE_WARNING)
    if partial:
        warnings.append("Suppressed or incomplete source precincts are patterned as unavailable; their known lower bounds do not establish complete candidate-vote totals.")
    if coverage["truncated"]:
        warnings.append("This viewport exceeds the geometry limit; zoom in for the complete selected area. Missing polygons are not reported zeroes.")
    if any(f["properties"]["data_status"] == "choose_contest" for f in features):
        warnings.append("Some precincts report multiple distinct contests for this office. Select a specific contest before mapping values; unrelated ballot items are not added together.")
    return {**base, "features": features, "coverage": coverage, "warnings": warnings, "sources": manifest["source_refs"],
        "availability": {"status": "loaded", "dataset_id": source["id"], "offices": manifest["offices"]},
        "boundary_vintage": manifest["boundary_vintage"], "methodology": manifest.get("methodology"),
        "temporal_basis": "retrospective_publisher_harmonization" if source["provider"] == "vest" else "dated_official_boundary_snapshot",
        "unmapped_results": [{"id": row["id"], "name": row["name"], "total_votes": row["total_votes"],
            "contest_id": row["contest_id"], "source_refs": row["source_refs"]} for row in unmatched],
        "contests": list(contests.values()), "unmatched_boundaries": manifest.get("unmatched_boundaries", []),
        "ambiguous_boundaries": manifest.get("ambiguous_boundaries", []),
        "legend": {"metric": "rep_margin_pp", "unit": "percentage points", "definition": "Republican minus Democratic share of all named options",
            "domain": [-100, 100], "bins": [-100, -30, -15, -5, 0, 5, 15, 30, 100],
            "colors": ["#17478e", "#2469bc", "#4b93df", "#a8ccef", "#f3bdad", "#e9856e", "#cf4e43", "#9d262b"],
            "missing": "No supported value; never zero", "date": election_day(year), "year": year}}
