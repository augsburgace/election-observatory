"""SC official CSV and archived Excel daily participation, preserving chronology."""
import csv
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin

from observatory.domain import ParsedBatch

from .common import excel_date, iso_date, number, observation, soup, xlsx_rows


def parse_early_rows(rows: list[list[str]], source: dict, doc, *, historical: bool = False, member: str | None = None):
    cycle = source.get("cycle", 2026)
    header_idx = next((i for i, r in enumerate(rows) if r and r[0].strip() in {"County", "Jurisdiction"}), None)
    if header_idx is None:
        raise ValueError("SC early-vote report lacks County/Jurisdiction header")
    header = rows[header_idx]
    date_cols = []
    for i, val in enumerate(header):
        try:
            d = excel_date(val.strip())
            if d.startswith(str(cycle)):
                date_cols.append((i, d))
        except (ValueError, OverflowError):
            pass
    if not date_cols:
        raise ValueError("SC daily columns are unavailable")
    report_date = max(d for _, d in date_cols)
    for r in rows[:header_idx]:
        if len(r) > 1 and re.match(r"\s*\d{1,2}/\d{1,2}/\d{4}", r[1]):
            report_date = iso_date(r[1].strip().split()[0])
    is_old = header[0].strip() == "County"
    obs = []
    statewide_daily = defaultdict(int)
    has_state = False
    for row in rows[header_idx + 1:]:
        row = row + [""] * max(0, len(header) - len(row))
        label = re.sub(r"\s+", " ", row[0].strip())
        if not label:
            continue
        state_row = label.lower() in {"south carolina", "grand total", "state total", "statewide total"}
        if is_old and not (label.endswith(" Total") or state_row):
            continue
        if not is_old and not (state_row or (len(row) > 1 and "General Election" in row[1])):
            continue
        name = "South Carolina" if state_row else re.sub(r"\s+Total$", "", label).strip()
        running = 0
        for col, d in date_cols:
            if not row[col].strip():
                continue
            val = number(row[col])
            running += val
            if not state_row:
                statewide_daily[d] += val
            obs.append(observation(source, doc, name=name, kind="state" if state_row else "county", value=running,
                                   metric="ballots_cast", date_=d, mode="early_in_person", basis="reconstructed",
                                   metadata={"archive_member": member, "original_column": header[col], "daily_cell": val,
                                             "native_definition": "Early voting turnout", "report_date": report_date}))
        total_col = next((i for i, cell in enumerate(header) if "Total" in cell and ("Voters" in cell or "Early" in cell)), None)
        if total_col is not None and row[total_col].strip() and number(row[total_col]) != running:
            raise ValueError(f"SC {name} daily cells do not reconcile to the published total")
        # Current aggregate snapshot uses its report date; daily event columns
        # remain a separate reconstructed view.
        if not historical:
            obs.append(observation(source, doc, name=name, kind="state" if state_row else "county", value=running,
                                   metric="ballots_cast", date_=report_date, mode="early_in_person",
                                   metadata={"report_date": report_date, "native_definition": "Early voting turnout", "original_column": "Total Voters"}))
        has_state |= state_row
    if not has_state:
        running = 0
        for d, val in sorted(statewide_daily.items()):
            running += val
            obs.append(observation(source, doc, name="South Carolina", kind="state", value=running,
                                   metric="ballots_cast", date_=d, mode="early_in_person", basis="reconstructed",
                                   metadata={"archive_member": member, "aggregation": "Sum of county total rows", "daily_cell": val}))
    return obs, report_date


def collect(source: dict, fetcher) -> ParsedBatch:
    doc = fetcher.fetch(source["url"])
    obs, dates = [], []
    if source.get("historical"):
        with zipfile.ZipFile(doc.path) as archive:
            members = [m for m in archive.namelist() if ("EV Stats (2022 GE" in m or "2024-GE-Early" in m)]
            if not members:
                raise ValueError("SC archive general-election early-voting workbook not found")
            for m in members:
                parsed, date_ = parse_early_rows(xlsx_rows(archive.read(m)), source, doc, historical=True, member=m)
                obs.extend(parsed)
                dates.append(date_)
    else:
        links = [(a.get_text(" ", strip=True), urljoin(doc.url, a["href"])) for a in soup(doc).select("a[href]")]
        ev = next((url for label, url in links if "Early Voting Turnout Report" in label and url.endswith(".csv")), None)
        if ev is None:
            raise ValueError("SC current general-election early-voting CSV missing")
        data = fetcher.fetch(ev)
        with Path(data.path).open(encoding="utf-8-sig", newline="") as f:
            parsed, d = parse_early_rows(list(csv.reader(f)), source, data)
        obs.extend(parsed)
        dates.append(d)
    return ParsedBatch(observations=obs, data_as_of=max(dates), warnings=[
        "Early-in-person only; absentee-by-mail statistics are separate and not combined into this measure.",
        "Daily columns are event-date reconstruction from the retrieved report, not proof of what was published on each historical day.",
    ])
