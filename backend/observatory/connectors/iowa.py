"""Iowa PDF adapter for source-dated general-election county reports."""
import re

from pypdf import PdfReader

from observatory.domain import ParsedBatch

from .common import iso_date, number, observation


def parse_pages(pages: list[str], source: dict, doc) -> ParsedBatch:
    obs, dates = [], []
    parties = ["Republican", "Democrat", "No Party", "Other"]
    for i, text in enumerate(pages):
        # New 2026 layout explicitly identifies every geography and reporting date.
        date_match = re.search(r"Data as of .*? on ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
        name_match = re.search(r"County\s*\|\s*Page\s+\d+\s+([^\n]+)\s+2026 General Election", text)
        if not date_match or not name_match:
            continue
        d = iso_date(date_match[1])
        name = name_match[1].strip()
        state = name == "Iowa Statewide"
        name = "Iowa" if state else name
        dates.append(d)
        for label, metric in (("Requested", "ballots_requested"), ("Issued", "ballots_issued"), ("Received", "ballots_returned")):
            match = re.search(fr"(?m)^\s*{label}\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", text)
            if not match:
                raise ValueError(f"Iowa {name} page {i + 1} missing {label} party totals")
            values = [number(v) for v in match.groups()]
            if sum(values[:4]) != values[4]:
                raise ValueError(f"Iowa {name} {label} does not reconcile")
            kw = dict(name=name, kind="state" if state else "county", metric=metric, date_=d,
                      metadata={"page": i + 1, "original_row": match[0].strip(), "native_definition": f"Absentee {label}"})
            obs.append(observation(source, doc, value=values[4], **kw))
            for p, value in zip(parties, values):
                obs.append(observation(source, doc, value=value, dimension="registration", category=p, **kw))
    if not obs:
        raise ValueError("Iowa PDF layout not supported or missing source-dated general-election observations; no fabricated fallback")
    return ParsedBatch(observations=obs, data_as_of=max(dates), warnings=[
        "Iowa received ballots include absentee-by-mail and in-person absentee; received does not establish acceptance.",
        "Historical legacy PDF layout requires a separately validated parser and is not silently inferred from the new layout.",
    ])


def collect(source: dict, fetcher) -> ParsedBatch:
    doc = fetcher.fetch(source["url"])
    return parse_pages([p.extract_text() or "" for p in PdfReader(doc.path).pages], source, doc)
