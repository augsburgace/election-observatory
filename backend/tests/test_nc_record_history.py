"""Synthetic final-record fixtures contain no real voters."""
from __future__ import annotations

import json
from collections import Counter
from types import SimpleNamespace

import pytest
from observatory.connectors.nc_record_history import parse_records
from observatory.geography import county_index

SOURCE = {"state": "NC", "cycle": 2016, "native_calendar": {"early_in_person_open": "2016-10-20", "early_in_person_close": "2016-11-05"}}
DOC = SimpleNamespace(url="https://s3.amazonaws.com/dl.ncsbe.gov/final2016.zip", sha256="sourcehash", retrieved_at="2026-10-21T16:00:00Z")


def records():
    result = []
    expected = Counter()
    for index, county in enumerate(county_index("NC")["by_geoid"].values()):
        for mode, native in [("early_in_person", "ONE-STOP"), ("mail", "MAIL")]:
            result.append({"county_desc": county["name"], "ncid": f"test-{index}-{mode}", "ballot_req_type": native,
                           "ballot_rtn_dt": "10/20/2016" if index == 0 else "10/21/2016", "ballot_rtn_status": "ACCEPTED",
                           "voter_party_code": "DEM", "race": "NATIVE SOURCE CATEGORY", "ethnicity": "Undesignated",
                           "gender": "F", "voter_street_address": "DO NOT PERSIST THIS PRIVATE FIELD"})
            expected[(county["geoid"], mode)] += 1
    return result, dict(expected)


def test_complete_cohort_dates_zeroes_reconcile_without_personal_fields():
    rows, expected = records()
    batch = parse_records(iter(rows), SOURCE, DOC, expected_final=expected)
    assert batch.metadata["native_accepted_count"] == 200
    assert batch.metadata["final_aggregate_reconciled"] is True
    assert all(row.time_basis == "reconstructed" for row in batch.observations)
    assert all(row.metadata["status_known_at_return_date"] is False for row in batch.observations)
    assert any(row.value == 0 and row.geography_type == "county" for row in batch.observations)
    assert "DO NOT PERSIST" not in json.dumps(batch.model_dump())
    assert "test-0-" not in json.dumps(batch.model_dump())
    total = next(row for row in batch.observations if row.date == "2016-10-21" and row.geography_type == "state"
                 and row.mode == "all" and row.category is None)
    assert total.value == 200


def test_duplicate_accepted_records_and_final_aggregate_mismatch_fail_closed():
    rows, expected = records()
    with pytest.raises(ValueError, match="repeated accepted"):
        parse_records(iter([*rows, rows[0]]), SOURCE, DOC, expected_final=expected)
    expected[next(iter(expected))] += 1
    with pytest.raises(ValueError, match="do not match"):
        parse_records(iter(rows), SOURCE, DOC, expected_final=expected)


def test_final_status_is_not_backdated_and_calendar_anomalies_are_excluded():
    rows, expected = records()
    rows[0]["ballot_rtn_dt"] = "10/19/2016"
    batch = parse_records(iter(rows), SOURCE, DOC, expected_final=expected)
    assert batch.metadata["excluded_anomalous_return_dates"] == 1
    assert batch.metadata["native_accepted_count"] == 200
    assert batch.metadata["temporal_coverage_complete"] is False
    assert not any(row.date == "2016-10-19" for row in batch.observations)
    assert all(row.published_at.startswith("2026") for row in batch.observations)
    assert all(row.mode == "all" for row in batch.observations if row.category_dimension == "race" and row.mode == "all")
