"""Paired result comparisons with explicit contest, round, and boundary review.

The county standard is material reporting-unit continuity, not a claim that two
cartographic files are pixel-identical. No area weights or votes are allocated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select

from .archive import Fetcher
from .atlas.models import Contest
from .atlas.store import _contest_identity, result_query
from .db import Revision, Snapshot, record_dict
from .geography import county_index

CENSUS_CHANGES = (
    "https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.html",
    "https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.2010.html",
)
REVIEWED_START, REVIEWED_END = 2018, 2024
# Explicitly preserve problematic source identifiers, including historical
# deleted IDs, instead of using a name to overwrite their geographic meaning.
WITHHELD_COUNTIES = {"county:51515", "county:46113", "county:02261", "county:02270"}


def archive_boundary_review(database, *, offline=False) -> dict:
    """Archive the actual Census reference used by the documented review."""
    fetcher = Fetcher(database.settings, offline=offline)
    try:
        previous = _review(database)
        if previous:
            return previous
        documents = [fetcher.fetch(url) for url in CENSUS_CHANGES]
        # A changed publisher layout must not silently validate every county.
        for doc in documents:
            text = Path(doc.path).read_text()
            if "Substantial Changes" not in text or "Connecticut" not in text and "Chugach" not in text:
                raise ValueError("County-change reference did not contain the reviewed material")
        result = {"reviewed_start": REVIEWED_START, "reviewed_end": REVIEWED_END,
            "standard": "same reported Census county identifier; no Census-listed substantial boundary or county-equivalent change during the comparison interval",
            "limitations": "The Census inventory defines substantial changes using population/area thresholds. Minor legal adjustments and map generalization are not certified identical. Comparisons describe matched reported counties and do not redistribute votes.",
            "sources": [{"url": doc.url, "sha256": doc.sha256, "archive_path": doc.path,
                "retrieved_at": doc.retrieved_at} for doc in documents]}
        with database.lock, database.session() as session, session.begin():
            revision = Revision(reason="Reviewed Census material county continuity, 2018–2024", source_id="census_county_changes")
            session.add(revision)
            session.flush()
            result["revision"] = revision.id
            for document, source in zip(documents, result["sources"]):
                snapshot = Snapshot(source_id="census_county_changes", url=document.url, sha256=document.sha256,
                    path=document.path, content_type=document.content_type, retrieved_at=document.retrieved_at,
                    byte_count=document.byte_count, revision=revision.id)
                session.add(snapshot)
                session.flush()
                source.update({"snapshot_id": snapshot.id, "revision": revision.id})
            path = database.settings.data_dir / "geometry" / "county-boundary-review.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2))
        return result
    finally:
        fetcher.close()


def boundary_eligibility(state: str, geography_id: str, level: str, year: int, baseline: int,
                         *, review_available: bool = True) -> dict:
    if year == baseline:
        return {"eligible": True, "reason": "same_election", "standard": "identical selected election"}
    if level == "state" and min(year, baseline) >= 1960:
        return {"eligible": True, "reason": "compatible_state_boundaries", "standard": "same state reporting unit"}
    if level != "county":
        return {"eligible": False, "reason": "reviewed_crosswalk_required", "standard": "native precinct/district continuity has not been established"}
    if not REVIEWED_START <= min(year, baseline) <= max(year, baseline) <= REVIEWED_END:
        return {"eligible": False, "reason": "outside_reviewed_boundary_window", "standard": f"county review covers {REVIEWED_START}–{REVIEWED_END}"}
    if not review_available:
        return {"eligible": False, "reason": "boundary_review_not_archived", "standard": "download the original Census reference before activating county differences"}
    if state == "AK":
        return {"eligible": False, "reason": "native_reporting_areas_not_counties", "standard": "Alaska election districts are not borough/census-area equivalents"}
    if state == "CT":
        return {"eligible": False, "reason": "county_equivalents_changed", "standard": "eight historic counties and nine planning regions require an explicit reviewed crosswalk"}
    if geography_id in WITHHELD_COUNTIES or not re.fullmatch(r"county:\d{5}", geography_id):
        return {"eligible": False, "reason": "changed_or_noncanonical_identifier", "standard": "original identifiers are preserved without allocation"}
    if geography_id.removeprefix("county:") not in county_index(state)["by_geoid"]:
        return {"eligible": False, "reason": "no_current_canonical_county", "standard": "the original county ID has no validated current Census boundary"}
    return {"eligible": True, "reason": "reviewed_material_county_continuity",
        "standard": "same reported county identifier; no Census-listed substantial change in 2018–2024",
        "limitation": "Minor boundary adjustments are not certified identical; no votes are redistributed."}


def _review(database, revision: int | None = None) -> dict | None:
    path = database.settings.data_dir / "geometry" / "county-boundary-review.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if revision is not None and value.get("revision", 0) > revision:
        return None
    import hashlib
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        return None
    for source in sources:
        sha = source.get("sha256") if isinstance(source, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            return None
        archived = database.settings.archive_dir / sha[:2] / sha
        if not archived.is_file():
            # Sanitized public checkpoints intentionally omit private paths.
            # A URL/hash without the original bytes cannot verify continuity.
            original = source.get("archive_path")
            if not isinstance(original, str) or not original:
                return None
            archived = Path(original)
        if not archived.is_file() or hashlib.sha256(archived.read_bytes()).hexdigest() != sha:
            return None
        source["archive_path"] = str(archived)
    return value


def compare_results(database, *, state: str, year: int = 2024, baseline: int = 2020,
                    office: str = "PRESIDENT", geography_level: str = "county",
                    revision: int | None = None, contest_id: str | None = None,
                    geography_ids: list[str] | None = None, limit: int = 200, offset: int = 0) -> dict:
    current = result_query(database, state=state, year=year, baseline=None, office=office,
        geography_level=geography_level, revision=revision, contest_id=contest_id,
        geography_ids=geography_ids, limit=limit if geography_level == "precinct" else None, offset=offset)
    bound = current["revision"]
    with database.session() as session:
        chosen = session.get(Contest, contest_id) if contest_id else None
        if chosen and (chosen.state != state.upper() or chosen.year != year or chosen.office != office.upper()):
            raise ValueError("Selected contest is outside the comparison scope")
        ids = list(session.scalars(select(Contest).where(Contest.state == state.upper(), Contest.year == baseline,
            Contest.office == office.upper())))
        baseline_id = next((row.id for row in ids if chosen and _contest_identity(record_dict(chosen)) == _contest_identity(record_dict(row))), None)
    earlier = result_query(database, state=state, year=baseline, baseline=None, office=office,
        geography_level=geography_level, revision=bound, contest_id=baseline_id,
        geography_ids=geography_ids, limit=limit if geography_level == "precinct" else None, offset=offset)
    if chosen and baseline_id is None:
        earlier["geographies"] = []
        earlier["totals"] = {"candidate_votes": None}
    lookup = {row["id"]: row for row in earlier["geographies"]}
    current_contests = {row["id"]: row for row in current["contests"]}
    earlier_contests = {row["id"]: row for row in earlier["contests"]}
    current_ids = {row["id"] for row in current["geographies"]}
    # More than one contest for one place cannot be collapsed to a single margin.
    ambiguous_current = {row["id"] for row in current["geographies"] if sum(other["id"] == row["id"] for other in current["geographies"]) > 1}
    ambiguous_old = {row["id"] for row in earlier["geographies"] if sum(other["id"] == row["id"] for other in earlier["geographies"]) > 1}
    review = _review(database, bound)
    rows, matched, eligible_rows = [], 0, 0
    for row in current["geographies"]:
        old = lookup.get(row["id"])
        boundary = boundary_eligibility(state.upper(), row["id"], geography_level, year, baseline,
            review_available=review is not None)
        contest = current_contests.get(row['contest_id'], {})
        if str(contest.get('district', 'STATEWIDE')).upper() != 'STATEWIDE' and year != baseline:
            boundary = {"eligible": False, "reason": "contest_district_crosswalk_required",
                "standard": "The contest's district, including its intersection with a county, needs a reviewed boundary crosswalk."}
        reason = boundary["reason"]
        eligible = bool(old and boundary["eligible"])
        if not old:
            reason, eligible = (boundary["reason"] if boundary["reason"] in {"county_equivalents_changed", "native_reporting_areas_not_counties", "changed_or_noncanonical_identifier"} else "missing_baseline"), False
        elif row["id"] in ambiguous_current or row["id"] in ambiguous_old:
            reason, eligible = "select_one_semantically_matching_contest", False
        elif _contest_identity(current_contests.get(row["contest_id"], {})) != _contest_identity(earlier_contests.get(old["contest_id"], {})):
            reason, eligible = "contest_semantics_differ", False
        elif row.get("round") == "reported_round_unspecified" or old.get("round") == "reported_round_unspecified" or row.get("round") != old.get("round"):
            reason, eligible = "round_provenance_required", False
        elif row.get("partial_suppression") or old.get("partial_suppression"):
            reason, eligible = "suppressed_or_incomplete_returns", False
        elif row.get("rep_margin_pp") is None or old.get("rep_margin_pp") is None:
            reason, eligible = "both_party_options_required_for_partisan_swing", False
        matched += int(old is not None)
        eligible_rows += int(eligible)
        delta_votes = row["total_votes"] - old["total_votes"] if eligible else None
        rows.append({"id": row["id"], "name": row["name"], "current_votes": row["total_votes"],
            "baseline_votes": old["total_votes"] if old else None, "vote_change": delta_votes,
            "vote_change_pct": 100 * delta_votes / old["total_votes"] if delta_votes is not None and old["total_votes"] else None,
            "current_margin_pp": row.get("rep_margin_pp"), "baseline_margin_pp": old.get("rep_margin_pp") if old else None,
            "change_pp": row["rep_margin_pp"] - old["rep_margin_pp"] if eligible else None,
            "eligible": eligible, "reason": reason, "boundary_review": boundary,
            "current_contest_id": row["contest_id"], "baseline_contest_id": old["contest_id"] if old else None,
            "source_refs": row["source_refs"] + (old["source_refs"] if old else [])})
    matched_current = sum(row["current_votes"] for row in rows if row["eligible"])
    matched_baseline = sum(row["baseline_votes"] for row in rows if row["eligible"])
    snapshot_ids = {ref["snapshot_id"] for row in rows for ref in row["source_refs"]}
    with database.session() as session:
        sources = [record_dict(r) for r in session.scalars(select(Snapshot).where(Snapshot.id.in_(snapshot_ids)))]
    warnings = list(dict.fromkeys(current.get("warnings", []) + earlier.get("warnings", []) + [
        "Comparison differences use matched reported units, the same office/contest semantics, and supported counting rounds. They are not current early-vote forecasts.",
        "County continuity means no Census-listed substantial change in the reviewed interval; minor adjustments are not certified identical. No votes are redistributed.",
        "Different source producers can reconcile differently with statewide certified totals. Original source warnings and each side's denominator remain visible."]))
    missing_review = geography_level == "county" and year != baseline and review is None
    if missing_review:
        warnings.append("County differences are withheld because the archived Census boundary-review evidence is unavailable or fails its checksum in this installation. Current and baseline election results remain available separately; original source links alone do not verify boundary continuity.")
    return {"revision": bound, "query": {"state": state.upper(), "year": year, "baseline": baseline,
        "office": office.upper(), "geography_level": geography_level, "contest_id": contest_id,
        "geography_ids": geography_ids, "limit": limit, "offset": offset},
        "current": current, "baseline": earlier, "rows": rows, "sources": sources,
        "coverage": {"matched": matched, "current_only": len(current["geographies"]) - matched,
            "baseline_only": len([r for r in earlier["geographies"] if r["id"] not in current_ids]),
            "eligible": eligible_rows, "withheld": len(rows) - eligible_rows,
            "matched_current_votes": matched_current, "matched_baseline_votes": matched_baseline,
            "matched_vote_change": matched_current - matched_baseline if eligible_rows else None},
        "eligible": eligible_rows > 0, "margin_definition": "Republican minus Democratic percentage points",
        "change_definition": "Current R-minus-D margin minus baseline R-minus-D margin; positive means toward Republican",
        "boundary_sources": review["sources"] if review else [
            {"url": url, "status": "official_reference_only", "verification": "archive_unavailable"}
            for url in CENSUS_CHANGES] if missing_review else [], "warnings": warnings}
