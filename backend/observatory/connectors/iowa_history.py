"""Strict, retrospective parser for Iowa's concatenated dated absentee reports.

Blank cells remain missing. Receipt channel is preserved as published and is
never promoted to voting method (e.g. a mailed ballot can be delivered at a
counter). A complete 99-county total must reconcile before geography is emitted.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from observatory.domain import ParsedBatch
from observatory.geography import county_match
from observatory.registry import ELECTION_DATES

from .common import document_text, iso_date, number, observation

METRICS = ("ballots_requested", "ballots_issued", "ballots_returned")
PARTIES = {"Democrat": "DEM", "Republican": "REP", "No Party": "UNA", "Other": "OTHER", "Libertarian": "LIB"}
CHANNELS = {"Counter / In-Office", "Satellite", "Mail", "Drop Box", "Health Care Facility", "E-Mail", "Fax"}


def _page_date(text: str, cycle: int) -> str:
    tail = "\n".join(text.splitlines()[-12:])
    values = re.findall(r"\b\d{1,2}/\d{1,2}/(?:20\d\d)\b", tail)
    if not values:
        raise ValueError("Iowa historical page lacks a native report-date footer")
    date_ = iso_date(values[-1])
    if int(date_[:4]) != cycle:
        raise ValueError("Iowa historical report date conflicts with its election cycle")
    return date_


def _numeric_row(line: str, cycle: int | None = None) -> tuple[str, tuple[int, int, int]] | None:
    # The county-number column in 2016 is explicitly distinguished from the
    # three status columns. Missing numeric cells are never shifted left.
    if cycle == 2016:
        coded = re.fullmatch(r"\s*(.+?)\s+(\d{2})\s+(.*?)\s*", line)
        if coded and county_match("IA", name=coded[1]):
            cells = coded[3].split()
            if len(cells) != 3 or not all(re.fullmatch(r"\d[\d,]*", cell) for cell in cells):
                return None
            return coded[1].strip(), tuple(number(cell) for cell in cells)
    match = re.fullmatch(r"\s*(.+?)\s+(\d[\d,]*)\s+(\d[\d,]*)\s+(\d[\d,]*)\s*", line)
    if not match:
        return None
    label = match[1].strip()
    label = re.sub(r"\s+\d{2}$", "", label)
    return label, tuple(number(value) for value in match.groups()[1:])


def parse_pages(pages: list[str], source: dict, doc: Any) -> ParsedBatch:
    cycle = int(source["cycle"])
    if source.get("state") != "IA" or cycle not in {2016, 2018, 2020, 2022, 2024}:
        raise ValueError("Iowa historical templates support reviewed 2016–2024 general cycles")
    if not pages or len(pages) > 5000:
        raise ValueError("Iowa historical PDF has an unsupported page count")
    groups = []
    for index, page in enumerate(pages, start=1):
        date_ = _page_date(page, cycle)
        if not groups or groups[-1]["date"] != date_:
            groups.append({"date": date_, "pages": []})
        groups[-1]["pages"].append((index, page))
    published = source.get("archive_capture_at") or doc.retrieved_at
    contemporaneous = bool(source.get("contemporary_archive_capture"))
    basis = "reported" if contemporaneous else "reconstructed"
    observations, manifests, failed = [], [], []
    seen_dates = set()
    for group in groups:
        date_ = group["date"]
        if date_ in seen_dates:
            failed.append({"date": date_, "reason": "Repeated noncontiguous report date; later block withheld pending source review"})
            continue
        seen_dates.add(date_)
        county_totals = {}
        party_totals = defaultdict(dict)
        channels = defaultdict(lambda: defaultdict(dict))
        current_county = current_party = None
        state_total = None
        conflicts = []
        for page_number, page in group["pages"]:
            for raw in page.splitlines():
                line = re.sub(r"\s+", " ", raw).strip()
                parsed = _numeric_row(line, cycle)
                if parsed is None:
                    # 2018 county headings precede party rows and a named subtotal.
                    match = county_match("IA", name=line)
                    if match and not re.search(r"\d", line):
                        current_county = match["geoid"]
                        current_party = None
                    continue
                label, values = parsed
                if label == "Grand Total":
                    if state_total is not None and state_total != values:
                        conflicts.append("Conflicting printed Grand Total rows")
                    state_total = values
                    continue
                match = county_match("IA", name=re.sub(r"\s+Total$", "", label))
                if match:
                    current_county = match["geoid"]
                    current_party = None
                    entry = {"values": values, "name": match["name"], "page": page_number, "row": raw.strip()}
                    if current_county in county_totals and county_totals[current_county]["values"] != values:
                        conflicts.append(f"Conflicting county totals for {match['name']}")
                    county_totals[current_county] = entry
                elif label in PARTIES and current_county:
                    current_party = PARTIES[label]
                    party_totals[current_county][current_party] = {"values": values, "page": page_number, "row": raw.strip()}
                elif label in CHANNELS and current_county and current_party:
                    channels[current_county][current_party][label] = {"values": values, "page": page_number, "row": raw.strip()}
        summed = tuple(sum(row["values"][i] for row in county_totals.values()) for i in range(3))
        reconciles = len(county_totals) == 99 and not conflicts and (state_total is None or summed == state_total)
        if not reconciles:
            reason = "; ".join(conflicts) or f"Only {len(county_totals)} complete county rows or Grand Total mismatch; county observations withheld"
            failed.append({"date": date_, "reason": reason})
            if state_total is None:
                continue
        metadata = {
            "parser_version": "iowa-history-1.0", "report_date": date_,
            "report_date_semantics": "native_dated_absentee_snapshot",
            "reconstruction_basis": "dated report snapshots in the official combined historical PDF",
            "historical_publication_verified": contemporaneous, "source_vintage": published,
            "archive_capture_at": source.get("archive_capture_at"),
            "archive_original_url": source.get("original_url"), "archive_capture_digest": source.get("archive_capture_digest"),
            "availability_definition": ("Conservative availability at independently archived capture timestamp; authority publication may have been earlier" if contemporaneous else "Retrieved combined archive; printed report dates do not establish original publication of these bytes"),
            "native_definition": "Iowa absentee Requested / Issued / Received; includes in-person absentee",
            "county_state_reconciles": reconciles, "reporting_county_count": len(county_totals),
            "county_observations_withheld": not reconciles,
            "status_classification": "Received does not establish acceptance, counted votes, or candidate support",
            "mode_classification": "All absentee methods combined; receipt method is a separate channel dimension",
            "period_end": (datetime.fromisoformat(date_).date() - timedelta(days=1)).isoformat() if any(re.search(r"Data from night before", page, re.I) for _, page in group["pages"]) else None,
        }
        def emit(name, kind, values, *, details=None, dimension=None, category=None):
            for metric, value in zip(METRICS, values):
                observations.append(observation(source, doc, name=name, kind=kind, value=value, metric=metric,
                    mode="all", date_=date_, basis=basis, published_at=published,
                    dimension=dimension, category=category, metadata={**metadata, **(details or {})}))
        emit("Iowa", "state", state_total or summed,
             details={"aggregation": ("Printed Grand Total reconciled across 99 counties" if reconciles else "Printed Grand Total; county details withheld") if state_total else "Exact sum of 99 published county totals"})
        statewide_party = defaultdict(lambda: [0, 0, 0])
        complete_party_counties = 0
        for geoid, county in (county_totals if reconciles else {}).items():
            details = {"geoid": geoid, "native_geography_id": geoid, "page": county["page"], "original_row": county["row"]}
            emit(county["name"], "county", county["values"], details=details)
            parts = party_totals.get(geoid, {})
            if tuple(sum(row["values"][i] for row in parts.values()) for i in range(3)) != county["values"]:
                continue
            complete_party_counties += 1
            for category, row in parts.items():
                emit(county["name"], "county", row["values"], dimension="registration", category=category,
                     details={**details, "page": row["page"], "original_row": row["row"],
                              "category_definition": "Published registration category; not candidate support"})
                for index, value in enumerate(row["values"]):
                    statewide_party[category][index] += value
                channel_rows = channels[geoid][category]
                # Receipt channel's received counts must form a coherent complete
                # partition. It is intentionally not a candidate voting-mode split.
                if channel_rows and sum(r["values"][2] for r in channel_rows.values()) == row["values"][2]:
                    for channel, channel_row in channel_rows.items():
                        observations.append(observation(source, doc, name=county["name"], kind="county",
                            value=channel_row["values"][2], metric="ballots_returned", date_=date_, mode="all",
                            basis=basis, published_at=published, dimension="registration_receipt_channel", category=f"{category} | {channel}",
                            metadata={**metadata, **details, "page": channel_row["page"], "original_row": channel_row["row"],
                                      "registration_category": category,
                                      "joint_category_note": "Native source table is joint registration and receipt channel; not independently additive across registration rows"}))
        if complete_party_counties == 99:
            for category, values in statewide_party.items():
                emit("Iowa", "state", values, dimension="registration", category=category,
                     details={"aggregation": "Exact sum of 99 reconciled county registration partitions"})
        manifests.append({"date": date_, "page_start": group["pages"][0][0], "page_end": group["pages"][-1][0],
                          "county_count": len(county_totals) if reconciles else 0, "requested": (state_total or summed)[0], "issued": (state_total or summed)[1], "received": (state_total or summed)[2],
                          "county_state_reconciles": reconciles,
                          "complete_registration_counties": complete_party_counties,
                          "printed_grand_total": state_total is not None})
    if not observations:
        raise ValueError("No dated Iowa report blocks passed 99-county and status-total reconciliation")
    return ParsedBatch(observations=observations, data_as_of=max(row.date for row in observations), warnings=[
        ("Contemporaneously archived original snapshot; availability begins at its independently verified archive capture, not the printed report date." if contemporaneous else "Retrospective official dated-report reconstruction; original contemporary publication timestamps are not established by this combined PDF."),
        "Absentee includes in-person participation. Published receipt channels do not by themselves identify voting method.",
        "Blank PDF cells remain missing, not zero. Dates lacking a complete reconciled county block are withheld.",
        *([f"{len(failed)} report block(s) were withheld; see failed_reports."] if failed else []),
    ], metadata={"reports": manifests, "failed_reports": failed, "parsed_report_count": len(manifests),
                 "source_authority": "Iowa Secretary of State", "historical_publication_verified": contemporaneous})


def collect(source: dict, fetcher: Any) -> ParsedBatch:
    if not source.get("archive_captures"):
        doc = fetcher.fetch(source["url"])
        reader = PdfReader(doc.path)
        return parse_pages([page.extract_text(extraction_mode="layout") or "" for page in reader.pages], source, doc)
    inventory = fetcher.fetch(source["url"])
    raw = json.loads(document_text(inventory))
    if not isinstance(raw, list) or not raw or "timestamp" not in raw[0]:
        raise ValueError("Archived Iowa capture inventory is unavailable")
    headers = raw[0]
    captures = [dict(zip(headers, row)) for row in raw[1:]]
    originals = source["original_url"]
    observations, manifests, failures = {}, [], []
    for requested in source["archive_captures"]:
        timestamp = requested["timestamp"]
        entry = next((row for row in captures if row["timestamp"] == timestamp and row["digest"] == requested["digest"]
                      and row["original"].lower() == originals.lower() and row.get("statuscode") == "200"
                      and row.get("mimetype") == "application/pdf"), None)
        if entry is None:
            raise ValueError("Configured Iowa PDF capture is not established by the archived CDX inventory")
        captured_at = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("UTC")).isoformat()
        url = f"https://web.archive.org/web/{timestamp}id_/{entry['original']}"
        try:
            doc = fetcher.fetch(url)
            digest = base64.b32encode(hashlib.sha1(Path(doc.path).read_bytes()).digest()).decode().rstrip("=")
            if digest != entry["digest"]:
                raise ValueError("Archived Iowa PDF bytes do not match the independently recorded capture digest")
            reader = PdfReader(doc.path)
            if len(reader.pages) > 5000:
                raise ValueError("Archived Iowa PDF exceeds the reviewed page limit")
            local_capture_day = datetime.fromisoformat(captured_at).astimezone(ZoneInfo("America/Chicago")).date().isoformat()
            historical = {**source, "archive_capture_at": captured_at, "archive_capture_digest": digest,
                          "contemporary_archive_capture": local_capture_day <= ELECTION_DATES[int(source["cycle"])]}
            batch = parse_pages([page.extract_text(extraction_mode="layout") or "" for page in reader.pages], historical, doc)
            for row in batch.observations:
                if row.date > local_capture_day:
                    raise ValueError("Native Iowa report date postdates its independently verified archive capture")
                row.metadata.update(archive_inventory_url=inventory.url, archive_inventory_sha256=inventory.sha256)
                key = (row.date, row.time_basis, row.metric, row.mode, row.geography_id, row.category_dimension, row.category)
                # Earliest evidence vintage wins; later combined archives cannot
                # revise a historically captured snapshot in place.
                if key not in observations or row.published_at < observations[key].published_at:
                    observations[key] = row
            manifests.append({"timestamp": timestamp, "captured_at": captured_at, "source_url": url,
                              "source_sha256": doc.sha256, "capture_digest_verified": True,
                              "contemporaneous": historical["contemporary_archive_capture"],
                              "report_count": batch.metadata["parsed_report_count"], "reports": batch.metadata["reports"],
                              "failed_reports": batch.metadata["failed_reports"]})
        except (OSError, ValueError, httpx.HTTPError, PdfReadError) as exc:
            failures.append({"timestamp": timestamp, "source_url": url, "reason": str(exc)[:400]})
    if not observations:
        raise ValueError("No archived Iowa reports passed capture-digest, date and count validation")
    return ParsedBatch(observations=list(observations.values()), data_as_of=max(row.date for row in observations.values()),
        warnings=["Original authority PDFs retrieved through a public historical archive; each payload must match its archived capture SHA1 digest.",
                  "Reported availability begins at a contemporaneous archive capture. Later combined reports are separately labeled reconstructed.",
                  "Blank numeric cells remain missing; county panels require complete 99-county reconciliation. Valid printed statewide totals are retained separately.",
                  "Receipt channel is not voting method. Absentee received does not establish acceptance or candidate support.",
                  *([f"{len(failures)} capture(s) failed validation or retrieval; no data substituted."] if failures else [])],
        metadata={"source_authority": "Iowa Secretary of State", "archive_inventory_url": inventory.url,
                  "archive_inventory_sha256": inventory.sha256, "captures": manifests, "failed_captures": failures,
                  "report_dates": sorted({row.date for row in observations.values()}),
                  "parsed_report_count": len({row.date for row in observations.values()})})
