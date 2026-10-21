"""Versioned 2020 Elections Project snapshots, an attributed research bridge.

Only published numeric JSON/HTML cells are read. R/JavaScript is never executed.
Repository commit timestamps preserve source vintage; they do not establish when
an upstream authority, or the public website, first made a quantity available.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from observatory.domain import Observation, ParsedBatch
from observatory.geography import county_match
from observatory.registry import all_states

from .common import document_text, iso_date, number, observation, soup

REPOSITORY = "ElectProject/Early-Vote-2020G"
API = f"https://api.github.com/repos/{REPOSITORY}/commits"
RAW = f"https://raw.githubusercontent.com/{REPOSITORY}"
SUPPORTED = {"NC", "GA", "MI", "FL", "IA", "OH", "TX"}
NY = ZoneInfo("America/New_York")
STATES = {row["code"]: row["name"] for row in all_states()}
PARTIES = {"Dem": "DEM", "Rep": "REP", "NPA": "UNA", "Minor": "OTHER"}
# Source-native field definitions are deliberately separate: acceptance and
# receipt are not synonyms, and an in-person absentee ballot is not mail.
FIELDS = {
    "NC": {"Voted.Tot": ("ballots_cast", "all"), "Inperson.Tot": ("ballots_cast", "early_in_person"),
           "Mail.Rtn.Tot": ("ballots_accepted", "mail"), "Mail.Reject.Tot": ("ballots_rejected", "mail"),
           "Mail.Req.Tot": ("ballots_requested", "mail")},
    "GA": {"Voted.Tot": ("ballots_cast", "all"), "Inperson.Tot": ("ballots_cast", "early_in_person"),
           "Mail.Accept.Tot": ("ballots_accepted", "mail"), "Mail.Reject.Tot": ("ballots_rejected", "mail"),
           "Mail.Req.Tot": ("ballots_requested", "mail")},
    "FL": {"Voted.Tot": ("ballots_cast", "all"), "Inperson.Tot": ("ballots_cast", "early_in_person"),
           "Mail.Return.Tot": ("ballots_returned", "mail"), "Mail.Req.Tot": ("ballots_requested", "mail")},
    "MI": {"Mail.Accept.Tot": ("ballots_accepted", "all"), "Mail.Reject.Tot": ("ballots_rejected", "all"),
           "Mail.Req.Tot": ("ballots_requested", "all")},
    "IA": {"Mail.Accept.Tot": ("ballots_accepted", "all"), "Mail.Reject.Tot": ("ballots_rejected", "all"),
           "Mail.Req.Tot": ("ballots_requested", "all")},
    "OH": {"Mail.Rtn.Tot": ("ballots_returned", "all"), "Mail.Req.Tot": ("ballots_requested", "all")},
    "TX": {},
}
# Match whole visible paragraphs, not chart labels or an unrelated earlier cycle.
HEADLINES = {
    "NC": [("Total Voted", "ballots_cast", "all"), ("In-Person Votes", "ballots_cast", "early_in_person"),
           ("Ballots Returned", "ballots_accepted", "mail"), ("Ballots Requested", "ballots_requested", "mail")],
    "GA": [("Total Voted", "ballots_cast", "all"), ("In-Person Early Votes", "ballots_cast", "early_in_person"),
           ("Mail Ballots Returned and Accepted", "ballots_accepted", "mail"), ("Ballots Requested", "ballots_requested", "mail")],
    "FL": [("Total Voted", "ballots_cast", "all"), ("In-Person Votes", "ballots_cast", "early_in_person")],
    "MI": [("Ballots Returned", "ballots_accepted", "all"), ("Ballots Requested", "ballots_requested", "all")],
    "IA": [("Mail Ballots Returned and Accepted", "ballots_accepted", "all"), ("Mail Ballots Requested", "ballots_requested", "all")],
    "OH": [("Ballots Returned", "ballots_returned", "all"), ("Ballots Requested", "ballots_requested", "all")],
    "TX": [("Total Voted", "ballots_cast", "all"), ("In-Person Votes", "ballots_cast", "early_in_person")],
}


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return number(str(value))
    except ValueError:
        return None


def _county_json(page: Any) -> list[dict]:
    """Read data-only htmlwidget payloads, deduplicating repeated thematic maps."""
    found: dict[str, dict] = {}
    for tag in page.select('script[type="application/json"]'):
        try:
            data = json.loads(tag.string or tag.get_text()).get("x", {})
        except (ValueError, TypeError):
            continue
        for series in (data.get("hc_opts") or {}).get("series", []):
            for row in series.get("data", []):
                if not isinstance(row, dict) or not re.fullmatch(r"\d{5}", str(row.get("fips", ""))):
                    continue
                identifier = str(row["fips"])
                if identifier in found:
                    # The same cells can occur in several map widgets; a conflict
                    # is an ambiguous source snapshot, never a license to choose.
                    overlap = set(found[identifier]) & set(row) - {"value", "row"}
                    if any(found[identifier][key] != row[key] for key in overlap):
                        raise ValueError(f"Conflicting embedded county values for {identifier}")
                    found[identifier].update({k: v for k, v in row.items() if k not in {"value", "row"}})
                else:
                    found[identifier] = {k: v for k, v in row.items() if k not in {"value", "row"}}
    return list(found.values())


def parse_snapshot(source: dict, doc: Any, commit: dict) -> tuple[list[Observation], dict]:
    state = source["state"]
    if state not in SUPPORTED or int(source.get("cycle", 2020)) != 2020:
        raise ValueError("The versioned Elections Project adapter supports reviewed 2020 state templates only")
    page = soup(doc)
    text = page.get_text(" ", strip=True)
    match = re.search(r"Last Report:\s*(\d{1,2}/\d{1,2}/2020)", text)
    if not match:
        raise ValueError("2020 source snapshot lacks a native Last Report date")
    date_ = iso_date(match[1])
    vintage = commit["committed_at"]
    if datetime.fromisoformat(vintage.replace("Z", "+00:00")).date().isoformat() < date_:
        raise ValueError("Source report date postdates its recorded repository vintage")
    source_line = re.search(r"Source:\s*(.*?)(?:Total Voted|Returned and Accepted|Mail Ballots Returned|These |Data presented|In-Person)", text)
    meta = {
        "parser_version": "electproject-history-1.0", "academic_fallback": True, "source_tier": 3,
        "attribution": "Michael P. McDonald, United States Elections Project / University of Florida",
        "source_repository": f"https://github.com/{REPOSITORY}", "commit_sha": commit["sha"],
        "commit_url": f"https://github.com/{REPOSITORY}/commit/{commit['sha']}",
        "source_vintage": vintage, "report_date": date_, "report_date_semantics": "producer_last_report",
        "historical_publication_verified": False,
        "reconstruction_basis": "dated report snapshots from original producer versioned repository; not individual ballot event dates",
        "availability_definition": "Repository commit is source vintage, not independently verified original web publication",
        "upstream_source": source_line[1].strip() if source_line else source.get("upstream_source"),
        "source_notes": source.get("notes"), "license": "Producer-specific permissions; retain attribution and review redistribution before public publication",
    }
    if state == "OH":
        meta.update(county_date_unverified=True, asynchronous_reporting=True,
                    mode_classification="Producer combines mail and in-person because some counties do not separate them",
                    party_classification="Not supplied: Ohio primary history is not party registration")
    if state in {"IA", "MI"}:
        meta["mode_classification"] = "Absentee includes in-person; source mail label cannot establish a disjoint mail-only count"
    if state in {"MI", "IA"}:
        meta["status_classification"] = "Producer labels returned and accepted; published status is preserved without equating it with counted votes"
    observations: list[Observation] = []
    headlines: dict[tuple[str, str], int] = {}
    for label, metric, mode in HEADLINES[state]:
        matches = []
        for paragraph in page.select("p"):
            value_match = re.fullmatch(re.escape(label) + r":\s*([\d,]+)(?:\s.*)?", paragraph.get_text(" ", strip=True))
            if value_match:
                matches.append(number(value_match[1]))
        if len(set(matches)) > 1:
            raise ValueError(f"Conflicting statewide {label} headlines")
        if matches:
            headlines[(metric, mode)] = matches[0]
    # A numeric HTML table has explicit Total cells and native headers. Only
    # reviewed party tables supply statewide values absent from a headline.
    table_rows: list[tuple[str, str, str, str, int, dict]] = []
    for table in page.select("table"):
        previous = table.find_previous(["h2", "h3", "h4"])
        title = previous.get_text(" ", strip=True) if previous else ""
        headers = [cell.get_text(" ", strip=True) for cell in table.select("thead th")]
        if "Party" not in headers or not title:
            continue
        if title.startswith("Total Voted by Party"):
            metric, mode = "ballots_cast", "all"
        elif title.startswith("In-Person Votes by Party"):
            metric, mode = "ballots_cast", "early_in_person"
        elif "Mail Ballots Returned" in title and "Outstanding" not in title:
            metric = "ballots_returned" if state == "FL" else "ballots_accepted"
            mode = "all" if state == "IA" else "mail"
        elif title.startswith("Mail Ballot Requests by Party") or title.startswith("Mail Ballots Requested by Party"):
            metric, mode = "ballots_requested", "all" if state in {"IA", "OH"} else "mail"
        else:
            continue
        rows = []
        for tr in table.select("tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.select("td")]
            if len(cells) < 2 or (count := _integer(cells[1])) is None:
                continue
            rows.append((cells[0], count))
        total = next((count for label, count in rows if label.upper() == "TOTAL"), None)
        parts = [(label, count) for label, count in rows if label.upper() != "TOTAL"]
        if total is None or sum(count for _, count in parts) != total:
            continue
        key = (metric, mode)
        if key in headlines and headlines[key] != total:
            # Some tracker panels update asynchronously. Do not silently replace
            # the headline or attach a different denominator's composition.
            continue
        headlines.setdefault(key, total)
        for label, count in parts:
            category = {"Democrats": "DEM", "Republicans": "REP", "No Party Affiliation": "UNA", "Minor": "OTHER"}.get(label, label)
            table_rows.append((metric, mode, "registration", category, count, {"native_table_title": title, "native_category": label}))
    county_rows = _county_json(page)
    coverage: dict[str, dict] = {}
    for field, (metric, mode) in FIELDS[state].items():
        valid = [row for row in county_rows if _integer(row.get(field)) is not None]
        subtotal = sum(_integer(row[field]) or 0 for row in valid)
        key = (metric, mode)
        headline = headlines.get(key)
        # Preserve source-native county values even when asynchronous. An
        # aggregate sum is labeled as a reporting-county subset, never statewide.
        matched = headline is not None and subtotal == headline
        coverage[f"{metric}:{mode}"] = {"reported_counties": len(valid), "county_sum": subtotal,
                                          "statewide_headline": headline, "reconciles": matched}
        for raw in valid:
            geoid = str(raw["fips"])
            name = raw.get("name") or raw.get("CountyName") or raw.get("County") or raw.get("COUNTY")
            if not county_match(state, geoid, str(name)):
                raise ValueError(f"Unmatched source-native county GEOID {geoid}")
            details = {**meta, "geoid": geoid, "native_geography_id": geoid, "original_column": field,
                       "original_cell": raw[field], "native_definition": field,
                       "county_state_reconciles": matched, "reporting_county_count": len(valid),
                       "county_sum": subtotal, "statewide_headline": headline}
            observations.append(observation(source, doc, name=str(name), value=_integer(raw[field]), metric=metric,
                                            mode=mode, date_=date_, kind="county", basis="reconstructed",
                                            published_at=vintage, metadata=details))
            prefix = field.removesuffix(".Tot")
            parts = [(suffix, category, _integer(raw.get(f"{prefix}.{suffix}"))) for suffix, category in PARTIES.items()]
            if all(value is not None for _, _, value in parts) and sum(value or 0 for _, _, value in parts) == raw[field]:
                for suffix, category, value in parts:
                    observations.append(observation(source, doc, name=str(name), value=value, metric=metric,
                        mode=mode, date_=date_, kind="county", dimension="registration", category=category,
                        basis="reconstructed", published_at=vintage,
                        metadata={**details, "original_column": f"{prefix}.{suffix}", "original_cell": value,
                                  "category_definition": "Published registration category; not candidate support"}))
    for (metric, mode), value in headlines.items():
        observations.append(observation(source, doc, name=STATES[state], kind="state", value=value, metric=metric,
                                        date_=date_, mode=mode, basis="reconstructed", published_at=vintage,
                                        metadata={**meta, "native_definition": "Published tracker headline/table total",
                                                  "county_coverage": coverage.get(f"{metric}:{mode}")}))
    for metric, mode, dimension, category, count, details in table_rows:
        observations.append(observation(source, doc, name=STATES[state], kind="state", value=count,
                                        metric=metric, date_=date_, mode=mode, dimension=dimension, category=category,
                                        basis="reconstructed", published_at=vintage, metadata={**meta, **details,
                                        "category_definition": "Published registration category; not candidate support"}))
    if not headlines or not observations:
        raise ValueError("No reviewed 2020 participation totals found")
    return observations, {"report_date": date_, "commit_sha": commit["sha"], "source_vintage": vintage,
                           "county_coverage": coverage, "source_url": doc.url, "source_sha256": doc.sha256}


def list_commits(source: dict, fetcher: Any) -> list[dict]:
    """Bounded, archived commit inventory; one last source version per commit day."""
    state = source["state"]
    commits = []
    for page in range(1, 4):
        url = f"{API}?path=docs/{state}.html&per_page=100&page={page}&since=2020-09-01T00:00:00Z&until=2020-11-03T23:59:59Z"
        doc = fetcher.fetch(url)
        values = json.loads(document_text(doc))
        if not isinstance(values, list):
            raise ValueError("Source commit inventory is unavailable or rate-limited")
        for row in values:
            sha = row.get("sha", "")
            committed = row.get("commit", {}).get("committer", {}).get("date", "")
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("Invalid source commit identifier")
            datetime.fromisoformat(committed.replace("Z", "+00:00"))
            commits.append({"sha": sha, "committed_at": committed, "inventory_url": url,
                            "inventory_sha256": doc.sha256})
        if len(values) < 100:
            break
    else:
        raise ValueError("Source history exceeds bounded 300-commit inventory")
    by_day = {}
    for row in sorted(commits, key=lambda item: item["committed_at"]):
        day = datetime.fromisoformat(row["committed_at"].replace("Z", "+00:00")).astimezone(NY).date().isoformat()
        by_day[day] = row
    if not by_day:
        raise ValueError("No 2020 historical snapshots found")
    return sorted(by_day.values(), key=lambda item: item["committed_at"])


def collect(source: dict, fetcher: Any) -> ParsedBatch:
    if source.get("state") not in SUPPORTED:
        raise ValueError("Unsupported 2020 tracker state template")
    commits = list_commits(source, fetcher)
    observations_by_report: dict[str, list[Observation]] = {}
    reports_by_date: dict[str, dict] = {}
    failures = []
    for commit in commits:
        url = f"{RAW}/{commit['sha']}/docs/{source['state']}.html"
        try:
            doc = fetcher.fetch(url)
            rows, manifest = parse_snapshot(source, doc, commit)
            date_ = manifest["report_date"]
            # Keep the earliest captured version for a report date. Later
            # corrections remain archived, not silently introduced into history.
            if date_ not in observations_by_report:
                observations_by_report[date_] = rows
                reports_by_date[date_] = {**manifest, "inventory_url": commit["inventory_url"],
                                           "inventory_sha256": commit["inventory_sha256"]}
        except (ValueError, KeyError) as exc:
            failures.append({"source_url": url, "reason": str(exc)[:300]})
    rows = [row for date_ in sorted(observations_by_report) for row in observations_by_report[date_]]
    if not rows:
        raise ValueError("No 2020 source snapshots passed validation")
    return ParsedBatch(observations=rows, data_as_of=max(observations_by_report), warnings=[
        "Academic research bridge to originating authorities; original tracker snapshot bytes and commit inventory are archived.",
        "Historical report-date reconstruction. Repository commit dates preserve source vintage, not independently verified authority/public-website publication times.",
        "County totals can update asynchronously. Reconciliation, source coverage, native metrics and unsupported methods remain explicit.",
        "Registration and primary participation are not candidate votes; no individual demographic or religious inference is made.",
        *([f"{len(failures)} historical snapshots failed parsing; no intermediate values were filled."] if failures else []),
    ], metadata={"source_authority": "United States Elections Project / Michael P. McDonald, University of Florida",
                 "academic_fallback": True, "historical_publication_verified": False,
                 "parsed_report_count": len(observations_by_report), "report_dates": sorted(observations_by_report),
                 "reports": [reports_by_date[date_] for date_ in sorted(reports_by_date)], "failed_reports": failures})
