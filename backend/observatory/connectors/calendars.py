"""Verified method-specific calendar references, never fabricated vote observations."""
from __future__ import annotations

import calendar
import json
import re
from datetime import date
from pathlib import Path

from observatory.domain import ParsedBatch

from .common import soup

CONFIG = Path(__file__).resolve().parents[3] / "config" / "calendars.json"


def load_calendars() -> list[dict]:
    config = json.loads(CONFIG.read_text())
    references = []
    for row in config["calendars"]:
        start, end = date.fromisoformat(row["voting_open_date"]), date.fromisoformat(row["voting_close_date"])
        if start.year != row["cycle"] or end.year != row["cycle"] or end < start:
            raise ValueError("Invalid verified calendar range")
        if (end - start).days + 1 != row["calendar_span_days"]:
            raise ValueError("Calendar span does not match verified endpoints")
        references.append({**row, "verified_at": config["verified_at"]})
    return references


def calendar_reference(state: str, cycle: int, mode: str) -> dict | None:
    return next((row for row in load_calendars() if row["state"] == state.upper()
                 and row["cycle"] == cycle and row["mode"] == mode), None)


def _date_mentioned(text: str, value: str) -> bool:
    parsed = date.fromisoformat(value)
    month = rf"(?:{calendar.month_name[parsed.month]}|{calendar.month_abbr[parsed.month]}\.?)"
    return bool(re.search(rf"\b{month}\s+0?{parsed.day}(?!\d)", text, re.I))


def collect(source: dict, fetcher) -> ParsedBatch:
    reference = calendar_reference(source.get("state", "NC"), int(source["cycle"]), "early_in_person")
    if reference is None or source["url"] != reference["source_url"]:
        raise ValueError("No verified calendar reference matches this source")
    document = fetcher.fetch(reference["source_url"])
    page = soup(document)
    text = re.sub(r"\s+", " ", (page.find("article") or page.find("main") or page).get_text(" ", strip=True))
    if any(marker in text.lower() for marker in ("access denied", "captcha", "just a moment")):
        raise ValueError("Calendar authority returned an access challenge")
    if not all(_date_mentioned(text, reference[key]) for key in ("voting_open_date", "voting_close_date")):
        raise ValueError("Original calendar no longer confirms the verified opening/closing dates")
    if str(reference["cycle"]) not in text or not re.search(r"early voting|in.person absentee voting", text, re.I):
        raise ValueError("Original calendar election context changed")
    return ParsedBatch(metadata={"reference_data": "calendar", "parsed_election_data": False,
        "calendar": {**reference, "source_sha256": document.sha256, "retrieved_at": document.retrieved_at,
                     "validation": "Both month/day endpoints and election year found in original visible calendar content"}},
        warnings=[reference["limitation"]])
