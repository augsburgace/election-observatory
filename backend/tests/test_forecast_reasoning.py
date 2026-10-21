"""Synthetic context policies never enter production forecasts or evidence."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from observatory import forecast_reasoning as reasoning
from observatory.db import Database, Revision, Snapshot
from observatory.settings import Settings
from test_ev_history import obs, seed


def call():
    return {"race_id": "synthetic-race", "state": "NC", "state_name": "North Carolina",
        "call": {"margin_pp": 2.8, "status": "ev_informed", "range_low_pp": -15, "range_high_pp": 20},
        "evidence": {"early_vote": {"total": 1000, "date": "2026-10-20", "metric_label": "Reported ballots", "mode": "all", "source_refs": []},
            "historical_reference": {"margin_pp": 3.5, "source_refs": []},
            "geographic_tilt": {"available": True, "adjustment_pp": -.7, "matched_areas": 2, "same_stage": True, "rows": []},
            "turnout_projection": {"available": True}, "composition": [], "polls": {"count": 50}}, "sources": []}


def test_ev_only_never_reads_optional_sources_and_keeps_call(monkeypatch):
    point = call()
    monkeypatch.setattr(reasoning, "early_vote_forecasts", lambda *a, **k: {"selected": point, "calls": [point], "model_version": "test"})
    for name in ("polling_signal", "market_signal", "context_signal"):
        monkeypatch.setattr(reasoning, name, lambda *a, **k: pytest.fail("An off source was read"))
    result = reasoning.forecast_reasoning(SimpleNamespace(latest_revision=lambda: 4), state="NC", as_of="2026-10-21")
    assert result["mode"] == "ev_only"
    assert all(s["status"] == "off" for s in result["signals"].values())
    assert result["ev_call"]["call"] == point["call"]
    assert "count" not in result["ev_call"]["evidence"]["polls"]
    assert "analogue is available" in result["paragraphs"][2]["text"]


def test_enabled_context_changes_explanation_never_ev_point_or_input_object(monkeypatch):
    point = call()
    original = deepcopy(point)
    monkeypatch.setattr(reasoning, "early_vote_forecasts", lambda *a, **k: {"selected": point, "calls": [point], "model_version": "test"})
    names = ("polling_signal", "market_signal", "context_signal")
    for name in names:
        monkeypatch.setattr(reasoning, name, lambda *a, **k: {"status": "available", "summary": "Explicit synthetic external evidence", "reason": "Context only", "source_refs": []})
    db = SimpleNamespace(latest_revision=lambda: 4)
    off = reasoning.forecast_reasoning(db, state="NC", as_of="2026-10-21")
    on = reasoning.forecast_reasoning(db, state="NC", as_of="2026-10-21", include_polls=True, include_markets=True, include_context=True)
    assert off["manifest"]["ev_call_sha256"] == on["manifest"]["ev_call_sha256"]
    assert off["manifest"]["sha256"] != on["manifest"]["sha256"]
    assert len(on["paragraphs"]) == len(off["paragraphs"]) + 3
    assert on["ev_call"]["call"] == off["ev_call"]["call"] and point == original


def poll(producer="Marist", *, secondary=False, published="2026-10-21", end="2026-10-18", population="LV", question_type="vote_choice"):
    return {"study_id": producer + end, "state": "NC", "cycle": 2026, "producer": producer,
        "field_start": "2026-10-15", "field_end": end, "published_at": published, "population": population,
        "question_type": question_type, "ballot_type": "aggregator_summary" if secondary else "full_ballot",
        "estimates": [{"candidate": "Synthetic D", "party": "DEM", "value": 48}, {"candidate": "Synthetic R", "party": "REP", "value": 44}],
        "metadata": {"secondary_summary": secondary}}


def test_poll_context_deduplicates_producer_prefers_original_and_keeps_questions_separate(monkeypatch):
    db = SimpleNamespace(polls=lambda **k: [poll(secondary=True), poll("Marist Poll"), poll("Other", question_type="winner_expectation"),
        poll("Future", published="2026-10-22"), poll("RV", population="RV")])
    monkeypatch.setattr(reasoning, "_refs", lambda *a: [])
    result = reasoning.polling_signal(db, "NC", 3, "2026-10-21", 2026)
    assert result["producer_count"] == 1
    assert result["studies"][0]["producer"] == "Marist Poll"
    assert result["studies"][0]["margin_pp"] == -4
    assert len(result["exclusions"]) == 4
    assert "averages" not in result and "probability" not in result


def market(*, quote="2026-10-20T12:00:00Z", closed=False):
    return obs(2026, quote[:10], 65, metric="market_price_pct", published=quote, metadata={
        "quote_at": quote, "market_id": "synthetic-1", "active": not closed, "closed": closed,
        "party": "DEM", "outcome_label": "Synthetic D", "question": "Synthetic contract?",
        "source_url": "https://fixture.invalid/market", "native_definition": "Contract price, not vote share"})


def test_market_context_respects_revision_future_and_closure(tmp_path):
    db = Database(Settings(tmp_path))
    original = seed(db, [market()])
    closed = seed(db, [market(quote="2026-10-21T12:00:00Z", closed=True)])
    assert reasoning.market_signal(db, "NC", original, "2026-10-21", 2026)["markets"][0]["price_pct"] == 65
    assert reasoning.market_signal(db, "NC", closed, "2026-10-21", 2026)["markets"] == []
    assert reasoning.market_signal(db, "NC", closed, "2026-10-19", 2026)["markets"] == []


def test_stale_market_quote_does_not_look_current(tmp_path):
    db = Database(Settings(tmp_path))
    revision = seed(db, [market(quote="2026-10-15T12:00:00Z")])
    assert reasoning.market_signal(db, "NC", revision, "2026-10-21", 2026)["status"] == "unavailable"


def test_missing_rcp_archive_withholds_context_instead_of_breaking_publication(tmp_path):
    db = Database(Settings(tmp_path))
    with db.session() as session:
        revision = Revision(reason="Synthetic browser context fixture")
        session.add(revision)
        session.flush()
        bound = revision.id
        session.add(Snapshot(source_id="rcp-oh-senate-2026", url="https://fixture.invalid/ohio",
            sha256="a" * 64, path=str(tmp_path / "withheld-capture.json"),
            content_type="application/vnd.observatory.browser-table+json",
            retrieved_at="2026-10-20T12:00:00Z", byte_count=100, revision=bound))
        session.commit()
    result = reasoning.context_signal(db, "OH", bound, "2026-10-21", 2026)
    assert result["status"] == "unavailable"
    assert result["items"] == [] and result["source_refs"] == []
    assert "No dated additional analyst assessment" in result["summary"]


@pytest.mark.parametrize("all_closed", [False, True])
def test_collected_event_closure_invalidates_old_quotes_and_preserves_pins(tmp_path, monkeypatch, all_closed):
    """Actual parser -> append-only collector -> reasoning, without network calls."""
    import json

    from observatory import collector
    from observatory.registry import sources
    from test_external_context import document, market_fixture

    source = next(s for s in sources() if s["id"] == "polymarket-oh-senate-2026")
    _, _, payload, _ = market_fixture(tmp_path)
    if not all_closed:
        second = deepcopy(payload["markets"][0])
        second.update(id="43", slug="example-democrat", groupItemTitle="Example Democrat (D)",
                      question="Will the Democrat win the 2026 Ohio Senate election?")
        payload["markets"].append(second)
    initial = document(tmp_path, source["url"], json.dumps(payload), "initial-market-event.json",
                       captured="2026-10-20T12:00:00Z", content_type="application/json")
    current = {"document": initial}

    class FixtureFetcher:
        def __init__(self, settings, **kwargs):
            self.settings, self.documents = settings, []

        def fetch(self, url):
            assert url == source["url"]
            self.documents.append(current["document"])
            return current["document"]

        def close(self):
            pass

    monkeypatch.setattr(collector, "Fetcher", FixtureFetcher)
    db = Database(Settings(tmp_path / "database"))
    first = collector._collect_one(db, source)
    assert first["observations"] == (1 if all_closed else 2)
    original_revision = first["revision"]
    original = reasoning.market_signal(db, "OH", original_revision, "2026-10-21", 2026)
    assert len(original["markets"]) == (1 if all_closed else 2)

    payload["markets"][0].update(active=False, closed=True, outcomePrices=None)
    current["document"] = document(tmp_path, source["url"], json.dumps(payload), "closed-market-event.json",
                                    captured="2026-10-21T12:00:00Z", content_type="application/json")
    closed = collector._collect_one(db, source)
    assert closed["status"] in {"ready", "partial"}
    assert closed["observations"] == (0 if all_closed else 1)
    current_view = reasoning.market_signal(db, "OH", closed["revision"], "2026-10-21", 2026)
    assert len(current_view["markets"]) == (0 if all_closed else 1)
    assert all(m["party"] == "DEM" for m in current_view["markets"])
    assert current_view["event_status_source_refs"]
    assert reasoning.market_signal(db, "OH", original_revision, "2026-10-21", 2026)["markets"] == original["markets"]
    assert len(reasoning.market_signal(db, "OH", closed["revision"], "2026-10-20", 2026)["markets"]) == (1 if all_closed else 2)
