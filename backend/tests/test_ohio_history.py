"""Arithmetic/definition regression fixtures for original Ohio survey archives."""
from types import SimpleNamespace

import pytest
from observatory.connectors import ohio_history
from observatory.geography import county_index


def fixture(monkeypatch, tmp_path, *, returns=True):
    names = sorted(row["name"] for row in county_index("OH")["by_geoid"].values())
    assert len(names) == 88
    headers = ["County", "Total Ballots Requested", "Ballots Cast Early In Person"]
    if returns:
        headers.append("Ballots Returned and Submitted for Counting")
    values = [100, 20, 70] if returns else [100, 20]
    rows = [headers, ["TOTAL", *[str(v * 88) for v in values]]]
    rows += [[name, *map(str, values), "", "999999", "888888", "777777"] for name in names]
    monkeypatch.setattr(ohio_history, "xlsx_rows", lambda _: rows)
    path = tmp_path / "explicitly-synthetic-test-only.xlsx"
    path.write_bytes(b"Fixture transport replaced by synthetic first-sheet values")
    source = {"state": "OH", "cycle": 2022, "data_date": "2022-11-07", "report_date": "2022-11-07",
        "archive_captured_at": "2025-03-06T11:29:39Z", "original_url": "https://fixture.invalid/original.xlsx",
        "date_semantics": "Synthetic dated report"}
    document = SimpleNamespace(path=path, url="https://fixture.invalid/archive.xlsx", sha256="0" * 64,
        retrieved_at="2026-10-21T12:00:00Z")
    return source, document, rows


def test_disjoint_native_remainders_and_prior_columns_never_create_fake_history(monkeypatch, tmp_path):
    source, document, _ = fixture(monkeypatch, tmp_path)
    batch = ohio_history.parse(source, document)
    assert len(batch.observations) == 89 * 4 * 2
    total = [r for r in batch.observations if r.geography_type == "state" and r.time_basis == "reconstructed"]
    counts = {(r.metric, r.mode): r.value for r in total}
    assert counts["ballots_cast", "all"] == 70 * 88
    assert counts["ballots_cast", "early_in_person"] == 20 * 88
    assert counts["ballots_requested", "mail"] == 80 * 88
    assert counts["ballots_returned", "mail"] == 50 * 88
    assert {r.cycle for r in batch.observations} == {2022}
    assert all(r.published_at == "2025-03-06T11:29:39Z" for r in batch.observations)


def test_request_only_report_never_manufactures_a_returned_or_total_ballot_count(monkeypatch, tmp_path):
    source, document, _ = fixture(monkeypatch, tmp_path, returns=False)
    batch = ohio_history.parse(source, document)
    assert {r.mode for r in batch.observations if r.metric == "ballots_cast"} == {"early_in_person"}
    assert not any(r.metric == "ballots_returned" for r in batch.observations)


def test_incomplete_reconciliation_and_unknown_county_fail_closed(monkeypatch, tmp_path):
    source, document, rows = fixture(monkeypatch, tmp_path)
    rows[2][3] = "71"
    with pytest.raises(ValueError, match="reconcile"):
        ohio_history.parse(source, document)
    rows[2][3] = "70"
    rows[2][0] = "Unverified place"
    with pytest.raises(ValueError, match="canonical"):
        ohio_history.parse(source, document)


def test_dated_republished_endpoint_is_reconstructed_only_and_reconciles(monkeypatch, tmp_path):
    source, document, rows = fixture(monkeypatch, tmp_path)
    rows[1] += ["", "8800", "1760", "6160"]
    for row in rows[2:]:
        row[4:] = ["", "100", "20", "70"]
    source.update(cycle=2018, data_date="2018-11-05", report_date="2018-11-05",
        column_start=5, republished_historical_columns=True, context_verified=True,
        expected_totals=[8800, 1760, 6160], workbook_vintage=2022,
        context_url="https://fixture.invalid/dated-original-2018-release", context_sha256="1" * 64)
    batch = ohio_history.parse(source, document)
    assert len(batch.observations) == 89 * 4
    assert {row.time_basis for row in batch.observations} == {"reconstructed"}
    assert {row.cycle for row in batch.observations} == {2018}
    assert {row.date for row in batch.observations} == {"2018-11-05"}
    assert all(row.metadata["workbook_vintage"] == 2022 for row in batch.observations)
    source["expected_totals"][2] += 1
    with pytest.raises(ValueError, match="three dated"):
        ohio_history.parse(source, document)


def test_republished_columns_without_primary_date_context_fail_closed(monkeypatch, tmp_path):
    source, document, _ = fixture(monkeypatch, tmp_path)
    source.update(column_start=5, republished_historical_columns=True, cycle=2018)
    with pytest.raises(ValueError, match="original dated release"):
        ohio_history.parse(source, document)


