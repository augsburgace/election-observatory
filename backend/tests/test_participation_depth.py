from types import SimpleNamespace

import pytest
from observatory.connectors import hawaii
from observatory.connectors.oregon import parse_pages
from observatory.connectors.uf_election_lab import parse_row, semantics
from observatory.db import Database, ObservationRecord, Revision, Snapshot
from observatory.participation_validation import apply_definition_validations
from observatory.settings import Settings


def test_request_proxies_and_issued_fields_never_become_requests():
    for state in ("TX", "DE", "UT", "DC"):
        assert semantics(state, "request") is None
    assert semantics("AZ", "request")[:2] == ("ballots_issued", "mail")
    assert semantics("TN", "voted")[:2] == ("ballots_cast", "early_in_person")
    assert semantics("OH", "inperson")[2]["mode_classification"]


def test_tennessee_total_is_not_an_all_method_total():
    d = SimpleNamespace(url="https://example.org/data", sha256="a", retrieved_at="2026-10-21T05:00:00+00:00")
    row = {
        "state": "Tennessee",
        "last_update": "10/20/2026",
        "voted_all": "100",
        "inperson_all": "100",
        "accept_all": "0",
        "request_all": "0",
    }
    obs = parse_row(row, {"state": "TN"}, d, row)
    assert len(obs) == 1 and obs[0].mode == "early_in_person"


def test_hawaii_checks_native_arithmetic_and_explicit_zero(tmp_path):
    cells = [
        "County",
        "ELECT Sent",
        "ELECT Voted",
        "Invalid",
        "Early",
        "Mail sent",
        "Mail voted",
        "Invalid",
        "VOTED",
        "TOTAL",
    ]
    rows = [
        ["Hawaii", 1, 1, 0, 0, 2, 1, 0, 2, 3],
        ["Maui", 1, 1, 0, 0, 2, 1, 0, 2, 3],
        ["Kauai", 1, 1, 0, 0, 2, 1, 0, 2, 3],
        ["Honolulu", 1, 1, 0, 0, 2, 1, 0, 2, 3],
        ["", 4, 4, 0, 0, 8, 4, 0, 8, 12],
    ]
    html = (
        "Last Updated on October 20, 2026<table>"
        + "".join(
            "<tr>" + "".join("<td>" + str(c) + "</td>" for c in row) + "</tr>" for row in [cells] + rows
        )
        + "</table>"
    )
    d = SimpleNamespace(
        text=html,
        url="https://elections.hawaii.gov/source",
        sha256="a",
        retrieved_at="2026-10-21T00:00:00+00:00",
    )
    fetcher = SimpleNamespace(fetch=lambda url: d)
    result = hawaii.collect({"state": "HI", "url": d.url}, fetcher)
    assert len(result.observations) == 40
    assert any(o.value == 0 and o.metadata["explicit_reported_zero"] for o in result.observations)
    d.text = html.replace("<td>8</td><td>12</td>", "<td>9</td><td>12</td>")
    with pytest.raises(ValueError, match="arithmetic"):
        hawaii.collect({"state": "HI", "url": d.url}, fetcher)


def test_oregon_rejects_unreconciled_or_undated_denominators():
    d = SimpleNamespace(
        url="https://example.gov/report.pdf", sha256="a", retrieved_at="2026-10-21T00:00:00+00:00"
    )
    with pytest.raises(ValueError, match="dates"):
        parse_pages(["Report Generated: 10/20/2026"], {"state": "OR"}, d)


def test_source_scoped_quality_does_not_hide_an_official_measure(tmp_path):
    db = Database(Settings(tmp_path))
    apply_definition_validations(db)
    with db.session() as s:
        rev = Revision(reason="test")
        s.add(rev)
        s.flush()
        snapshot = Snapshot(
            source_id="fixture",
            url="https://example.gov/fixture",
            sha256="a",
            path="/fixture",
            content_type="text/csv",
            retrieved_at="2026-10-20T23:00:00+00:00",
            byte_count=1,
            revision=rev.id,
        )
        s.add(snapshot)
        s.flush()
        for source in ("uf-fallback-az", "az-official"):
            payload = {
                "state": "AZ",
                "cycle": 2026,
                "election_date": "2026-11-03",
                "date": "2026-10-20",
                "metric": "ballots_requested",
                "value": 10,
                "geography_id": "AZ",
                "geography_name": "Arizona",
                "geography_type": "state",
                "mode": "mail",
                "unit": "requests",
                "time_basis": "reported",
                "published_at": "2026-10-20",
                "metadata": {},
            }
            s.add(
                ObservationRecord(
                    logical_key=source,
                    source_id=source,
                    snapshot_id=snapshot.id,
                    revision=rev.id,
                    observed_at="2026-10-20T23:00:00+00:00",
                    state="AZ",
                    cycle=2026,
                    date="2026-10-20",
                    metric="ballots_requested",
                    value=10,
                    payload=payload,
                )
            )
        s.commit()
    records = db.observations(state="AZ")
    assert (
        next(r for r in records if r["source_id"] == "uf-fallback-az")["validation"]["status"]
        == "quarantined"
    )
    assert "validation" not in next(r for r in records if r["source_id"] == "az-official")
    catalog = db.observation_catalog(revision=db.latest_revision(), state="AZ", cutoff="2100-01-01")
    assert {r["source_id"] for r in catalog} == {"az-official"}


def test_new_investigation_prefers_original_source_over_proxy_metric():
    from observatory.service import _recommended_selection

    common = {"mode": "all", "time_basis": "reported", "category_dimension": None}
    choice = _recommended_selection([
        {**common, "source_id": "uf-fallback-hi", "metric": "ballots_cast"},
        {**common, "source_id": "hi-official-receipts-2026", "metric": "ballots_returned"},
    ])
    assert choice["metric"] == "ballots_returned"
