"""Synthetic chronology fixtures; never installed in the local evidence store."""
from __future__ import annotations

import pytest
from observatory.db import Database, ObservationRecord, Revision, Snapshot, observation_key
from observatory.domain import Observation
from observatory.ev_history import stage_history
from observatory.registry import ELECTION_DATES, source_covers_state
from observatory.settings import Settings
from sqlalchemy import select


def seed(database, rows, observed="2026-10-21T12:00:00Z"):
    with database.session() as session:
        rev = Revision(reason="Explicitly synthetic chronology fixture", created_at=observed)
        session.add(rev)
        session.flush()
        snap = Snapshot(source_id="synthetic", url="https://fixture.invalid/aggregate", sha256="0" * 64,
            path="test-only", content_type="application/json", retrieved_at=observed, byte_count=1, revision=rev.id)
        session.add(snap)
        session.flush()
        for row in rows:
            value = Observation(**row).model_dump()
            session.add(ObservationRecord(logical_key=observation_key(value, "synthetic"), source_id="synthetic", snapshot_id=snap.id,
                revision=rev.id, observed_at=observed, state=value["state"], cycle=value["cycle"], date=value["date"],
                metric=value["metric"], value=value["value"], payload=value))
        session.commit()
        return rev.id


def obs(cycle, date, value, *, basis="reported", published=None, metric="ballots_cast", metadata=None, denominator=None):
    return {"state": "NC", "cycle": cycle, "election_date": ELECTION_DATES[cycle], "date": date,
        "metric": metric, "mode": "all", "value": value, "geography_id": "NC", "geography_name": "North Carolina",
        "geography_type": "state", "time_basis": basis, "published_at": published or date + "T12:00:00Z",
        "denominator": denominator, "metadata": metadata or {}}


@pytest.fixture
def db(tmp_path):
    return Database(Settings(tmp_path))


def test_actual_same_stage_and_stale_reports_are_distinct(db):
    revision = seed(db, [obs(2026, "2026-10-21", 300), obs(2022, "2022-10-26", 200, basis="reconstructed"),
        obs(2018, "2018-10-23", 100, basis="reconstructed")])
    view = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2018, 2022))
    old, recent = view["cycles"]
    assert recent["same_stage"] and recent["pace_ratio"] == 1.5
    assert old["target_date"] == "2018-10-24" and old["age_days"] == 1
    assert not old["same_stage"] and old["pace_ratio"] is None
    assert old["value"] == 100 and len(old["trajectory"]) == 1


def test_presidential_snapshot_is_context_even_at_an_exact_midterm_stage(db):
    revision = seed(db, [obs(2026, "2026-10-21", 300), obs(2024, "2024-10-23", 900, basis="reconstructed")])
    prior = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2024,))["cycles"][0]
    assert prior["value"] == 900 and prior["aligned_report"]
    assert not prior["same_election_type"] and not prior["same_stage"]
    assert prior["pace_ratio"] is None and prior["matched"]["ratio"] is None
    assert "Different election environment" in prior["reason"]


def test_strict_cutoff_selects_earlier_available_version_and_retrospective_is_labeled(db):
    seed(db, [obs(2026, "2026-10-21", 300), obs(2022, "2022-10-26", 100)], observed="2022-10-26T14:00:00Z")
    revision = seed(db, [obs(2022, "2022-10-26", 999, published="2022-10-28T12:00:00Z")])
    strict = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2022,), history_basis="reported")
    assert strict["cycles"][0]["value"] == 100
    retrospective = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2022,))
    assert retrospective["cycles"][0]["value"] == 999
    assert "Later-retained" in retrospective["cycles"][0]["chronology"]["description"]


def test_missing_opening_calendar_does_not_guess_from_first_vote(db):
    revision = seed(db, [obs(2026, "2026-10-21", 300), obs(2022, "2022-10-26", 200, basis="reconstructed")])
    view = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2022,), alignment="days_since_opening")
    assert view["current"]["days_since_opening"] is None
    assert not view["cycles"][0]["alignment_available"]
    assert view["cycles"][0]["target_date"] is None


def test_final_acceptance_cohort_is_not_an_exact_reported_stage(db):
    revision = seed(db, [obs(2026, "2026-10-21", 300), obs(2022, "2022-10-26", 200,
        basis="reconstructed", metadata={"final_status_cohort": True})])
    historical = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2022,))["cycles"][0]
    assert historical["value"] == 200 and not historical["same_stage"]
    assert historical["pace_ratio"] is None and "Final-status" in historical["reason"]


