"""Chronology and native-measure safeguards for the public 2024 UF archive."""
from types import SimpleNamespace

import pytest
from observatory.connectors import uf_history


def parse(row, capture="2024-11-04T12:00:00Z"):
    source = {"state": "US", "cycle": 2024}
    doc = SimpleNamespace(url="https://fixture.invalid/capture.csv", sha256="a" * 64, retrieved_at="2026-10-21T00:00:00Z")
    return uf_history.parse_row(source, doc, row, capture)


def ohio_row():
    return {"state": "Ohio", "state_abbv": "OH", "last_update": "11/2/2024", "request_all": "100",
            "accept_all": "30", "inperson_all": "50", "voted_all": "80", "data_source": "Official Ohio dashboard"}


def test_archive_availability_and_native_methods_remain_distinct():
    observations, manifest = parse(ohio_row())
    assert len(observations) == 8
    assert {row.cycle for row in observations} == {2024}
    assert {row.published_at for row in observations} == {"2024-11-04T12:00:00Z"}
    assert manifest["date"] == "2024-11-02"
    assert {row.time_basis for row in observations} == {"reported", "reconstructed"}


@pytest.mark.parametrize("native_date", ["11/7/2022", "11/5/2024"])
def test_template_prior_cycle_and_future_dates_are_rejected(native_date):
    with pytest.raises(ValueError, match="Template"):
        parse({**ohio_row(), "last_update": native_date})


def test_combined_total_cannot_hide_method_reconciliation_failure():
    observations, manifest = parse({**ohio_row(), "voted_all": "90"})
    assert not any(row.metric == "ballots_cast" and row.mode == "all" for row in observations)
    assert any(row.metric == "ballots_returned" and row.value == 30 for row in observations)
    assert "withheld" in manifest["warnings"][0]


def test_zeros_are_missing_placeholders_and_not_returned_counts():
    observations, _ = parse({**ohio_row(), "accept_all": "0", "inperson_all": "0", "voted_all": "0"})
    assert {row.metric for row in observations} == {"ballots_requested"}


def test_ohio_primary_history_is_never_promoted_to_party_registration():
    observations, _ = parse({**ohio_row(), "voted_dem": "40", "voted_rep": "30", "voted_none": "10"})
    assert not any(row.category_dimension == "registration" for row in observations)


def test_iowa_native_absentee_receipts_are_not_silently_called_mail_only():
    observations, _ = parse({**ohio_row(), "state_abbv": "IA", "state": "Iowa", "inperson_all": "0", "voted_all": "30"})
    assert {row.mode for row in observations if row.metric == "ballots_returned"} == {"all"}


def test_overlapping_or_invalid_composition_is_withheld():
    observations, manifest = parse({**ohio_row(), "state_abbv": "FL", "state": "Florida", "voted_dem": "60", "voted_rep": "30", "voted_none": "10"})
    assert not any(row.category_dimension == "registration" for row in observations)
    assert any("breakdown withheld" in warning for warning in manifest["warnings"])
