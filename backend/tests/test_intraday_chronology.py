"""Date precision must not introduce intraday look-ahead from later archives.

All numerical records below are explicit test fixtures, never installed live.
"""
from __future__ import annotations

from datetime import datetime

from observatory.analytics import historical_analysis, poll_analysis
from observatory.analytics.common import available_at
from observatory.db import Database, ObservationRecord, PollRecord, Revision, Snapshot, observation_key
from observatory.settings import Settings


def observation(value=100, **changes):
    return {"state": "NC", "cycle": 2026, "election_date": "2026-11-03", "date": "2026-10-20",
        "metric": "ballots_cast", "value": value, "geography_id": "NC", "geography_name": "North Carolina",
        "geography_type": "state", "mode": "all", "time_basis": "reported", "published_at": "2026-10-20",
        "observed_at": "2026-10-20T18:00:00Z", "metadata": {}, **changes}


def poll(**changes):
    return {"study_id": "synthetic-intraday-study", "state": "NC", "cycle": 2026,
        "producer": "Explicit synthetic chronology fixture", "publisher": "Fixture", "population": "LV",
        "field_start": "2026-10-17", "field_end": "2026-10-18", "published_at": "2026-10-20",
        "observed_at": "2026-10-20T18:00:00Z", "question_type": "vote_choice", "ballot_type": "full_ballot",
        "question": "Synthetic choice?", "source_url": "https://fixture.invalid/survey",
        "estimates": [{"candidate": "Example A", "value": 48}, {"candidate": "Example B", "value": 45}],
        "metadata": {}, **changes}


def test_date_only_historical_publication_is_known_by_end_of_new_york_day():
    record = observation(published_at="2022-10-25", observed_at="2026-10-20T18:00:00Z")
    assert available_at(record) == datetime.fromisoformat("2022-10-26T03:59:59.999999+00:00")
    assert available_at({**record, "observed_at": None}) == available_at(record)


def test_same_day_archive_proves_hour_without_backdating_midnight():
    record = observation()
    assert available_at(record) == datetime.fromisoformat("2026-10-20T18:00:00+00:00")
    early = historical_analysis([record], state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20T17:00:00Z")
    later = historical_analysis([record], state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20T19:00:00Z")
    daily = historical_analysis([record], state="NC", cycle=2026, metric="ballots_cast", as_of="2026-10-20")
    assert early["latest"] is None
    assert later["latest"]["value"] == daily["latest"]["value"] == 100


def test_same_day_is_evaluated_in_research_timezone_not_utc():
    assert available_at(observation(observed_at="2026-10-21T02:00:00Z")) == datetime.fromisoformat("2026-10-21T02:00:00+00:00")
    # Retrieval the next New York day cannot prove a time within the previous day.
    assert available_at(observation(observed_at="2026-10-21T06:00:00Z")) == datetime.fromisoformat("2026-10-21T03:59:59.999999+00:00")


def test_documented_publication_timestamp_keeps_its_precision():
    assert available_at(observation(published_at="2026-10-20T10:00:00-04:00")) == datetime.fromisoformat("2026-10-20T14:00:00+00:00")


def test_revised_bytes_need_revision_publication_or_their_first_archive():
    correction = observation(120, published_at="2026-10-19", observed_at="2026-10-20T20:00:00Z",
        metadata={"is_revision": True, "revision_of": 1})
    assert available_at(correction) == datetime.fromisoformat("2026-10-20T20:00:00+00:00")
    date_proof = {**correction, "metadata": {"is_revision": True, "revision_published_at": "2026-10-20"}}
    assert available_at(date_proof) == available_at(correction)
    exact_proof = {**correction, "metadata": {"revision_of": 1, "revision_published_at": "2026-10-20T18:00:00Z"}}
    assert available_at(exact_proof) == datetime.fromisoformat("2026-10-20T18:00:00+00:00")


def test_original_poll_date_does_not_establish_an_earlier_release_hour():
    before = poll_analysis([poll()], state="NC", cycle=2026, as_of="2026-10-20T17:00:00Z")
    after = poll_analysis([poll()], state="NC", cycle=2026, as_of="2026-10-20T19:00:00Z")
    daily = poll_analysis([poll()], state="NC", cycle=2026, as_of="2026-10-20")
    assert before["producer_count"] == 0
    assert after["producer_count"] == daily["producer_count"] == 1


def test_database_observations_catalog_polls_and_revision_pin_share_availability(tmp_path):
    database = Database(Settings(tmp_path / "chronology"))
    with database.session() as session:
        first = Revision(reason="Synthetic original", created_at="2026-10-20T18:00:00Z")
        session.add(first)
        session.flush()
        snapshot = Snapshot(source_id="synthetic-chronology", url="https://fixture.invalid/source", sha256="synthetic",
            path=str(tmp_path / "fixture"), content_type="text/plain", retrieved_at="2026-10-20T18:00:00Z",
            byte_count=1, revision=first.id)
        session.add(snapshot)
        session.flush()
        original = observation()
        session.add(ObservationRecord(logical_key=observation_key(original, "synthetic-chronology"),
            source_id="synthetic-chronology", snapshot_id=snapshot.id, revision=first.id,
            observed_at=original["observed_at"], state="NC", cycle=2026, date=original["date"],
            metric=original["metric"], value=original["value"], payload=original))
        session.add(PollRecord(study_id="synthetic-intraday-study", source_id="synthetic-chronology",
            snapshot_id=snapshot.id, revision=first.id, observed_at="2026-10-20T18:00:00Z", state="NC", cycle=2026, payload=poll()))
        second = Revision(reason="Synthetic correction", created_at="2026-10-20T20:00:00Z")
        session.add(second)
        session.flush()
        corrected = observation(120, metadata={"revision_of": 1}, observed_at="2026-10-20T20:00:00Z")
        session.add(ObservationRecord(logical_key=observation_key(corrected, "synthetic-chronology"),
            source_id="synthetic-chronology", snapshot_id=snapshot.id, revision=second.id,
            observed_at=corrected["observed_at"], state="NC", cycle=2026, date=corrected["date"],
            metric=corrected["metric"], value=corrected["value"], payload=corrected))
        session.commit()
        original_revision, latest_revision = first.id, second.id
    before, after = "2026-10-20T17:00:00Z", "2026-10-20T19:00:00Z"
    assert database.observations(state="NC", cutoff=before) == []
    assert database.observation_catalog(state="NC", revision=latest_revision, cutoff=before) == []
    assert database.polls(state="NC", cutoff=before) == []
    assert [r["value"] for r in database.observations(state="NC", cutoff=after)] == [100]
    assert len(database.observation_catalog(state="NC", revision=latest_revision, cutoff=after)) == 1
    assert len(database.polls(state="NC", cutoff=after)) == 1
    assert [r["value"] for r in database.observations(state="NC", cutoff="2026-10-20")] == [120]
    assert [r["value"] for r in database.observations(state="NC", cutoff="2026-10-20", revision=original_revision)] == [100]
    database.engine.dispose()