def test_final_turnout_is_a_prior_reference_and_scenarios_respect_observed_floor(db):
    revision = seed(db, [obs(2026, "2026-10-21", 950), obs(2022, "2022-11-08", 1000, metric="final_turnout", basis="final"),
        obs(2026, "2026-11-03", 99999, metric="final_turnout", basis="final")])
    turnout = stage_history(db, revision=revision, as_of="2026-10-21")["turnout"]
    assert [r["cycle"] for r in turnout["historical_final_participation"]] == [2022]
    low, same, high = turnout["scenarios"]
    assert not low["consistent"] and low["remaining_participation"] is None
    assert same["remaining_participation"] == 50 and high["remaining_participation"] == 150
    assert turnout["registration_denominator"] is None


def test_registration_rate_requires_date_definition_and_positive_denominator(db):
    revision = seed(db, [obs(2026, "2026-10-21", 300, denominator=1000)])
    assert stage_history(db, revision=revision, as_of="2026-10-21")["turnout"]["registration_denominator"] is None
    revision = seed(db, [obs(2026, "2026-10-21", 300, denominator=1000,
        metadata={"denominator_date": "2026-10-01", "denominator_definition": "All registered voters"})])
    rate = stage_history(db, revision=revision, as_of="2026-10-21")["turnout"]["registration_denominator"]
    assert rate["participation_rate_pct"] == 30 and rate["date"] == "2026-10-01"


def test_pinned_revision_excludes_later_revisions_and_unsupported_inputs_fail(db):
    first = seed(db, [obs(2026, "2026-10-21", 300)])
    seed(db, [obs(2026, "2026-10-21", 900)])
    assert stage_history(db, revision=first, as_of="2026-10-21")["current"]["value"] == 300
    with pytest.raises(ValueError):
        stage_history(db, revision=999)
    with pytest.raises(ValueError):
        stage_history(db, alignment="invented_opening")


def test_national_sources_are_one_inventory_record_with_explicit_state_scope():
    assert source_covers_state({"state": "US", "scope": "national"}, "OH")
    assert not source_covers_state({"state": "NC"}, "OH")


def test_later_manual_correction_does_not_rewrite_strict_stage(db):
    from observatory.db import Correction
    revision = seed(db, [obs(2026, "2026-10-21", 300), obs(2022, "2022-10-26", 100)])
    with db.session() as session:
        record = session.scalar(select(ObservationRecord).where(ObservationRecord.cycle == 2022))
        session.add(Correction(observation_id=record.id, revision=revision, original=100, replacement=999,
                               reason="Synthetic later correction", created_at="2026-10-21T12:00:00Z"))
        session.commit()
    strict = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2022,), history_basis="reported")
    assert strict["cycles"][0]["value"] == 100
    retrospective = stage_history(db, revision=revision, as_of="2026-10-21", baseline_cycles=(2022,))
    assert retrospective["cycles"][0]["value"] == 999


def test_old_cutoff_cannot_acquire_later_final_turnout_references(db):
    revision = seed(db, [obs(2018, "2018-11-06", 1000, metric="final_turnout", basis="final"),
        obs(2020, "2020-11-03", 2000, metric="final_turnout", basis="final"),
        obs(2022, "2022-11-08", 3000, metric="final_turnout", basis="final")])
    turnout = stage_history(db, cycle=2026, revision=revision, as_of="2020-10-21")["turnout"]
    assert [row["cycle"] for row in turnout["historical_final_participation"]] == [2018]
    assert all(row["reference_cycle"] == 2018 for row in turnout["scenarios"])


def test_returned_receipts_are_not_subtracted_as_counted_participation(db):
    revision = seed(db, [obs(2026, "2026-10-21", 1050, metric="ballots_returned"),
        obs(2022, "2022-11-08", 1000, metric="final_turnout", basis="final")])
    turnout = stage_history(db, revision=revision, as_of="2026-10-21", metric="ballots_returned")["turnout"]
    for scenario in turnout["scenarios"]:
        assert scenario["reported_measure_value"] == 1050
        assert scenario["unaccepted_receipt_measure"]
        assert not scenario["counted_participation_floor_applied"]
        assert scenario["remaining_participation"] is None
        assert scenario["reported_early_participation"] is None