def test_archive_capture_digest_verification(tmp_path):
    import base64
    import hashlib

    path = tmp_path / "archive-bytes"
    path.write_bytes(b"explicit test archive")
    doc = SimpleNamespace(path=path)
    digest = base64.b32encode(hashlib.sha1(path.read_bytes()).digest()).decode()
    ohio_history._verify_digest(doc, digest)
    with pytest.raises(ValueError, match="CDX capture digest"):
        ohio_history._verify_digest(doc, "0" * 32)


def test_2016_native_military_domestic_and_method_categories_remain_disjoint(monkeypatch, tmp_path):
    source, document, rows = fixture(monkeypatch, tmp_path)
    names = [row[0] for row in rows[2:]]
    values = [100, 70, 3, 2, 1, 75, 46, 21]
    header = ["County", "", "Total Ballots Requested", "Total Ballots Cast", "Military & Overseas Ballots Requested",
        "Military/Overseas Ballots Returned for Counting", "Military/Overseas Requested & Cast In-Person",
        "Domestic Ballots Requested", "Domestic Ballots Returned & Submitted for Counting", "Domestic Ballots Requested & Cast In-Person"]
    rows[:] = [header, [""] * 10, ["Statewide", "", *[str(v * 88) for v in values]]]
    rows.extend([[name, "", *map(str, values)] for name in names])
    source.update(cycle=2016, native_schema="2016_detailed", retrospective_only=True,
        data_date="2016-10-28", report_date="2016-10-31", expected_totals=[8800, 6160])
    batch = ohio_history.parse(source, document)
    total = {(r.metric, r.mode): r.value for r in batch.observations if r.geography_type == "state"}
    assert total["ballots_cast", "early_in_person"] == 22 * 88
    assert total["ballots_returned", "mail"] == 48 * 88
    assert total["ballots_requested", "mail"] == 78 * 88
    assert total["ballots_cast", "all"] == 70 * 88
    assert {row.time_basis for row in batch.observations} == {"reconstructed"}
    rows[3][5] = "3"
    with pytest.raises(ValueError, match="method components"):
        ohio_history.parse(source, document)


def native2020_fixture(monkeypatch, tmp_path, *, width=6):
    source, document, previous = fixture(monkeypatch, tmp_path)
    names = [row[0] for row in previous[2:]]
    header = ["County", "UOCAVA Applications", "Non-UOCAVA Applications", "Early In Person Ballots Cast",
              "Ballots Returned and Submitted for Counting", "Total Ballots Returned and Submitted for Counting"][:width]
    values = [3, 97, 20, 50, 70][:width - 1]
    rows = [header, ["TOTAL", *[str(v * 88) for v in values]], *[[name, *map(str, values)] for name in names]]
    monkeypatch.setattr(ohio_history, "xlsx_rows", lambda _: rows)
    source.update(cycle=2020, native_schema="2020_native", data_date="2020-10-27", report_date="2020-10-27",
                  expected_native_totals=[v * 88 for v in values], retrospective_only=False,
                  archive_captured_at="2020-11-01T01:20:11Z", context_captured_at="2020-11-01T10:37:47Z")
    return source, document, rows


def test_2020_native_modes_reconcile_without_inventing_request_method(monkeypatch, tmp_path):
    source, document, _ = native2020_fixture(monkeypatch, tmp_path)
    batch = ohio_history.parse(source, document)
    totals = {(r.metric, r.mode): r.value for r in batch.observations if r.geography_type == "state"}
    assert totals == {("ballots_requested", "all"): 8800, ("ballots_cast", "early_in_person"): 1760,
                      ("ballots_returned", "mail"): 4400, ("ballots_cast", "all"): 6160}
    assert not any(r.metric == "ballots_requested" and r.mode == "mail" for r in batch.observations)
    assert all(r.published_at == "2020-11-01T10:37:47Z" for r in batch.observations)
    assert all(r.category_dimension is None for r in batch.observations)


@pytest.mark.parametrize("width,expected_metrics", [(3, {"ballots_requested"}), (4, {"ballots_requested", "ballots_cast"})])
def test_2020_incomplete_native_columns_preserve_missing_returns(monkeypatch, tmp_path, width, expected_metrics):
    source, document, _ = native2020_fixture(monkeypatch, tmp_path, width=width)
    source["retrospective_only"] = True
    batch = ohio_history.parse(source, document)
    assert {r.metric for r in batch.observations} == expected_metrics
    assert not any(r.metric == "ballots_cast" and r.mode == "all" for r in batch.observations)
    assert {r.time_basis for r in batch.observations} == {"reconstructed"}


def test_2020_native_combined_arithmetic_is_independently_validated(monkeypatch, tmp_path):
    source, document, rows = native2020_fixture(monkeypatch, tmp_path)
    # Keep county/state reconciliation exact while corrupting the mode equation.
    rows[1][-1] = str(71 * 88)
    source["expected_native_totals"][-1] = 71 * 88
    for row in rows[2:]:
        row[-1] = "71"
    with pytest.raises(ValueError, match="mail returns plus in-person"):
        ohio_history.parse(source, document)
