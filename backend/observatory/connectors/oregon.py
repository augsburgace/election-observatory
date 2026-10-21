"""Official Oregon PDF: counts and dated active registration, never chart labels."""
import re

from pypdf import PdfReader

from observatory.domain import ParsedBatch

from .common import iso_date, number, observation


def parse_pages(pages, source, doc):
    text = "\n".join(pages)
    generated = re.search(r"Report Generated:\s*(\d{1,2}/\d{1,2}/\d{4})", text)
    frozen = re.search(r"snapshot as of\s*(\d{1,2}/\d{1,2}/\d{2,4})", text, re.I)
    if not generated or not frozen:
        raise ValueError("Oregon report/denominator dates are not established")
    date, denominator_date = iso_date(generated[1]), iso_date(frozen[1])
    if not date.startswith(str(source.get("cycle", 2026))):
        raise ValueError("Oregon PDF belongs to another election cycle")
    county_page = next((p for p in pages if "Unofficial Ballots Returns by County" in p and "Active Voters" in p), None)
    if not county_page:
        raise ValueError("Oregon county table missing")
    rows = []
    for line in county_page.splitlines():
        match = re.fullmatch(r"\s*([A-Z][A-Z ]+|Total)\s+(\d[\d,]*)(?:\s+(\d[\d,]*)\s+([\d.]+)%?)?\s*", line)
        if match:
            rows.append((match[1].strip(), number(match[2]), number(match[3]) if match[3] else None))
    total = next((r for r in rows if r[0] == "Total"), None)
    counties = [r for r in rows if r[0] != "Total"]
    if not total or len(counties) != 36 or sum(r[1] for r in counties) != total[1] or sum(r[2] or 0 for r in counties) != total[2]:
        raise ValueError("Oregon county counts/registration do not reconcile with the published total")
    observations = []
    for name, active, returned in rows:
        meta = {"denominator_date": denominator_date, "denominator_definition": "Active registered voters frozen at the report's stated snapshot",
            "native_definition": "Unofficial ballots received; acceptance/certification not established.",
            "printed_percentage_definition": "County column is a share of statewide active voters; it is NOT the county return rate.",
            "source_usage_note": "Producer labels this a transparency report, not official reporting, certification or formal analysis.",
            "reported_county_returns": sum(r[2] is not None for r in counties), "expected_counties": 36}
        common = dict(name="Oregon" if name == "Total" else name.title(), kind="state" if name == "Total" else "county",
            published_at=date, metadata=meta)
        registration = observation(source, doc, metric="registered_voters", value=active, mode="all", date_=denominator_date, **common)
        registration.unit = "voters"
        observations.append(registration)
        if returned is not None:
            item = observation(source, doc, metric="ballots_returned", value=returned, mode="mail", date_=date, **common)
            item.denominator = active
            observations.append(item)
    return ParsedBatch(observations=observations, data_as_of=date, metadata={"primary_document_url": doc.url},
        warnings=["Descriptive unofficial receipts; producer excludes certification/formal-reporting use.",
            "Blank county return cells remain missing, even when other rows sum to the statewide total.",
            "Participation rates are computed against dated active registration, not the PDF's county percentage column."])


def collect(source, fetcher):
    doc = fetcher.fetch(source["url"])
    return parse_pages([p.extract_text(extraction_mode="layout") or "" for p in PdfReader(doc.path).pages], source, doc)
