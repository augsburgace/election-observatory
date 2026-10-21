"""Shared evidence handling for pure analytical services."""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

RESEARCH_TIMEZONE = ZoneInfo("America/New_York")


def is_generic_poll_response(label: str) -> bool:
    """Recognize noncandidate response options without discarding named third parties."""
    normalized = re.sub(r"[^a-z0-9]+", " ", label.casefold().replace("’", "").replace("'", "")).strip()
    return normalized in {
        "undecided", "other", "refused", "dont know", "do not know", "not sure", "no response", "noresponse",
        "someone else", "someoneelse", "dont know refused", "dont know or refused", "dont know not sure",
        "undecided refused", "wouldnt vote", "would not vote", "wouldnt vote refused", "would not vote refused",
        "not voting", "will not vote", "wont vote", "no preference", "declined", "did not answer",
        "none of the above", "none", "another partys candidate", "another party candidate", "another candidate",
        "other candidate", "someone else write in", "another partys candidate write in",
    }


def instant(value: str | date | datetime | None, *, end_of_day: bool = False) -> datetime | None:
    """Date-only dashboard cutoffs use the user's New York calendar day."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if end_of_day else time.min, RESEARCH_TIMEZONE)
    else:
        value = str(value).strip()
        if len(value) == 10:
            parsed = datetime.combine(date.fromisoformat(value), time.max if end_of_day else time.min, RESEARCH_TIMEZONE)
        else:
            parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def day(value: Any) -> date:
    if isinstance(value, str) and len(value.strip()) == 10:
        return date.fromisoformat(value.strip())
    parsed = instant(value)
    if parsed is None:
        raise ValueError("A date is required")
    return parsed.astimezone(RESEARCH_TIMEZONE).date()


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")  # noqa: TRY004 -- public validation contract
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def evidence(record: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "source_id", "snapshot_id", "source_url", "published_at", "observed_at")
    return {key: record[key] for key in keys if record.get(key) is not None}


def source_refs(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for record in records:
        refs = [evidence(record)]
        metadata = record.get("metadata") or {}
        if metadata.get("dating_context_url") and metadata.get("dating_context_sha256"):
            refs.append({"source_id": record.get("source_id"), "source_url": metadata["dating_context_url"],
                "sha256": metadata["dating_context_sha256"], "role": "dating_context",
                "original_url": metadata.get("dating_context_original_url"),
                "capture": metadata.get("dating_context_capture")})
        if metadata.get("capture_inventory_url") and metadata.get("capture_inventory_sha256"):
            refs.append({"source_id": record.get("source_id"), "source_url": metadata["capture_inventory_url"],
                "sha256": metadata["capture_inventory_sha256"], "role": "archive_capture_inventory"})
        for ref in refs:
            key = repr(sorted(ref.items()))
            if ref and key not in seen:
                seen.add(key)
                result.append(ref)
    return result


def available_at(record: dict[str, Any]) -> datetime | None:
    """Return the earliest availability supported by the recorded precision.

    A publication *date* establishes availability by that New York day's end,
    rather than at midnight. An earlier same-day archived observation proves a
    more precise time. A documented publication timestamp can precede retrieval.
    Revised bytes need their own publication evidence or first observation;
    the original release's date never dates a subsequent correction.
    """
    metadata = record.get("metadata") or {}
    revised = metadata.get("is_revision") or metadata.get("revision_of")
    publication = metadata.get("revision_published_at") if revised else record.get("published_at")
    observed = instant(record.get("observed_at"), end_of_day=True)
    if publication is None or publication == "":
        return observed
    published = instant(publication, end_of_day=True)
    date_only = (isinstance(publication, date) and not isinstance(publication, datetime)) or (
        isinstance(publication, str) and len(publication.strip()) == 10)
    if date_only and observed is not None and day(observed) == day(publication):
        return min(published, observed)
    return published


def version_rank(record: dict[str, Any]) -> tuple[str, str, str]:
    metadata = record.get("metadata") or {}
    return (
        str(metadata.get("revision_published_at") or record.get("observed_at") or record.get("published_at") or ""),
        str(record.get("published_at") or ""),
        str(record.get("id") or ""),
    )
