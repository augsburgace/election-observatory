"""Query projection and calendar guards use synthetic integration evidence only."""
from __future__ import annotations

from observatory.connectors.calendars import calendar_reference
from observatory.db import Revision, Snapshot, SourceState, poll_key
from test_evidence_workflows import BASE_QUERY, aggregate, workspace
from test_evidence_workflows import harness as harness


def test_market_price_never_creates_voting_capability_or_a_ballot_total(harness):
    from observatory.service import capabilities
    harness.state.payload["observations"] = [{**aggregate(65), "metric": "market_price_pct", "unit": "contract price percent"}]
    harness.collect()
    cap = capabilities(harness.database, "NC", as_of="2026-10-20")
    assert not cap["participation_available"] and cap["recommended_selection"] is None
    assert "market_price_pct" not in cap["metrics"]
    view = workspace(harness, as_of="2026-10-20")
    assert view["summary"]["total"] is None and "market_price_pct" not in view["coverage"]["available_metrics"]
    response = harness.client.get("/api/v1/workspace", params={**BASE_QUERY, "metric": "market_price_pct"})
    assert response.status_code == 422 and "not voting participation" in response.json()["detail"]


def test_selected_observation_scope_is_complete_and_other_modes_are_latest_state_context(harness):
    rows = [aggregate(125)] + [aggregate(1, geo=f"NC:SYNTHETIC-{index}", name=f"Synthetic place {index}", kind="county")
                             for index in range(125)]
    rows += [{**aggregate(40), "mode": "mail"},
             {**aggregate(35, date="2026-10-19"), "mode": "mail"},
             {**aggregate(85), "mode": "early_in_person"},
             {**aggregate(1, geo="NC:SYNTHETIC-0", name="Synthetic place 0", kind="county"), "mode": "mail"},
             {**aggregate(1000), "metric": "ballots_requested", "mode": "mail"}]
    harness.state.payload["observations"] = rows
    harness.collect()
    view = workspace(harness, as_of="2026-10-20")
    assert view["observation_scope"]["complete"]
    assert view["observation_scope"]["selected_count"] == 126
    assert view["observation_scope"]["context_count"] == 2
    assert len(view["observations"]) == 128
    context = [row for row in view["observations"] if row["mode"] != "all"]
    assert all(row["geography_type"] == "state" for row in context)
    assert {row["date"] for row in context} == {"2026-10-20"}
    assert "ballots_requested" in view["coverage"]["available_metrics"]
    assert all(row["metric"] == "ballots_cast" for row in view["observations"])
    export = harness.client.get("/api/v1/exports", params={**BASE_QUERY, "as_of": "2026-10-20", "format": "csv"})
    assert len(export.content.decode("utf-8-sig").splitlines()) == 127
    evidence = harness.client.get(f"/api/v1/evidence/{view['observations'][0]['id']}").json()
    assert "fixture" in evidence["observation"]["metadata"]
    assert "fixture" not in view["observations"][0]["metadata"]


def test_source_failure_invalidates_workspace_health_cache_without_erasing_counts(harness):
    harness.collect()
    before = workspace(harness, as_of="2026-10-20")
    harness.state.status = 500
    harness.collect(now="2026-10-21T16:00:00Z")
    after = workspace(harness, as_of="2026-10-20")
    assert before["summary"]["total"] == after["summary"]["total"] == 100
    assert before["sources"][0]["status"] != after["sources"][0]["status"]
    assert after["sources"][0]["status"] == "failed"


def test_verified_calendar_only_enriches_ip_with_archived_proof_in_scope(harness):
    harness.state.payload["observations"] += [{**aggregate(70), "mode": "early_in_person"}]
    first = harness.collect()
    reference = calendar_reference("NC", 2026, "early_in_person")
    archive = harness.settings.archive_dir / "synthetic-calendar"
    archive.write_text("Explicitly synthetic calendar archive for a query guard test.")
    with harness.database.session() as session:
        revision = Revision(reason="Synthetic calendar test", created_at="2026-10-20T17:00:00Z")
        session.add(revision)
        session.flush()
        session.add(SourceState(id=reference["id"], status="reference_ready", document_hash="synthetic",
                                last_changed="2026-10-20T17:00:00Z", last_checked="2026-10-20T17:00:00Z"))
        session.add(Snapshot(source_id=reference["id"], url=reference["source_url"], sha256="synthetic",
                             path=str(archive), content_type="text/html", retrieved_at="2026-10-20T17:00:00Z",
                             byte_count=archive.stat().st_size, revision=revision.id))
        session.commit()
    before = workspace(harness, mode="early_in_person", as_of="2026-10-20T16:30:00Z", alignment="days_since_open")
    assert before["calendar_references"] == []
    assert before["series"][0]["x"] is None
    after = workspace(harness, mode="early_in_person", as_of="2026-10-20T18:00:00Z", alignment="days_since_open")
    assert after["series"][0]["x"] == 5
    assert after["calendar_references"][0]["snapshot_id"]
    assert any(event["date"] == "2026-10-15" for event in after["calendar"])
    pinned = workspace(harness, mode="early_in_person", as_of="2026-10-20", revision=first["revision"])
    assert pinned["calendar_references"] == []
    all_modes = workspace(harness, as_of="2026-10-20T18:00:00Z")
    assert all("voting_open_date" not in row["metadata"] for row in all_modes["observations"] if row["mode"] == "all")


def test_narrative_poll_identity_ignores_labels_but_preserves_candidate_configuration():
    first = {"state": "GA", "cycle": 2026, "study_id": "synthetic-study", "producer": "Synthetic producer",
             "question": "Descriptive question label", "metadata": {"question_wording_exact": False},
             "estimates": [{"candidate": "Named Candidate A", "party": "D"},
                           {"candidate": "Named Candidate B", "party": "R"}, {"candidate": "Someone else"}]}
    relabeled = {**first, "question": "Improved descriptive question label",
                 "estimates": first["estimates"][:2] + [{"candidate": "Don’t know/Refused"}]}
    alternate = {**first, "estimates": [{"candidate": "Different Candidate", "party": "D"}] + first["estimates"][1:]}
    assert poll_key(first) == poll_key(relabeled)
    assert poll_key(first) != poll_key(alternate)
