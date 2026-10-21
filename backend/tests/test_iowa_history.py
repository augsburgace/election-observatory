"""Generated source-format fixtures validate parser safeguards, not election facts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from observatory.connectors.iowa_history import parse_pages
from observatory.geography import county_index


def make_pages(*, mismatch=False, missing=False, channels=False):
    rows = ["Absentee Ballot Statistics", "November 8, 2022 General Election", "County/ Party / Receipt Method Requested Issued Received"]
    for index, county in enumerate(county_index("IA")["by_geoid"].values()):
        if missing and index == 0:
            continue
        rows.append(f"{county['name']} 10 9 8")
        rows.extend(["Democrat 6 5 4", "Mail 4 4 4", "Republican 4 4 4", "Counter / In-Office 4 4 4"] if channels else ["Democrat 6 5 4", "Republican 4 4 4"])
    rows.append(f"Grand Total {991 if mismatch else 990} 891 792")
    rows.extend(["Prepared by the Office of Iowa Secretary of State", "Data from night before report date 10/21/2022"])
    return ["\n".join(rows)]


def doc():
    return SimpleNamespace(url="https://sos.iowa.gov/source.pdf", sha256="hash", retrieved_at="2026-10-21T16:00:00Z")


def test_full_native_county_party_reconciliation_and_retrospective_chronology():
    result = parse_pages(make_pages(), {"state": "IA", "cycle": 2022}, doc())
    assert result.metadata["parsed_report_count"] == 1
    assert result.metadata["reports"][0]["complete_registration_counties"] == 99
    assert all(row.time_basis == "reconstructed" and row.published_at.startswith("2026") for row in result.observations)
    state = next(row for row in result.observations if row.geography_type == "state" and row.metric == "ballots_returned" and row.category is None)
    assert state.value == 792 and state.mode == "all"
    assert "not establish original publication" in state.metadata["availability_definition"]


def test_nonreconciling_and_incomplete_county_days_fail_closed():
    for pages in [make_pages(mismatch=True), make_pages(missing=True)]:
        result = parse_pages(pages, {"state": "IA", "cycle": 2022}, doc())
        assert all(row.geography_type == "state" for row in result.observations)
        assert all(row.metadata["county_observations_withheld"] for row in result.observations)
        assert result.metadata["failed_reports"]


def test_receipt_channel_remains_joint_and_does_not_become_voting_mode():
    result = parse_pages(make_pages(channels=True), {"state": "IA", "cycle": 2022}, doc())
    joint = [row for row in result.observations if row.category_dimension == "registration_receipt_channel"]
    assert len(joint) == 198
    assert all(row.mode == "all" for row in joint)
    assert {row.category for row in joint} == {"DEM | Mail", "REP | Counter / In-Office"}


def test_missing_or_wrong_year_report_footers_fail_closed():
    for pages in [["Absentee Statistics no dated footer"], [make_pages()[0].replace("10/21/2022", "10/21/2024")]]:
        with pytest.raises(ValueError):
            parse_pages(pages, {"state": "IA", "cycle": 2022}, doc())


def test_archive_digest_and_capture_time_control_reported_availability(tmp_path, monkeypatch):
    import base64
    import hashlib
    import json

    from observatory.connectors import iowa_history

    path = tmp_path / "synthetic-original.pdf"
    path.write_bytes(b"synthetic PDF bytes; reader is stubbed to isolate archive chronology")
    digest = base64.b32encode(hashlib.sha1(path.read_bytes()).digest()).decode().rstrip("=")
    original = "https://sos.iowa.gov/elections/pdf/2022/general/AbsenteeCounty2022.pdf"
    timestamp = "20221021160000"
    source = {"state": "IA", "cycle": 2022, "url": "https://web.archive.org/cdx/source",
              "original_url": original, "archive_captures": [{"timestamp": timestamp, "digest": digest}]}
    inventory = [["timestamp", "original", "digest", "statuscode", "mimetype"],
                 [timestamp, original, digest, "200", "application/pdf"]]
    class Fetcher:
        def fetch(self, url):
            if "/cdx/" in url:
                return SimpleNamespace(url=url, sha256="inventory-hash", text=json.dumps(inventory))
            return SimpleNamespace(url=url, path=str(path), sha256="payload-hash", retrieved_at="2026-10-21T16:00:00Z")
    class Page:
        def extract_text(self, **kwargs):
            return make_pages()[0]
    monkeypatch.setattr(iowa_history, "PdfReader", lambda _: SimpleNamespace(pages=[Page()]))
    result = iowa_history.collect(source, Fetcher())
    assert all(row.time_basis == "reported" for row in result.observations)
    assert all(row.published_at == "2022-10-21T16:00:00+00:00" for row in result.observations)
    assert all(row.metadata["archive_capture_digest"] == digest for row in result.observations)
    assert all(row.metadata["period_end"] == "2022-10-20" for row in result.observations)
    assert result.metadata["captures"][0]["capture_digest_verified"] is True
    path.write_bytes(b"tampered bytes")
    with pytest.raises(ValueError, match="No archived Iowa reports"):
        iowa_history.collect(source, Fetcher())


def test_later_archive_capture_never_backdates_combined_history(tmp_path, monkeypatch):
    import base64
    import hashlib
    import json

    from observatory.connectors import iowa_history

    path = tmp_path / "later.pdf"
    path.write_bytes(b"later combined file")
    digest = base64.b32encode(hashlib.sha1(path.read_bytes()).digest()).decode().rstrip("=")
    original = "https://sos.iowa.gov/elections/pdf/2022/general/AbsenteeCounty2022.pdf"
    timestamp = "20240113160000"
    inventory = [["timestamp", "original", "digest", "statuscode", "mimetype"], [timestamp, original, digest, "200", "application/pdf"]]
    source = {"state": "IA", "cycle": 2022, "url": "https://web.archive.org/cdx/source", "original_url": original,
              "archive_captures": [{"timestamp": timestamp, "digest": digest}]}
    class Fetcher:
        def fetch(self, url):
            return SimpleNamespace(url=url, sha256="hash", text=json.dumps(inventory), path=str(path), retrieved_at="2026-10-21T16:00:00Z")
    class Page:
        def extract_text(self, **kwargs):
            return make_pages()[0]
    monkeypatch.setattr(iowa_history, "PdfReader", lambda _: SimpleNamespace(pages=[Page()]))
    result = iowa_history.collect(source, Fetcher())
    assert all(row.time_basis == "reconstructed" and row.published_at.startswith("2024") for row in result.observations)
    assert not any(row.metadata["historical_publication_verified"] for row in result.observations)


def test_legacy_county_number_cannot_fill_a_blank_status_cell():
    from observatory.connectors.iowa_history import _numeric_row

    assert _numeric_row("Adair 01 1509 1509 1459", 2016) == ("Adair", (1509, 1509, 1459))
    assert _numeric_row("Adair 01 1509 1509", 2016) is None
    assert _numeric_row("Democrat 406 406 389", 2016) == ("Democrat", (406, 406, 389))
