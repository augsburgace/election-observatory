"""Publicly archived original-producer UF 2024 tracker, with native chronology.

Only ordinary public CSV captures are used. This adapter neither requests paid
precinct products nor treats a later current CSV as a historical daily snapshot.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from observatory.domain import ParsedBatch
from observatory.registry import all_states

from .common import document_text, iso_date, number, observation, read_csv
from .uf_election_lab import DIMENSIONS

STATES = {row["code"]: row["name"] for row in all_states()}

ORIGINAL = "https://election.lab.ufl.edu/data-downloads/earlyvote/2024/US.csv"
ATTRIBUTION = "University of Florida Election Lab, Michael P. McDonald, 2024 Early Voting Tracker"


def _date(value):
    try:
        return iso_date(value)
    except ValueError:
        return datetime.strptime(value.strip(), "%m-%d-%Y").date().isoformat()


def parse_row(source, doc, row, captured_at):
    """Return one statewide native report, rejecting template years and future dates."""
    state = row.get("state_abbv", "")
    if state not in STATES:
        raise ValueError("Unknown state in archived UF tracker")
    date_ = _date(row.get("last_update", ""))
    if not date_.startswith("2024-") or date_ > captured_at[:10]:
        raise ValueError("Template, wrong-cycle or future report date in archived UF tracker")
    numeric = {}
    for prefix in ("request", "accept", "inperson", "voted"):
        cell = row.get(prefix + "_all", "")
        if cell not in {"", "NA", "N/A", "0"}:
            numeric[prefix] = number(cell)
    # Explicitly native unsupported request proxies are not applications.
    if state in {"TX", "DE", "DC", "UT", "WA"}:
        numeric.pop("request", None)
    diagnostics = []
    if all(p in numeric for p in ("accept", "inperson", "voted")) and numeric["accept"] + numeric["inperson"] != numeric["voted"]:
        diagnostics.append("Combined participation differs from the separately published mail and in-person totals; combined value withheld")
        numeric.pop("voted")
    observations = []
    for prefix, value in numeric.items():
        metric, mode = {"request": ("ballots_requested", "mail"), "accept": ("ballots_returned", "mail"),
                        "inperson": ("ballots_cast", "early_in_person"), "voted": ("ballots_cast", "all")}[prefix]
        if state in {"IA", "MI"} and prefix in {"request", "accept"}:
            mode = "all"
        if state == "TN" and prefix == "voted":
            mode = "early_in_person"
        if state == "AZ" and prefix == "request":
            metric = "ballots_issued"
        definitions = {"request": "UF tracker native absentee request field; state-specific administrative scope retained",
                       "accept": "UF tracker native accepted/received absentee field; receipt does not establish acceptance or candidate votes",
                       "inperson": "UF tracker native in-person early field; producer classification, not individual candidate choice",
                       "voted": "UF tracker native combined early participation"}
        meta = {"parser_version": "uf-archived-2024-1.0", "academic_fallback": True, "source_tier": 3,
                "attribution": ATTRIBUTION, "license": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
                "license_note": "Personal noncommercial research; review redistribution conditions before publication",
                "upstream_source": row.get("data_source"), "original_url": ORIGINAL,
                "archive_captured_at": captured_at, "native_last_update": row.get("last_update"),
                "report_date_semantics": "Original producer last_update field; not individual voting-event dates",
                "native_definition": definitions[prefix], "original_column": prefix + "_all",
                "reconstruction_basis": "dated original-producer public CSV snapshot, not individual voter histories",
                "contemporary_publication_verified": True, "publication_evidence": "Independent Internet Archive capture, payload SHA1 verified against CDX inventory",
                "method_categories_disjoint": False, "geographic_grain": "statewide only",
                "native_reconciliation_warnings": diagnostics}
        if state in {"IA", "MI"} and prefix in {"accept", "request"}:
            meta["native_definition"] += "; all absentee scope includes in-person absentee where administered; mail-only allocation unavailable"
        if state == "OH":
            meta["party_classification"] = "Ohio primary participation is not party registration; no party breakdown inferred"
        if state in {"KY", "MD"}:
            meta["underlying_report_date_unverified"] = True
        local_source = {**source, "state": state, "cycle": 2024}
        for basis in ("reported", "reconstructed"):
            kw = dict(name=row.get("state") or STATES[state], value=value, metric=metric,
                      date_=date_, kind="state", mode=mode, basis=basis, published_at=captured_at, metadata=meta)
            observations.append(observation(local_source, doc, **kw))
            for dimension, categories in DIMENSIONS.items():
                # Ohio has primary-history status rather than party registration.
                if dimension == "registration" and state in {"OH", "GA", "MI", "MN", "TX", "VA", "WI"}:
                    continue
                cells = [(label, row.get(prefix + "_" + suffix, ""), suffix) for suffix, label in categories]
                entries = [(label, number(cell), suffix) for label, cell, suffix in cells if cell not in {"", "NA", "N/A"}]
                subtotal = sum(v for _, v, _ in entries)
                if subtotal == 0:
                    continue
                if subtotal > value:
                    diagnostics.append(f"{prefix} {dimension} categories exceed the native total; breakdown withheld")
                    continue
                for label, count, suffix in entries:
                    item = observation(local_source, doc, **{**kw, "value": count}, dimension=dimension, category=label)
                    item.metadata = {**meta, "original_column": prefix + "_" + suffix,
                                     "breakdown_sum": subtotal, "breakdown_complete": subtotal == value}
                    observations.append(item)
    return observations, {"state": state, "date": date_, "warnings": sorted(set(diagnostics)), "observations": len(observations)}


def collect(source, fetcher):
    inventory = fetcher.fetch(source["url"])
    rows = json.loads(document_text(inventory))
    header = ["timestamp", "original", "mimetype", "digest", "statuscode"]
    if not isinstance(rows, list) or not rows or rows[0] != header or len(rows) > 101:
        raise ValueError("UF 2024 capture inventory unavailable or exceeds bounded history")
    observations, reports, failures, later_versions = [], {}, [], []
    captures = sorted(rows[1:], key=lambda r: r[0])
    for item in captures:
        if len(item) != 5:
            raise ValueError("Malformed UF archive capture metadata")
        timestamp, original, _, digest, status = item
        if original != ORIGINAL or status != "200" or len(timestamp) != 14 or not timestamp.isdigit():
            raise ValueError("UF capture does not identify the reviewed original public CSV")
        capture = datetime.strptime(timestamp, "%Y%m%d%H%M%S").isoformat() + "Z"
        if date.fromisoformat(capture[:10]).year != 2024:
            continue
        url = f"https://web.archive.org/web/{timestamp}id_/{original}"
        try:
            doc = fetcher.fetch(url)
            actual = base64.b32encode(hashlib.sha1(Path(doc.path).read_bytes()).digest()).decode()
            if actual != digest:
                raise ValueError("UF 2024 payload differs from independent CDX SHA1")
            data = list(read_csv(doc))
            seen = set()
            for row in data:
                state = row.get("state_abbv", "")
                if state in seen:
                    raise ValueError("Duplicate state row in original UF CSV")
                seen.add(state)
                try:
                    values, manifest = parse_row(source, doc, row, capture)
                    if not values:
                        continue
                    key = (state, manifest["date"])
                    if key in reports:
                        later_versions.append({**manifest, "capture": capture, "sha256": doc.sha256})
                        continue
                    for value in values:
                        value.metadata.update(capture_inventory_url=inventory.url, capture_inventory_sha256=inventory.sha256)
                    observations.extend(values)
                    reports[key] = {**manifest, "capture": capture, "source_url": url, "sha256": doc.sha256}
                except ValueError as exc:
                    failures.append({"state": state, "capture": capture, "reason": str(exc)})
        except ValueError as exc:
            failures.append({"capture": capture, "source_url": url, "reason": str(exc)})
    if not observations:
        raise ValueError("No original-producer UF 2024 captures passed validation")
    return ParsedBatch(observations=observations, data_as_of=max(r["date"] for r in reports.values()),
        warnings=["Attributed UF Election Lab compilation, separate from original election-authority records.",
                  "Source dates are producer last-update dates; archive availability is separate. Missing daily reports remain missing.",
                  "Earliest positive validated snapshot per state/report date retained; later same-date corrections remain archived and listed for review.",
                  "Statewide observations only: no county or precinct pattern is implied. Zero category placeholders are withheld.",
                  "Party registration and demographic categories do not identify candidate votes; no religion or individual vote inference.",
                  *([f"{len(failures)} template, unavailable or invalid report rows/captures withheld."] if failures else [])],
        metadata={"academic_fallback": True, "reports": list(reports.values()), "failed_reports": failures,
                  "later_same_date_versions": later_versions, "states": sorted({r.state for r in observations}),
                  "source_authority": ATTRIBUTION, "parsed_report_count": len(reports), "county_coverage": "Unavailable"})
