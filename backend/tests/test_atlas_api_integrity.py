"""Version-two contracts use synthetic evidence and never fetch live datasets."""
from __future__ import annotations

import csv
import io

from observatory.atlas.ingest import _publish, parse_results
from observatory.atlas_api import _result_export
from observatory.domain import FetchedDocument
from test_atlas_data import native, rows_file
from test_evidence_workflows import BASE_QUERY, aggregate
from test_evidence_workflows import harness as harness


def test_paginated_observations_preserve_query_scope_and_brush(harness):
    harness.state.payload["observations"] = [aggregate(10, date="2026-10-19"), aggregate(20)]
    harness.collect()
    response = harness.client.get("/api/v2/observations", params={**BASE_QUERY,
        "date_window": "2026-10-19,2026-10-19", "offset": 0, "limit": 1})
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1
    assert result["observations"][0]["value"] == 10
    assert result["query"]["date_window"] == ["2026-10-19", "2026-10-19"]
    assert result["revision"] == result["query"]["revision"]


def test_invalid_family_and_mismatched_state_never_start_downloads(harness):
    assert harness.client.post("/api/v2/datasets/medsl_2024/load", json={}).status_code == 422
    assert harness.client.post("/api/v2/datasets/medsl_2024_TX/load", json={"state": "CA"}).status_code == 422
    assert harness.client.post("/api/v2/datasets/unverified-source/load", json={}).status_code == 404
    datasets = harness.client.get("/api/v2/catalog/datasets", params={"state": "AZ"}).json()["datasets"]
    assert any(row["id"] == "uf-fallback-az" and row["provider"] == "participation" for row in datasets)
    assert all(not row.get("state") or row["state"] == "AZ" for row in datasets)
    assert harness.client.get("/api/v2/results", params={"revision": 99999}).status_code == 422
    assert harness.client.get("/api/v2/context", params={"state": "NO"}).status_code == 422


def test_place_history_is_paged_and_pinned_metadata_does_not_gain_later_years(harness, tmp_path):
    revisions = []
    for year in (2020, 2024):
        path = rows_file(tmp_path, [native(year=str(year)), native(year=str(year), candidate="Candidate B", party_simplified="REPUBLICAN", votes="80")])
        source = {"id": f"synthetic-{year}", "provider": "county_legacy", "years": [year], "title": "Synthetic", "tier": 1}
        parsed, metadata = parse_results(source, str(path))
        document = FetchedDocument(url="https://fixture.invalid/results.csv", path=str(path), sha256=str(year) * 16,
            content_type="text/csv", retrieved_at="2026-10-21T04:00:00Z", byte_count=path.stat().st_size)
        revisions.append(_publish(harness.database, source, document, parsed, metadata)["revision"])
    latest = harness.client.get("/api/v2/places/county:48001", params={"state": "TX", "history_limit": 1}).json()
    assert latest["history_page"]["years"] == [2024]
    assert latest["history_page"]["total"] == 2
    assert latest["history_page"]["has_more"]
    pinned = harness.client.get("/api/v2/places/county:48001", params={"state": "TX", "revision": revisions[0]}).json()
    assert pinned["history_page"]["years"] == [2020]
    assert {version["vintage"] for version in pinned["versions"]} == {"2020"}
    assert all("path" not in source for entry in latest["history"] for source in entry["sources"])


def test_result_csv_protects_formula_text_while_retaining_numeric_values():
    result = {"revision": 1, "query": {"state": "TX", "year": 2024, "office": "PRESIDENT"},
        "sources": [], "margin_definition": {}, "coverage": {}, "warnings": [],
        "geographies": [{"id": "county:48001", "name": "=SYNTHETIC()", "contest_id": "synthetic-contest",
            "total_votes": 1, "dem_margin_pp": -10, "swing_pp": None, "winner": None,
            "options": [{"id": "synthetic-option", "name": "@SYNTHETIC()", "party": "OTHER", "votes": 1, "share_pct": 100}]}]}
    content, _ = _result_export(result, "csv")
    row = next(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert row["geography_name"].startswith("'=")
    assert row["option"].startswith("'@")
    assert row["dem_margin_pp"] == "-10"


def test_place_participation_preserves_the_whole_investigation(harness):
    harness.state.payload['observations'] = [aggregate(10, date='2026-10-19'), aggregate(20)]
    harness.collect()
    response = harness.client.get('/api/v2/places/state:NC', params={**BASE_QUERY,
        'as_of': '2026-10-19', 'date_window': '2026-10-19,2026-10-19', 'mode': 'all'})
    assert response.status_code == 200
    query = response.json()['participation']['query']
    assert query['as_of'] == '2026-10-19'
    assert query['date_window'] == ['2026-10-19', '2026-10-19']
    assert query['metric'] == BASE_QUERY['metric']
    assert query['geography_ids'] == ['state:NC']
