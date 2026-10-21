"""Synthetic report fixtures exercise the NC parser; no fixture is research data."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from urllib.parse import quote, urlencode

import pytest
from observatory.analytics import historical_analysis
from observatory.connectors.nc_reports import (
    BUCKET,
    PREFIXES,
    _counties,
    collect,
    parse_report,
    report_date_from_key,
)
from reportlab.pdfgen.canvas import Canvas


def document(tmp_path, lines, *, name="report", url="https://s3.amazonaws.com/dl.ncsbe.gov/synthetic.pdf"):
    path = tmp_path / f"{name}.pdf"
    canvas = Canvas(str(path))
    y = 810
    for line in lines:
        canvas.drawString(20, y, line)
        y -= 16
    canvas.save()
    return SimpleNamespace(path=str(path), url=url, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           retrieved_at="2026-10-26T20:00:00+00:00", text=None)


def lines(report_day="20", period_day="19"):
    return [
        "General Statistics Total Ballots Cast (Absentee/Early Voting)",
        "Total Ballots Cast 10 In-Person Early Voting 6",
        "Total Eligible Voters* 100 Civilian (Mail) 2",
        "Turnout 10.00% Military (Mail) 1", "Overseas (Mail) 1",
        "Registration Statistics by Party % Ballots Cast by Party Turnout* Proportion**",
        "Democratic 60 60.00% Democratic 6 10.00% 60.00%",
        "Republican 40 40.00% Republican 4 10.00% 40.00%",
        "Registration Statistics by Race % Ballots Cast by Race Turnout* Proportion**",
        "White 50 50.00% White 5 10.00% 50.00%",
        "Black 30 30.00% Black 3 10.00% 30.00%",
        "Other 20 20.00% Other 2 10.00% 20.00%",
        "Registration Statistics by Gender % Ballots Cast by Gender Turnout* Proportion**",
        "Female 55 55.00% Female 6 10.91% 60.00%",
        "Male 45 45.00% Male 4 8.89% 40.00%",
        "N.C. Absentee & Early Voting Statistics for the 2026 General Election",
        f"Published 10/{report_day}/2026; Ballots cast through 10/{period_day}/2026",
    ]


def entry(day="20", modified="2026-10-20T12:43:20.000Z"):
    return {"key": f"{PREFIXES[2026]}2026-10-{day} Daily Absentee Stats Report - 2026 General.pdf",
            "date": f"2026-10-{day}", "last_modified": modified,
            "listing_url": BUCKET + "?" + urlencode({"prefix": PREFIXES[2026]}), "listing_sha256": "xml-hash"}


def test_report_parses_primary_totals_exact_denominators_and_native_categories(tmp_path):
    parsed, warnings = parse_report({"state": "NC", "cycle": 2026}, document(tmp_path, lines()), entry())
    totals = [row for row in parsed if row.geography_type == "state" and row.mode == "all"
              and row.metric == "ballots_cast" and row.category_dimension is None]
    assert len(totals) == 2  # Separate reported and reconstructed research views.
    assert all(row.value == 10 and row.denominator == 100 for row in totals)
    assert all(row.published_at == "2026-10-20T12:43:20.000Z" for row in totals)
    assert all(row.metadata["period_end"] == "2026-10-19" for row in totals)
    registered = [row for row in parsed if row.metric == "registered_voters" and row.category_dimension is None]
    assert all(row.value == 100 and row.unit == "voters" for row in registered)
    dem = next(row for row in parsed if row.category == "DEM" and row.metric == "ballots_cast")
    assert dem.value == 6 and dem.denominator == 60
    assert any(row.category_dimension == "race_report" for row in parsed)
    assert not any(row.category_dimension == "race" for row in parsed)
    assert all(row.denominator is None for row in parsed if row.geography_type == "county")
    assert any("county" in warning for warning in warnings)


def test_later_archived_pdf_is_not_backdated_in_reported_replay(tmp_path):
    parsed, warnings = parse_report({"state": "NC", "cycle": 2026}, document(tmp_path, lines()),
                                   entry(modified="2026-10-25T12:00:00Z"))
    rows = [{**row.model_dump(), "id": index, "source_id": "synthetic-report", "snapshot_id": 1,
             "observed_at": "2026-10-26T20:00:00Z"} for index, row in enumerate(parsed, start=1)]
    strict = historical_analysis(rows, state="NC", cycle=2026, as_of="2026-10-20",
                                 metric="ballots_cast", time_basis="reported")
    reconstructed = historical_analysis(rows, state="NC", cycle=2026, as_of="2026-10-20",
                                        metric="ballots_cast", time_basis="reconstructed")
    assert strict["latest"] is None
    assert reconstructed["latest"]["value"] == 10
    assert any("modified after" in warning for warning in warnings)


def test_filename_and_printed_report_date_must_agree(tmp_path):
    with pytest.raises(ValueError, match="dates conflict"):
        parse_report({"state": "NC", "cycle": 2026}, document(tmp_path, lines(report_day="19")), entry())


def test_voting_modes_must_reconcile_before_publishing_total(tmp_path):
    changed = [line.replace("Overseas (Mail) 1", "Overseas (Mail) 2") for line in lines()]
    with pytest.raises(ValueError, match="do not sum"):
        parse_report({"state": "NC", "cycle": 2026}, document(tmp_path, changed), entry())


def test_demographics_with_failed_reconciliation_are_withheld(tmp_path):
    changed = [line.replace("Democratic 6 10.00%", "Democratic 7 10.00%") for line in lines()]
    parsed, warnings = parse_report({"state": "NC", "cycle": 2026}, document(tmp_path, changed), entry())
    assert not any(row.category_dimension == "registration" for row in parsed)
    assert any("Party" in warning for warning in warnings)


def test_county_parser_handles_pdf_header_extracted_after_cells_and_requires_complete_reconciliation():
    county_names = ["SYNTHETIC " + chr(65 + index // 26) + chr(65 + index % 26) for index in range(100)]
    text = "\n".join([f"{name} 6 2 1 1 10" for name in county_names] + ["Ballots Cast by County"])
    parsed, warnings = _counties([text], total=1000, early_total=600, cycle=2026)
    assert len(parsed) == 100 and not warnings
    assert all(row["mail"] == 4 for row in parsed)
    failed, warnings = _counties([text], total=999, early_total=600, cycle=2026)
    assert failed == [] and warnings


def test_key_date_supports_current_and_archived_official_naming():
    assert report_date_from_key("2026-10-20 Daily Absentee Stats Report - 2026 General.pdf", 2026) == "2026-10-20"
    assert report_date_from_key("Absentee_Stats_2020General_10202020.pdf", 2020) == "2020-10-20"
    assert report_date_from_key("Absentee_Stats_Combined_October_31_2018.pdf", 2018) == "2018-10-31"
    assert report_date_from_key("An unrelated press release.pdf", 2026) is None


def test_collector_keeps_valid_reports_and_exposes_missing_failed_dates(tmp_path):
    prefix = PREFIXES[2026]
    key19 = f"{prefix}2026-10-19 Daily Absentee Stats Report - 2026 General.pdf"
    key20 = f"{prefix}2026-10-20 Daily Absentee Stats Report - 2026 General.pdf"
    listing_url = BUCKET + "?" + urlencode({"prefix": prefix})
    xml = "<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'><IsTruncated>false</IsTruncated>"
    for key, timestamp in ((key19, "2026-10-19T12:00:00Z"), (key20, "2026-10-20T12:00:00Z")):
        xml += f"<Contents><Key>{key}</Key><LastModified>{timestamp}</LastModified></Contents>"
    xml += "</ListBucketResult>"
    mapping = {
        listing_url: SimpleNamespace(text=xml, url=listing_url, sha256="xml-hash"),
        BUCKET + quote(key19, safe="/"): document(tmp_path, lines("19", "18"), name="valid"),
        BUCKET + quote(key20, safe="/"): document(tmp_path, ["Synthetic invalid source template"], name="invalid"),
    }
    fetcher = SimpleNamespace(fetch=lambda url: mapping[url])
    result = collect({"state": "NC", "cycle": 2026, "url": listing_url}, fetcher)
    assert result.metadata["parsed_report_count"] == 1
    assert result.metadata["available_report_count"] == 2
    assert result.metadata["failed_reports"][0]["date"] == "2026-10-20"
    assert result.data_as_of == "2026-10-18"
    assert not any(row.date == "2026-10-20" for row in result.observations)
