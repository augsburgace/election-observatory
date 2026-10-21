"""Dated NCSBE reports, with S3 object chronology and separately labeled reconstruction.

The official data page links the public bucket folders. A filename/report date
does not prove that the current PDF bytes were public then: historical PDFs
have sometimes been replaced later. LastModified is therefore the conservative
availability timestamp for reported replay; reconstructed report snapshots keep
the original report date and explicitly retain their later source vintage.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zoneinfo import ZoneInfo

import httpx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from observatory.domain import Observation, ParsedBatch

from .common import document_text, iso_date, number, observation

BUCKET = "https://s3.amazonaws.com/dl.ncsbe.gov/"
PREFIXES = {
    2026: "Press/2026 General/NC Absentee Stats for 2026 General/",
    2024: "Press/2024 General/NC Absentee Stats for 2024 General/",
    2022: "Press/2022 General/NC Absentee Stats for 2022 General/",
    2020: "Press/2020 General/NC Absentee Stats for 2020 General Election/",
    2018: "Press/2018 General/",
}
PARTIES = {"Democratic": "DEM", "Republican": "REP", "Unaffiliated": "UNA", "Libertarian": "LIB",
           "Green": "GRE", "Constitution": "CST", "No Labels": "NLB", "We The People": "WTP",
           "Justice For All": "JFA"}
ETHNICITIES = {"Hispanic or Latino": "HISPANIC or LATINO", "Not Hispanic or Not Latino": "NOT HISPANIC or NOT LATINO",
               "Undesignated": "UNDESIGNATED"}
DIMENSIONS = {"Party": "registration", "Race": "race_report", "Ethnicity": "ethnicity", "Gender": "gender"}
NY = ZoneInfo("America/New_York")


def _local_date(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp)
    return parsed.astimezone(NY).date().isoformat()


def _child(element: ET.Element, name: str) -> str | None:
    return next((item.text for item in element if item.tag.rsplit("}", 1)[-1] == name), None)


def report_date_from_key(key: str, cycle: int) -> str | None:
    filename = PurePosixPath(key).name
    match = re.search(r"(20\d\d-\d\d-\d\d)", filename)
    if match:
        result = match[1]
    elif match := re.search(r"_(\d{2})(\d{2})(20\d\d)\.pdf$", filename, re.I):
        result = f"{match[3]}-{match[1]}-{match[2]}"
    elif match := re.search(r"_(October|November|September)_(\d{1,2})_(20\d\d)\.pdf$", filename, re.I):
        result = datetime.strptime(f"{match[1]} {match[2]}, {match[3]}", "%B %d, %Y").date().isoformat()
    else:
        return None
    if int(result[:4]) != cycle:
        return None
    # Invalid dates must not become observation keys.
    datetime.fromisoformat(result)
    return result


def list_reports(source: dict[str, Any], fetcher: Any) -> list[dict[str, Any]]:
    """Archive the public bucket listing, including each object's LastModified."""
    cycle = int(source.get("cycle", 2026))
    if cycle not in PREFIXES:
        raise ValueError("NC dated reports support 2018, 2020, 2022, 2024, and 2026")
    query = parse_qs(urlparse(source["url"]).query)
    prefix = source.get("prefix") or query.get("prefix", [PREFIXES[cycle]])[0]
    if not str(prefix).startswith(f"Press/{cycle} General/"):
        raise ValueError("Only the official NCSBE general-election report prefix is supported")
    marker = None
    result = []
    for _page in range(10):
        parameters = {"prefix": prefix}
        if marker:
            parameters["marker"] = marker
        listing_url = BUCKET + "?" + urlencode(parameters)
        document = fetcher.fetch(listing_url)
        root = ET.fromstring(document_text(document))
        if root.tag.rsplit("}", 1)[-1] != "ListBucketResult":
            raise ValueError("NCSBE archive returned no valid public bucket listing")
        entries = [item for item in root if item.tag.rsplit("}", 1)[-1] == "Contents"]
        for entry in entries:
            key = _child(entry, "Key") or ""
            if not key.startswith(str(prefix)) or not key.lower().endswith(".pdf"):
                continue
            # 2018's broader folder can contain unrelated press documents.
            if "absentee" not in key.lower() or "request" in key.lower():
                continue
            report_date = report_date_from_key(key, cycle)
            if report_date is None:
                continue
            modified = _child(entry, "LastModified")
            if not modified:
                raise ValueError("NC report archive omitted object chronology")
            datetime.fromisoformat(modified)
            result.append({"key": key, "date": report_date, "last_modified": modified,
                           "url": BUCKET + quote(key, safe="/"), "listing_url": listing_url,
                           "listing_sha256": document.sha256})
        if (_child(root, "IsTruncated") or "false").lower() != "true":
            break
        marker = _child(root, "NextMarker") or (_child(entries[-1], "Key") if entries else None)
        if marker is None:
            raise ValueError("NC report listing pagination is incomplete")
    else:
        raise ValueError("NC report archive exceeded the bounded listing limit")
    if not result:
        raise ValueError("No dated absentee reports were found in the official NC archive")
    limit = int(source.get("max_reports", 366))
    if not 1 <= limit <= 366:
        raise ValueError("max_reports must be between 1 and 366")
    return sorted(result, key=lambda item: (item["date"], item["last_modified"]))[-limit:]


