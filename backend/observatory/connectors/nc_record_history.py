"""Aggregate original NC final absentee records into retrospective date histories.

Personal fields never enter normalized observations or diagnostic output. Return
calendar dates and final accepted status have different vintages: this is a
final-accepted cohort reconstruction, never an operational as-reported replay.
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from observatory.domain import ParsedBatch
from observatory.geography import county_index, county_match

from .common import iso_date, observation

DIMENSIONS = {"voter_party_code": "registration", "race": "race", "ethnicity": "ethnicity", "gender": "gender"}


@lru_cache(maxsize=200)
def _county(name: str) -> tuple[str, str]:
    match = county_match("NC", name=name)
    if not match:
        raise ValueError("NC historical record names an unmatched county")
    return match["geoid"], match["name"]


@lru_cache(maxsize=500)
def _date(value: str) -> str | None:
    try:
        return iso_date(value)
    except ValueError:
        return None


def parse_records(records: Any, source: dict, doc: Any, *, expected_final: dict[tuple[str, str], int] | None = None) -> ParsedBatch:
    cycle = int(source["cycle"])
    if source.get("state") != "NC" or cycle != 2016:
        raise ValueError("Only the reviewed NC2016 record schema is supported")
    dates = source.get("native_calendar", {})
    open_ip, close_ip = dates.get("early_in_person_open"), dates.get("early_in_person_close")
    open_mail = dates.get("mail_open")
    statuses, invalid_dates, modes, native_final = Counter(), Counter(), Counter(), Counter()
    daily = Counter()
    names = {}
    seen = set()
    row_count = accepted = duplicate = 0
    for row in records:
        row_count += 1
        status = row["ballot_rtn_status"].strip()
        statuses[status or "Unknown"] += 1
        if status != "ACCEPTED":
            continue
        accepted += 1
        geoid, name = _county(row["county_desc"].strip())
        names[geoid] = name
        native = row["ballot_req_type"].strip()
        if native not in {"ONE-STOP", "MAIL"}:
            raise ValueError("NC2016 contains an unreviewed accepted ballot request type")
        mode = "early_in_person" if native == "ONE-STOP" else "mail"
        native_final[(geoid, mode)] += 1
        modes[mode] += 1
        # Identity is used only in memory to enforce one accepted record per
        # voter. Conflicting accepted records abort instead of choosing a row.
        identity = row.get("ncid", "").strip() or f"{geoid}:{row.get('voter_reg_num', '').strip()}"
        if not identity or identity.endswith(":" ):
            raise ValueError("NC accepted records lack the native identifier required for deduplication")
        if identity in seen:
            duplicate += 1
            raise ValueError("NC final file contains repeated accepted voter identifiers; manual source review required")
        seen.add(identity)
        d = _date(row["ballot_rtn_dt"].strip())
        if d is None or int(d[:4]) != cycle:
            invalid_dates["missing_or_wrong_year"] += 1
            continue
        if mode == "early_in_person" and (not open_ip or not close_ip or not open_ip <= d <= close_ip):
            invalid_dates["outside_documented_in_person_period"] += 1
            continue
        if mode == "mail" and open_mail and d < open_mail:
            invalid_dates["before_documented_mail_period"] += 1
            continue
        if d > f"{cycle}-12-31":
            invalid_dates["after_cycle"] += 1
            continue
        for geographic_id in (geoid, "state"):
            for item_mode in (mode, "all"):
                daily[(d, geographic_id, item_mode, None, None)] += 1
                for column, dimension in DIMENSIONS.items():
                    if geographic_id != "state" and not source.get("include_county_composition", False):
                        continue
                    category = row.get(column, "").strip() or "Unknown"
                    daily[(d, geographic_id, item_mode, dimension, category)] += 1
    del seen
    if not accepted or not daily:
        raise ValueError("NC final records contain no validated accepted ballot return dates")
    if expected_final is not None and dict(native_final) != expected_final:
        raise ValueError("NC final accepted record totals do not match the original published county/method aggregate")
    # A state file is a complete enumerated cohort. An empty county/date cell
    # becomes a calculated zero only after the complete county population and
    # independent final aggregate reconciliation have both been established.
    expected_counties = set(county_index("NC")["by_geoid"])
    if set(names) != expected_counties:
        raise ValueError("NC final accepted cohort does not cover all 100 verified counties")
    series = defaultdict(dict)
    for (d, geography, mode, dimension, category), value in daily.items():
        series[(geography, mode, dimension, category)][d] = value
    native_dates = sorted({key[0] for key in daily})
    common = {
        "parser_version": "nc-record-history-1.0", "reconstruction_basis": "final accepted cohort reconstructed from native ballot return dates",
        "historical_publication_verified": False, "source_vintage": doc.retrieved_at,
        "native_definition": "Final ACCEPTED absentee records grouped by recorded ballot_rtn_dt; includes ONE-STOP and MAIL",
        "report_date_semantics": "recorded_return_date_in_final_file", "event_date_field": "ballot_rtn_dt",
        "final_status_cohort": True, "status_known_at_return_date": False,
        "category_vintage": "Categories as preserved in the final 2016 absentee file; not independently established as-of each return date",
        "classification_window": "Final2016 absentee record vintage",
        "availability_definition": "Later final-status source file; these bytes and acceptance classifications were not necessarily available on each return date",
        "county_state_reconciles": True, "reporting_county_count": 100,
        "final_aggregate_reconciled": expected_final is not None,
        "temporal_coverage_complete": not invalid_dates, "excluded_anomalous_return_dates": sum(invalid_dates.values()),
        "anomalous_date_reasons": dict(invalid_dates), "native_calendar": dates,
        "native_record_count": row_count, "native_accepted_count": accepted,
    }
    observations = []
    for (geography, mode, dimension, category), values in series.items():
        running = 0
        for d in native_dates:
            running += values.get(d, 0)
            # Marginal categories are sparse; absence is not manufactured into a
            # demographic intersection. Unclassified source values stay Unknown.
            if dimension is not None and running == 0:
                continue
            details = {**common, "geoid": None if geography == "state" else geography,
                       "native_geography_id": geography, "daily_event_count": values.get(d, 0),
                       "recorded_return_date": d, "aggregation": "Exact cumulative count of validated final-accepted records through date"}
            observations.append(observation(source, doc, name="North Carolina" if geography == "state" else names[geography],
                kind="state" if geography == "state" else "county", value=running, metric="ballots_accepted",
                date_=d, mode=mode, dimension=dimension, category=category, basis="reconstructed",
                published_at=doc.retrieved_at, metadata=details))
    return ParsedBatch(observations=observations, data_as_of=max(native_dates), warnings=[
        "Retrospective final-accepted cohort. Acceptance and registration classifications may have been established after the recorded return date; this is not operational as-reported validation.",
        "Original record-level files remain in the private local archive; normalized outputs contain aggregates only.",
        "Recorded return dates can differ from actual voting dates. Documented out-of-calendar or anomalous dates are withheld from the timeline, while final accepted totals remain archived.",
        "County/method totals reconcile to the separately published original 2016 aggregate before publication.",
    ], metadata={**common, "source_authority": "North Carolina State Board of Elections", "report_dates": native_dates,
                 "native_status_counts": dict(statuses), "mode_totals": dict(modes), "duplicate_accepted_records": duplicate,
                 "primary_document_url": doc.url})


def collect(source: dict, fetcher: Any) -> ParsedBatch:
    doc = fetcher.fetch(source["url"])
    reference = fetcher.fetch(source["final_aggregate_url"])
    expected = Counter()
    with Path(reference.path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) != 6:
                raise ValueError("NC2016 final aggregate schema changed")
            geoid, _ = _county(row[0])
            mode = "early_in_person" if row[1] == "ONE-STOP" else "mail" if row[1] in {"CIVILIAN", "MILITARY", "OVERSEAS"} else None
            if mode is None:
                raise ValueError("Unreviewed NC2016 final aggregate method")
            expected[(geoid, mode)] += int(row[5])
    with zipfile.ZipFile(doc.path) as archive:
        members = [entry for entry in archive.infolist() if entry.filename == "absentee_20161108.csv"]
        if len(members) != 1 or members[0].file_size > 1_500_000_000:
            raise ValueError("NC2016 ZIP does not match the reviewed bounded record file")
        with archive.open(members[0]) as raw:
            # Latin1 preserves every source byte. All analytical columns in this
            # reviewed vintage use ASCII categories; no personal text is emitted.
            handle = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            records = csv.DictReader((line.replace("\x00", "") for line in handle))
            required = {"county_desc", "ncid", "ballot_req_type", "ballot_rtn_dt", "ballot_rtn_status"}
            if not required.issubset(records.fieldnames or []):
                raise ValueError("NC2016 absentee record schema changed")
            batch = parse_records(records, source, doc, expected_final=dict(expected))
    batch.metadata.update(final_aggregate_url=reference.url, final_aggregate_sha256=reference.sha256,
                          archive_member=members[0].filename)
    for row in batch.observations:
        row.metadata.update(final_aggregate_url=reference.url, final_aggregate_sha256=reference.sha256)
    return batch
