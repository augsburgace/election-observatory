"""Primary-source router. A successful page fetch is never counted as parsed data."""
from observatory.domain import ParsedBatch

from . import (
    alaska,
    calendars,
    electproject_history,
    external_context,
    florida,
    hawaii,
    iowa,
    iowa_history,
    maine,
    nc_record_history,
    nc_reports,
    north_carolina,
    ohio_history,
    oregon,
    polling,
    reconmr,
    research_polls,
    south_carolina,
    turnout_historical,
    uf_election_lab,
    uf_history,
)
from .common import document_text, soup


def collect(source: dict, fetcher) -> ParsedBatch:
    adapters = {"nc_counts": north_carolina.collect, "fl_stats": florida.collect,
                "sc_early": south_carolina.collect, "ia_pdf": iowa.collect,
                "ak_statistics": alaska.collect, "marist_pdf": polling.collect, "me_records": maine.collect,
                "uf_tracker": uf_election_lab.collect, "reconmr_pdf": reconmr.collect,
                "research_poll": research_polls.collect, "nc_reports": nc_reports.collect,
                "calendar_reference": calendars.collect, "hi_receipts": hawaii.collect, "or_receipts": oregon.collect}
    adapters.update(electproject_history=electproject_history.collect, iowa_history=iowa_history.collect,
                    turnout_historical=turnout_historical.collect, nc_record_history=nc_record_history.collect,
                    ohio_history=ohio_history.collect, external_context=external_context.collect,
                    uf_history=uf_history.collect)
    connector = source.get("connector", "discovery")
    if connector in adapters:
        return adapters[connector](source, fetcher)
    if connector != "discovery":
        raise ValueError(f"Unknown connector: {connector}")
    doc = fetcher.fetch(source["url"])
    content = document_text(doc)
    text = soup(doc).get_text(" ", strip=True)
    blocked = any(s in text.lower() for s in ("just a moment", "captcha", "access denied", "enable javascript and cookies", "request could not be satisfied"))
    warning = source.get("limitation", "Source archived for discovery; unattended extraction is not validated.")
    if blocked:
        raise ValueError("Source returned an access/security challenge, not election data; no observations published")
    return ParsedBatch(warnings=[warning], metadata={"status": "discovery_only", "page_title": soup(doc).title.get_text() if soup(doc).title else None,
                                                    "source_bytes": len(content), "parsed_election_data": False})