def _field(text: str, expression: str, label: str) -> int:
    match = re.search(expression, text, re.I)
    if not match:
        raise ValueError(f"NC report schema changed: missing {label}")
    return number(match[1])


def _document_dates(text: str, expected: str) -> tuple[str, str | None]:
    published = re.search(r"Published\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    period = re.search(r"Ballots\s+cast\s+through\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    if published:
        printed_date = iso_date(published[1])
        if printed_date != expected:
            raise ValueError("NC report filename and printed publication dates conflict")
    else:
        # Older templates call this an update date, not a publication assertion.
        updated = next((line for line in text.splitlines() if "updated" in line.lower()), "")
        numeric = re.search(r"\d{1,2}/\d{1,2}/\d{4}", updated)
        spelled = re.search(r"(?:Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?)\.?\s+\d{1,2},?\s+20\d\d", updated, re.I)
        if numeric:
            printed_date = iso_date(numeric[0])
        elif spelled:
            value = spelled[0].replace(".", "")
            value = re.sub(r"(\d),?\s+(20\d\d)", r"\1, \2", value)
            printed_date = iso_date(value)
        else:
            raise ValueError("NC report lacks a recognizable printed report/update date")
        if printed_date != expected:
            raise ValueError("NC report filename and printed update dates conflict")
    period_end = iso_date(period[1]) if period else None
    if period_end and period_end > expected:
        raise ValueError("NC report contains future ballot-period dates")
    return printed_date, period_end


def _category(section: str, label: str) -> str:
    if section == "Party":
        return PARTIES.get(label, label)
    if section == "Gender":
        return label.upper()
    if section == "Ethnicity":
        return ETHNICITIES.get(label, label)
    # PDF race categories are coarser than the downloadable joint CSV.
    return label


def _demographics(text: str, total: int, electorate: int) -> tuple[list[dict[str, Any]], list[str]]:
    sections = list(re.finditer(r"Registration\s+Statistics\s+by\s+(Party|Race|Ethnicity|Gender)", text, re.I))
    rows, warnings = [], []
    pattern = re.compile(r"^(.+?)\s+(\d[\d,]*)\s+[\d.]+%\s+(?:Turnout\s+)?(.+?)\s+(\d[\d,]*)\s+[\d.]+%\s+[\d.]+%\s*$")
    for index, header in enumerate(sections):
        section = header[1].title()
        body = text[header.end():sections[index + 1].start() if index + 1 < len(sections) else len(text)]
        category_rows = []
        for line in body.splitlines():
            match = pattern.match(line.strip())
            if match and match[1].strip().casefold() == match[3].strip().casefold():
                category_rows.append({"dimension": DIMENSIONS[section], "category": _category(section, match[1].strip()),
                                      "native_category": match[1].strip(), "denominator": number(match[2]),
                                      "value": number(match[4]), "original_row": line.strip()})
        if (category_rows and sum(row["value"] for row in category_rows) == total
                and sum(row["denominator"] for row in category_rows) == electorate):
            rows.extend(category_rows)
        else:
            warnings.append(f"{section} categories did not reconcile with statewide totals and were withheld.")
    return rows, warnings


def _counties(pages: list[str], total: int, early_total: int, cycle: int) -> tuple[list[dict[str, Any]], list[str]]:
    text = "\n".join(pages)
    marker = re.search(r"Ballots\s+Cast\s+by\s+County", text, re.I)
    values = []
    if marker:
        pattern = re.compile(r"^([A-Z][A-Z .'-]*?)\s+(\d[\d,]*(?:\s+\d[\d,]*){0,4})\s*$")
        # Positioned PDF headers can extract after the county cells on a page.
        # Parse all county pages, then require the complete reconciled 100 rows.
        for line in text.splitlines():
            match = pattern.match(line.strip())
            if not match or match[1].strip() in {"TOTAL", "STATEWIDE", "NORTH CAROLINA"}:
                continue
            name = match[1].strip()
            counts = [number(item) for item in match[2].split()]
            if len(counts) == 1:
                values.append({"name": name, "all": counts[0]})
            elif len(counts) == 5 and sum(counts[:4]) == counts[4]:
                values.append({"name": name, "all": counts[4], "early_in_person": counts[0],
                               "mail": sum(counts[1:4]), "civilian_mail": counts[1],
                               "military_mail": counts[2], "overseas_mail": counts[3]})
            elif len(counts) == 5:
                return [], ["County voting-method totals failed reconciliation; county observations withheld."]
        if len(values) == 100 and len({row["name"] for row in values}) == 100 and sum(row["all"] for row in values) == total:
            if all("early_in_person" in row for row in values) and sum(row["early_in_person"] for row in values) != early_total:
                return [], ["County early-voting totals differ from the statewide report; county observations withheld."]
            return values, []
        return [], ["A complete set of 100 county rows did not reconcile; statewide evidence retained, county values withheld."]
    if cycle == 2018:
        sites: dict[str, int] = defaultdict(int)
        pattern = re.compile(r"^\d{2}/\d{2}/2018\s+([A-Z][A-Z ]+?)\s+[A-Z0-9-]+\s+ONE-STOP\s+ACCEPTED\s+([\d,]+)\s*$")
        for line in text.splitlines():
            if match := pattern.match(line.strip()):
                sites[match[1].strip()] += number(match[2])
        if len(sites) == 100 and sum(sites.values()) == early_total:
            return [{"name": name, "early_in_person": value} for name, value in sites.items()], [
                "2018 county values are accepted one-stop ballots summed from published site counts; no county total across all voting methods is inferred."]
    return [], ["No validated county breakdown was found for this report template."]


def parse_report(source: dict[str, Any], document: Any, entry: dict[str, Any]) -> tuple[list[Observation], list[str]]:
    reader = PdfReader(document.path)
    if not 1 <= len(reader.pages) <= 30:
        raise ValueError("NC report page count exceeds the supported bounded template")
    pages = [page.extract_text() or "" for page in reader.pages]
    first = pages[0]
    cycle = int(source.get("cycle", 2026))
    report_date, period_end = _document_dates(first, entry["date"])
    total = _field(first, r"Total\s+(?:Absentee\s+)?Ballots\s+Cast\s+([\d,]+)", "statewide total")
    early = _field(first, r"(?:In-Person\s+Early\s+Voting|One[- ]Stop\s+early\s+voting)\s+([\d,]+)", "early voting")
    civilian = _field(first, r"Civilian(?:\s+\(Mail\))?\s+([\d,]+)", "civilian mail")
    military = _field(first, r"Military(?:\s+\(Mail\))?\s+([\d,]+)", "military mail")
    overseas = _field(first, r"Overseas\s*(?:\(Mail\))?\s+([\d,]+)", "overseas mail")
    if early + civilian + military + overseas != total:
        raise ValueError("NC statewide voting methods do not sum to its reported total")
    registered_match = re.search(r"Total\s+Registered\s+Voters\s+([\d,]+)", first, re.I)
    electorate = number(registered_match[1]) if registered_match else _field(
        first, r"Total\s+Eligible\s+Voters\*?\s+([\d,]+)", "dated voter denominator")
    denominator_definition = "Total Registered Voters" if registered_match else "Total Eligible Voters (source label)"
    demographic_rows, warnings = _demographics(first, total, electorate)
    county_rows, county_warnings = _counties(pages[1:], total, early, cycle)
    warnings.extend(county_warnings)
    modified_date = _local_date(entry["last_modified"])
    delayed = modified_date != report_date
    metadata = {
        "parser_version": "nc_reports-1.0", "native_definition": "Total absentee and in-person early ballots cast (NCSBE daily report)",
        "report_date": report_date, "period_end": period_end, "printed_report_or_update_date": report_date,
        "object_last_modified": entry["last_modified"], "archive_listing_url": entry["listing_url"],
        "archive_listing_sha256": entry["listing_sha256"], "archive_key": entry["key"],
        "availability_definition": "Conservative current-object availability: public archive LastModified, not backdated to filename",
        "object_modified_after_report_date": delayed,
        "denominator_date": report_date, "denominator_definition": denominator_definition,
        "denominator_active_all_status": "Not distinguished by this report",
        "source_url": document.url, "source_sha256": document.sha256,
    }
    if delayed:
        warnings.append("Some archive objects were modified after their printed report dates. Reported replay uses the later object timestamp; reconstructed report-date views expose the later vintage.")
    bases = ["reported", "reconstructed"] if source.get("include_reconstructed", True) else ["reported"]
    observations = []
    for basis in bases:
        meta = {**metadata, "reconstruction_basis": "dated report snapshots, not individual ballot event dates"} if basis == "reconstructed" else metadata

        def make(name: str, value: int, mode: str = "all", kind: str = "state", metric: str = "ballots_cast",
                 dimension: str | None = None, category: str | None = None, denominator: int | None = None,
                 details: dict[str, Any] | None = None) -> Observation:
            row = observation(source, document, name=name, value=value, kind=kind, metric=metric, date_=report_date,
                              mode=mode, basis=basis, dimension=dimension, category=category,
                              published_at=entry["last_modified"], metadata={**meta, **(details or {})})
            row.denominator = denominator
            if metric == "registered_voters":
                row.unit = "voters"
            return row

        modes = {"all": total, "early_in_person": early, "mail": civilian + military + overseas,
                 "civilian_mail": civilian, "military_mail": military, "overseas_mail": overseas}
        for mode, value in modes.items():
            observations.append(make("North Carolina", value, mode=mode, denominator=electorate))
        observations.append(make("North Carolina", electorate, metric="registered_voters",
                                 details={"native_definition": denominator_definition}))
        for row in demographic_rows:
            details = {"native_category": row["native_category"], "original_row": row["original_row"],
                       "category_definition": "Published marginal report category; intersections are unavailable",
                       "page": 1}
            observations.append(make("North Carolina", row["value"], dimension=row["dimension"], category=row["category"],
                                     denominator=row["denominator"], details=details))
            observations.append(make("North Carolina", row["denominator"], metric="registered_voters",
                                     dimension=row["dimension"], category=row["category"],
                                     details={**details, "native_definition": "Published registered-voter count for this demographic"}))
        for row in county_rows:
            for mode, value in row.items():
                if mode == "name":
                    continue
                observations.append(make(row["name"].title(), value, mode=mode, kind="county",
                                         details={"denominator_date": None, "denominator_definition": None,
                                                  "county_derivation": "Published county table" if cycle != 2018 else "Sum of published accepted one-stop site counts"}))
    return observations, warnings


def collect(source: dict[str, Any], fetcher: Any) -> ParsedBatch:
    if source.get("state") != "NC":
        raise ValueError("The NCSBE daily-report connector only supports North Carolina")
    entries = list_reports(source, fetcher)
    observations, warnings, failed = [], [], []
    for entry in entries:
        try:
            document = fetcher.fetch(entry["url"])
            rows, notices = parse_report(source, document, entry)
            observations.extend(rows)
            warnings.extend(notices)
        except (OSError, ValueError, KeyError, httpx.HTTPError, PdfReadError) as exc:
            failed.append({"date": entry["date"], "url": entry["url"], "reason": str(exc)[:500]})
    if not observations:
        raise ValueError("No NC dated reports passed schema, chronology, and total validation")
    warnings.extend([
        "Official dated reports are snapshots. Snapshot differences are newly reported activity, not necessarily ballots cast that day.",
        "Reconstructed mode uses archived report dates, not individual ballot event dates; later object modifications remain documented.",
        "PDF race groups are coarser than the downloadable CSV and use a separate race_report dimension.",
        "Registration denominators are from the same report and demographic grain; no county denominators are inferred.",
    ])
    if failed:
        warnings.append(f"{len(failed)} report(s) failed validation or retrieval; their dates are missing, not zero.")
    valid_dates = sorted({row.date for row in observations})
    period_dates = [row.metadata.get("period_end") or row.date for row in observations]
    return ParsedBatch(observations=observations, data_as_of=max(period_dates), warnings=sorted(set(warnings)),
                       metadata={"parsed_report_count": len(valid_dates), "available_report_count": len(entries),
                                 "report_dates": valid_dates, "failed_reports": failed,
                                 "primary_document_url": entries[-1]["url"],
                                 "source_authority": "North Carolina State Board of Elections",
                                 "reconstruction_basis": "dated report snapshots, not individual ballot event dates"})
