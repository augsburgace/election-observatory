"""Local aggregation of Maine public absentee records, with conservative semantics.

The published DUP/reissue layout is currently inaccessible. Record counts are
therefore deliberately not labeled unique voters, valid ballots, or turnout.
No voter identifiers, addresses, or individual records enter the analytical API.
"""
import re
from collections import defaultdict
from urllib.parse import unquote, urljoin

from observatory.domain import ParsedBatch

from .common import iso_date, observation, read_csv, soup


def collect(source: dict, fetcher) -> ParsedBatch:
    index = fetcher.fetch(source["url"])
    link = next((a for a in soup(index).select("a[href]")
                 if "Statewide Absentee Voter Data File (Text)" in a.get_text(" ", strip=True)
                 and "26" in a["href"]), None)
    if link is None:
        raise ValueError("Maine current 2026 absentee file link unavailable")
    url = urljoin(index.url, link["href"])
    date_match = re.search(r"as of (\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", unquote(url), re.I)
    if not date_match:
        raise ValueError("Maine file has no explicit as-of date in its published filename")
    date_ = iso_date(date_match[1].replace("-", "/"))
    doc = fetcher.fetch(url)
    totals, timeline = defaultdict(int), defaultdict(int)
    rows, malformed, reissued, rejected = 0, 0, 0, 0
    anomalous_dates, standing_request_dates = 0, 0
    for raw in read_csv(doc, "|"):
        row = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in raw.items() if k is not None}
        if not {"RES MUNICIPALITY", "Req Date", "Issued Date", "Rec Date", "P", "DUP", "Status"}.issubset(row):
            raise ValueError("Maine absentee column schema changed")
        if any(row.get(k) is None for k in ("Req Date", "Issued Date", "Rec Date", "DUP", "Status")):
            malformed += 1
            continue
        rows += 1
        reissued += bool(row["DUP"])
        rejected += row["Status"] == "REJ"
        for field, metric in (("Req Date", "ballot_records_requested"), ("Issued Date", "ballot_records_issued"),
                              ("Rec Date", "ballot_records_returned")):
            if not row[field]:
                continue
            municipality = row["RES MUNICIPALITY"].title()
            for name in ("Maine", municipality):
                totals[(name, metric, None, None)] += 1
                totals[(name, metric, "registration_code", row["P"] or "Unknown")] += 1
            # Req Date may represent a standing request from an earlier cycle.
            # Counting records with that field is supported; assigning those
            # records to a current-cycle event chronology is not established.
            try:
                event_date = iso_date(row[field])
            except ValueError:
                anomalous_dates += 1
                continue
            if metric == "ballot_records_requested":
                standing_request_dates += event_date[:4] != str(source.get("cycle", 2026))
                anomalous_dates += event_date > date_
                continue
            if event_date > date_ or event_date[:4] != str(source.get("cycle", 2026)):
                anomalous_dates += 1
                continue
            # Only validated current-cycle issued/returned dates reconstruct a timeline.
            timeline[(metric, event_date)] += 1
    metadata = {"native_definition": "Number of published absentee records containing the relevant date field",
                "record_count_only": True, "includes_duplicate_reissued_records": True,
                "includes_rejected_records": True, "not_valid_ballots_or_unique_voters": True,
                "input_records": rows, "duplicate_flag_records": reissued, "rejected_status_records": rejected,
                "malformed_rows_excluded": malformed, "anomalous_date_fields_excluded_from_timeline": anomalous_dates,
                "standing_request_dates": standing_request_dates, "request_chronology_withheld": True,
                "parser_version": "2.0-quality-chronology"}
    obs = []
    for (name, metric, dim, category), value in totals.items():
        item = observation(source, doc, name=name, kind="state" if name == "Maine" else "municipality",
                           metric=metric, value=value, date_=date_, dimension=dim, category=category,
                           metadata=metadata)
        item.unit = "records"
        obs.append(item)
    for metric in {key[0] for key in timeline}:
        running = 0
        for (m, d), value in sorted(timeline.items()):
            if m != metric:
                continue
            running += value
            item = observation(source, doc, name="Maine", kind="state", metric=metric, value=running,
                               date_=d, basis="reconstructed", metadata=metadata)
            item.unit = "records"
            obs.append(item)
    if not obs:
        raise ValueError("Maine public file contained no usable dated records")
    return ParsedBatch(observations=obs, data_as_of=date_, warnings=[
        "Record counts include duplicate/reissued and rejected records. They are not valid ballots, unique voters, or turnout.",
        "Official code layout could not be retrieved; status and registration codes are not expanded through inference.",
        "Issued/returned event-date history is reconstructed from the current file, not historical as-reported snapshots.",
        "Request-date history is withheld: standing requests cannot establish current-election voting events.",
        f"{anomalous_dates} malformed, future, or outside-cycle date fields were excluded from event timelines; presence counts remain record counts.",
        f"{malformed} incomplete source rows excluded. Raw personal records remain only in the private local source archive.",
    ])
