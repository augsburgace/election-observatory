"""Regression checks for geography, chronology, finite values, and linked research.

Numerical records below are synthetic test evidence and never seed the app.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from observatory.analytics import historical_analysis
from observatory.connectors import maine
from observatory.db import Database, ObservationRecord, Revision, Snapshot, observation_key
from observatory.domain import ResearchQuery
from observatory.geography import canonicalize_observation, enrich_geojson, normalize_selections
from observatory.service import _geographic_research, _recommended_selection, bootstrap
from observatory.settings import Settings


def row(value=100, **changes):
    return {"state": "NC", "cycle": 2026, "election_date": "2026-11-03", "date": "2026-10-20",
            "metric": "ballots_cast", "value": value, "geography_id": "NC:NEW HANOVER",
            "geography_name": "New Hanover", "geography_type": "county", "mode": "all",
            "time_basis": "reported", "published_at": "2026-10-20T12:00:00Z",
            "observed_at": "2026-10-20T13:00:00Z", "source_id": "synthetic-official", "metadata": {}, **changes}


@pytest.mark.parametrize(("state", "name", "geoid"), [
    ("NC", "New Hanover", "37129"), ("IA", "O’Brien", "19141"),
    ("IA", "Cerro Gordo", "19033"), ("IA", "Buena Vista", "19021"),
    ("IA", "Palo Alto", "19147"), ("IA", "Van Buren", "19177"), ("TX", "Harris", "48201"),
])
def test_reviewed_county_joins_preserve_legacy_identity(state, name, geoid):
    record = row(state=state, geography_id=f"{state}:{name.upper()}", geography_name=name)
    joined = canonicalize_observation(record)
    assert joined["canonical_id"] == f"county:{geoid}"
    assert joined["geography_id"] == record["geography_id"]
    assert joined["geography_join"]["boundary_vintage"] == "2024"
    assert normalize_selections(state, [record["geography_id"], f"county:{geoid}"]) == [f"county:{geoid}"]


def test_no_county_geometry_is_invented_for_a_native_reporting_area():
    native = canonicalize_observation(row(state="AK", geography_type="district", geography_id="AK:DISTRICT 1",
        geography_name="District 1", source_id="ak-official", metadata={"boundary_vintage": "2026"}))
    assert native["canonical_id"] == "native:ak-official:district:2026:AK%3ADISTRICT%201"
    assert native["geography_join"]["status"] == "native_geography"
    unmatched = canonicalize_observation(row(geography_id="NC:SYNTHETIC", geography_name="Synthetic County"))
    assert unmatched["canonical_id"] is None
    assert unmatched["geography_join"]["status"] == "unmatched"
    municipal = canonicalize_observation(row(state="ME", geography_type="municipality", geography_name="Hancock"))
    assert municipal["geography_join"]["status"] == "native_geography"


def test_enriched_boundary_keeps_legacy_id():
    feature = {"type": "FeatureCollection", "features": [{"id": "TX:HARRIS", "properties": {"GEOID": "48201", "postal": "TX"}, "geometry": None}]}
    result = enrich_geojson(feature)
    assert result["features"][0]["id"] == "TX:HARRIS"
    assert result["features"][0]["properties"]["canonical_id"] == "county:48201"


def test_canonical_selection_accepts_old_alias_without_double_counting_sources():
    records = [row(), row(geography_id="NC:NEWHANOVER", source_id="synthetic-secondary",
        metadata={"source_priority": 300})]
    result = historical_analysis(records, state="NC", cycle=2026, metric="ballots_cast",
        geography_ids=["county:37129"], as_of="2026-10-20")
    assert result["latest"]["value"] == 100
    assert result["latest"]["geography_count"] == 1


def test_nonfinite_denominator_and_invalid_date_do_not_enter_analysis():
    records = [row(denominator=float("inf")), row(3, date="not-a-date")]
    result = historical_analysis(records, state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    assert result["latest"]["rate"] is None
    assert "Malformed observations were excluded." in result["warnings"]


def test_per_place_series_and_concentration_are_individually_labeled():
    records = [row(20, date="2026-10-19", published_at="2026-10-19"), row(30),
               row(70, geography_id="NC:WAKE", geography_name="Wake")]
    records = [canonicalize_observation(item) for item in records]
    result = _geographic_research(records, ResearchQuery(), 100, "2026-10-20")
    assert {place["name"] for place in result["places"]} == {"New Hanover", "Wake"}
    assert result["rankings"][0]["name"] == "Wake"
    assert result["rankings"][0]["share"] == .7
    assert result["concentration"][-1]["cumulative_share"] == 1
    assert result["waterfall"][0]["change"] == 10
    assert len(next(p for p in result["places"] if p["name"] == "New Hanover")["series"]) == 2


def test_available_default_is_a_suggestion_not_a_query_rewrite():
    assert _recommended_selection([{"metric": "ballots_accepted", "mode": "mail", "time_basis": "reported"}])["mode"] == "mail"
    assert ResearchQuery().metric == "ballots_cast"


def test_quality_revision_quarantines_new_views_and_retains_pinned_originals(tmp_path):
    database = Database(Settings(tmp_path / "quality"))
    with database.session() as session:
        rev = Revision(reason="Synthetic chronology test", created_at="2026-10-20T12:00:00Z")
        session.add(rev)
        session.flush()
        snapshot = Snapshot(source_id="synthetic-maine", url="https://fixture.invalid/maine", sha256="synthetic",
            path=str(tmp_path / "synthetic"), content_type="text/plain", retrieved_at="2026-10-20T12:00:00Z", byte_count=1, revision=rev.id)
        session.add(snapshot)
        session.flush()
        payload = row(state="ME", geography_id="ME", geography_name="Maine", geography_type="state",
            metric="ballot_records_requested", time_basis="reconstructed", date="2024-05-01")
        session.add(ObservationRecord(logical_key=observation_key(payload, "synthetic-maine"), source_id="synthetic-maine",
            snapshot_id=snapshot.id, revision=rev.id, observed_at="2026-10-20T12:00:00Z", state="ME", cycle=2026,
            date=payload["date"], metric=payload["metric"], value=payload["value"], payload=payload))
        session.commit()
        old_revision = rev.id
    decision = database.apply_quality_validations()
    assert database.apply_quality_validations()["revision"] == decision["revision"]
    old = database.observations(revision=old_revision)
    assert old[0]["value"] == 100
    assert old[0]["validation"]["status"] == "historical_warning"
    latest = database.observations()
    assert latest[0]["validation"]["status"] == "quarantined"
    result = historical_analysis(latest, state="ME", cycle=2026, metric="ballot_records_requested",
        time_basis="reconstructed", as_of="2099-01-01")
    assert result["status"] == "no_observations"
    replay = historical_analysis(old, state="ME", cycle=2026, metric="ballot_records_requested",
        time_basis="reconstructed", as_of="2026-10-20")
    assert replay["latest"]["value"] == 100
    assert any("standing" in warning for warning in replay["warnings"])
    assert len(bootstrap(database)["states"]) == 50
    database.engine.dispose()


def test_maine_standing_request_dates_never_become_voting_trajectories(tmp_path):
    path = tmp_path / "explicitly-synthetic-maine.txt"
    path.write_text("RES MUNICIPALITY|Req Date|Issued Date|Rec Date|P|DUP|Status\n"
        "Synthetic Town|01/01/2022|10/10/2026|10/15/2026|U||\n"
        "Synthetic Town|10/01/2026|10/30/2026||D|Y|REJ\n")
    index = SimpleNamespace(url="https://fixture.invalid/index", text='<a href="/2026-as%20of%2010-20-26.txt">Statewide Absentee Voter Data File (Text)</a>')
    document = SimpleNamespace(url="https://fixture.invalid/2026-as%20of%2010-20-26.txt", path=str(path),
        sha256="synthetic", retrieved_at="2026-10-20T12:00:00Z")
    fetcher = SimpleNamespace(fetch=lambda url: index if url.endswith("index") else document)
    batch = maine.collect({"state": "ME", "cycle": 2026, "url": index.url}, fetcher)
    assert not any(item.metric == "ballot_records_requested" and item.time_basis == "reconstructed" for item in batch.observations)
    assert all(item.date <= "2026-10-20" for item in batch.observations)
    snapshot = next(item for item in batch.observations if item.geography_type == "state" and item.metric == "ballot_records_requested" and not item.category)
    assert snapshot.value == 2
    assert snapshot.metadata["standing_request_dates"] == 1
    assert snapshot.metadata["anomalous_date_fields_excluded_from_timeline"] == 1


def test_date_brush_filters_all_series_and_pins_the_same_cutoff(tmp_path):
    from observatory.service import workspace
    database = Database(Settings(tmp_path / "brush"))
    records = []
    for date, value in (("2026-10-18", 10), ("2026-10-19", 20), ("2026-10-20", 30)):
        records.extend([row(value, date=date, published_at=date, geography_id="NC", geography_name="North Carolina", geography_type="state"),
                        row(value, date=date, published_at=date)])
    with database.session() as session:
        revision = Revision(reason="Synthetic brush test", created_at="2026-10-20T12:00:00Z")
        session.add(revision)
        session.flush()
        snapshot = Snapshot(source_id="synthetic-brush", url="https://fixture.invalid/brush", sha256="synthetic",
            path=str(tmp_path / "synthetic"), content_type="text/plain", retrieved_at="2026-10-20T12:00:00Z", byte_count=1, revision=revision.id)
        session.add(snapshot)
        session.flush()
        for record in records:
            session.add(ObservationRecord(logical_key=observation_key(record, "synthetic-brush"), source_id="synthetic-brush",
                snapshot_id=snapshot.id, revision=revision.id, observed_at="2026-10-20T12:00:00Z", state="NC", cycle=2026,
                date=record["date"], metric=record["metric"], value=record["value"], payload=record))
        session.commit()
    query = ResearchQuery(date_window=("2026-10-19", "2026-10-19"))
    view = workspace(database, query)
    assert view["summary"]["total"] == 20
    assert {point["date"] for point in view["series"]} == {"2026-10-19"}
    assert {point["date"] for point in view["historical"]["current_series"]} == {"2026-10-19"}
    assert {point["date"] for point in view["geographic_research"]["places"][0]["series"]} == {"2026-10-19"}
    assert {record["date"] for record in view["observations"]} == {"2026-10-19"}
    assert view["query"]["date_window"] == ("2026-10-19", "2026-10-19")
    database.engine.dispose()


def test_virginia_city_county_name_collision_requires_an_identifier():
    ambiguous = canonicalize_observation(row(state="VA", geography_id="VA:RICHMOND", geography_name="Richmond"))
    assert ambiguous["canonical_id"] is None
    county = canonicalize_observation(row(state="VA", geography_id="VA:RICHMOND", geography_name="Richmond County"))
    city = canonicalize_observation(row(state="VA", geography_id="VA:RICHMOND", geography_name="Richmond city"))
    assert county["canonical_id"] == "county:51159"
    assert city["canonical_id"] == "county:51760"
