"""Optional-source identity, chronology and units; fixtures never seed real data."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from observatory.connectors import external_context
from observatory.domain import FetchedDocument


class PublicFixtureFetcher:
    def __init__(self, settings, *, offline=False):
        self.settings, self.offline, self.documents = settings, offline, []
        self.fixture_documents = {}

    def fetch(self, url):
        if url not in self.fixture_documents:
            raise ValueError("No archived fixture response")
        doc = self.fixture_documents[url]
        self.documents.append(doc)
        return doc

    def close(self):
        pass


def fixture_fetcher(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    return PublicFixtureFetcher(SimpleNamespace(data_dir=tmp_path, archive_dir=archive))


def document(tmp_path, url, content, name="fixture.txt", *, captured="2026-10-21T12:00:00Z", content_type="text/html"):
    data = content.encode()
    path = tmp_path / name
    path.write_bytes(data)
    return FetchedDocument(url=url, sha256=hashlib.sha256(data).hexdigest(), path=str(path),
                           retrieved_at=captured, byte_count=len(data), content_type=content_type, text=content)


def coefficient_fixture(tmp_path):
    source = {"state": "KS", "state_name": "Kansas", "cycle": 2026,
              "url": "https://fixture.invalid/ks/", "release_url": "https://fixture.invalid/"}
    html = """<h1>Kansas U.S. Senate</h1><p>October 10-12, 2026. Sample 600 likely voters. MoE ±4.0%</p>
    <p>If the election for U.S. Senate were held today, for whom would you vote?</p>
    <div class="cand"><span class="cand-name">Example Republican</span><span class="cand-party">Republican</span><span class="cand-pct">47%</span></div>
    <div class="cand"><span class="cand-name">Example Democrat</span><span class="cand-party">Democrat</span><span class="cand-pct">45%</span></div>
    <div class="cand"><span class="cand-name">Undecided</span><span class="cand-pct">8%</span></div>"""
    release = '<a href="/ks">Kansas October 15, 2026</a>'
    fetcher = fixture_fetcher(tmp_path)
    fetcher.fixture_documents = {source["url"]: document(tmp_path, source["url"], html, "survey.html"),
        source["release_url"]: document(tmp_path, source["release_url"], release, "index.html")}
    return source, fetcher


def test_original_poll_keeps_complete_responses_and_explicit_publication_evidence(tmp_path):
    source, fetcher = coefficient_fixture(tmp_path)
    poll = external_context.coefficient(source, fetcher).polls[0]
    assert poll.published_at == "2026-10-15"
    assert poll.field_end == "2026-10-12"
    assert [e["value"] for e in poll.estimates] == [47, 45, 8]
    assert poll.estimates[2]["party"] is None
    assert poll.metadata["publication_date_verified"] is True
    assert poll.margin_of_error == 4


def test_missing_undecided_category_does_not_become_a_reallocated_two_party_poll(tmp_path):
    source, fetcher = coefficient_fixture(tmp_path)
    doc = fetcher.fixture_documents[source["url"]]
    doc.text = doc.text[:doc.text.index('<div class="cand"><span class="cand-name">Undecided')]
    with pytest.raises(ValueError, match="Complete original response"):
        external_context.coefficient(source, fetcher)


def test_original_poll_cannot_claim_publication_before_fieldwork(tmp_path):
    source, fetcher = coefficient_fixture(tmp_path)
    fetcher.fixture_documents[source["release_url"]].text = '<a href="/ks">Kansas October 11, 2026</a>'
    with pytest.raises(ValueError, match="predates fieldwork"):
        external_context.coefficient(source, fetcher)


def test_original_poll_future_release_is_not_current_evidence(tmp_path):
    source, fetcher = coefficient_fixture(tmp_path)
    fetcher.fixture_documents[source["release_url"]].text = '<a href="/ks">Kansas October 25, 2026</a>'
    with pytest.raises(ValueError, match="future|retriev|capture", check=lambda e: bool(str(e))):
        external_context.coefficient(source, fetcher)


def rcp_fixture(tmp_path, *, rows=None, state="OH", title="Ohio 2026 Senate"):
    url = "https://www.realclearpolling.com/polls/senate/general/2026/ohio/example"
    source = {"state": state, "state_name": "Ohio", "cycle": 2026, "url": url,
              "parties": {"Example Republican": "REP", "Example Democrat": "DEM"}}
    header = {"cells": ["Pollster", "Date", "Sample", "MoE", "Example Republican", "Example Democrat", "Spread"]}
    rows = rows if rows is not None else [{"cells": ["Example Institute", "10/10 - 10/12", "600 LV", "4", "48", "45", "R+3"]}]
    payload = {"schema": "rcp-browser-tables-v1", "url": url, "title": title,
               "captured_at": "2026-10-21T12:00:00Z", "capture_method": "Explicit unit-only fixture, not product data", "tables": [[header, *rows]]}
    path = tmp_path / "source-captures" / "rcp" / f"{state}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))
    return source, fixture_fetcher(tmp_path), payload, path


def test_secondary_poll_retains_capture_cutoff_and_never_imputes_undecideds(tmp_path):
    source, fetcher, _, _ = rcp_fixture(tmp_path)
    poll = external_context.rcp_capture(source, fetcher).polls[0]
    assert poll.published_at == "2026-10-21T12:00:00Z"
    assert poll.ballot_type == "aggregator_summary"
    assert poll.metadata["secondary_summary"] is True
    assert [e["value"] for e in poll.estimates] == [48, 45]
    assert sum(e["value"] for e in poll.estimates) == 93
    assert not poll.metadata["publication_date_verified"]


def test_rcp_release_order_need_not_be_fieldwork_end_order(tmp_path):
    rows = [{"cells": ["Recent release, older interviews", "10/9 - 10/11", "600 LV", "4", "48", "45", "R+3"]},
            {"cells": ["Another producer", "10/10 - 10/14", "700 LV", "3.5", "46", "47", "D+1"]}]
    source, fetcher, _, _ = rcp_fixture(tmp_path, rows=rows)
    polls = external_context.rcp_capture(source, fetcher).polls
    assert len(polls) == 2
    assert {p.field_end for p in polls} == {"2026-10-11", "2026-10-14"}


def test_exact_duplicated_rcp_rows_are_one_study(tmp_path):
    row = {"cells": ["Example Institute", "10/10 - 10/12", "600 LV", "4", "48", "45", "R+3"]}
    source, fetcher, _, _ = rcp_fixture(tmp_path, rows=[row, copy.deepcopy(row)])
    assert len(external_context.rcp_capture(source, fetcher).polls) == 1


def test_rcp_short_or_malformed_row_fails_closed(tmp_path):
    source, fetcher, _, _ = rcp_fixture(tmp_path, rows=[{"cells": ["Example Institute"]}])
    with pytest.raises(ValueError, match="row|schema|columns"):
        external_context.rcp_capture(source, fetcher)


def test_rcp_mismatched_capture_identity_fails_closed(tmp_path):
    source, fetcher, payload, path = rcp_fixture(tmp_path)
    payload["url"] = "https://fixture.invalid/unrelated"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="identity"):
        external_context.rcp_capture(source, fetcher)


def test_rcp_future_fieldwork_never_enters_a_current_cycle_poll(tmp_path):
    source, fetcher, _, _ = rcp_fixture(tmp_path, rows=[{"cells": ["Future interviews", "10/23 - 10/25", "600 LV", "4", "48", "45", "R+3"]}])
    assert not external_context.rcp_capture(source, fetcher).polls


def test_rcp_unavailable_capture_explains_primary_sources_still_work(tmp_path):
    source = {"state": "OH", "url": "https://www.realclearpolling.com/example"}
    with pytest.raises(ValueError, match="explicit public browser-table capture"):
        external_context.rcp_capture(source, fixture_fetcher(tmp_path))


def market_fixture(tmp_path, price="0.6", *, label="Example Republican (R)", question="Will the Republican win the 2026 Ohio Senate election?"):
    source = {"state": "OH", "state_name": "Ohio", "cycle": 2026,
              "event_slug": "ohio-senate-election-winner", "url": "https://fixture.invalid/event"}
    market = {"id": "42", "slug": "example-party", "groupItemTitle": label, "question": question,
              "outcomes": json.dumps(["No", "Yes"]), "outcomePrices": json.dumps(["0.4", price]),
              "active": True, "closed": False, "liquidity": "100", "volume": "200"}
    payload = {"slug": source["event_slug"], "title": "Ohio Senate election winner", "markets": [market]}
    fetcher = fixture_fetcher(tmp_path)
    doc = document(tmp_path, source["url"], json.dumps(payload), content_type="application/json")
    fetcher.fixture_documents[source["url"]] = doc
    return source, fetcher, payload, doc


@pytest.mark.parametrize("price,expected", [("0", 0), ("1", 100), ("0.6", 60)])
def test_market_yes_label_mapping_and_price_units(tmp_path, price, expected):
    source, fetcher, _, _ = market_fixture(tmp_path, price)
    row = external_context.polymarket(source, fetcher).observations[0]
    assert row.value == expected
    assert row.unit == "percent of $1 contract payout"
    assert row.metadata["party"] == "REP"
    assert row.date == "2026-10-21"
    assert "Not a vote share" in row.metadata["native_definition"]


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-0.01", "1.01"])
def test_invalid_or_nonfinite_market_prices_are_rejected(tmp_path, price):
    source, fetcher, _, _ = market_fixture(tmp_path, price)
    with pytest.raises(ValueError):
        external_context.polymarket(source, fetcher)


def test_named_unknown_party_contract_does_not_become_a_forced_party(tmp_path):
    source, fetcher, _, _ = market_fixture(tmp_path, label="Example Named Candidate", question="Will Example Named Candidate win the 2026 Ohio Senate election?")
    row = external_context.polymarket(source, fetcher).observations[0]
    assert row.metadata["party"] is None
    assert row.metadata["outcome_label"] == "Example Named Candidate"


def test_market_wrong_event_identity_is_rejected(tmp_path):
    source, fetcher, payload, doc = market_fixture(tmp_path)
    payload["slug"] = "another-event"
    Path(doc.path).write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="identity"):
        external_context.polymarket(source, fetcher)


def test_market_wrong_office_cannot_become_a_senate_input(tmp_path):
    source, fetcher, _, _ = market_fixture(tmp_path, question="Will the Republican win the 2026 Ohio Governor election?")
    with pytest.raises(ValueError, match="contract|identity|office"):
        external_context.polymarket(source, fetcher)


def test_repeated_market_id_is_not_counted_twice(tmp_path):
    source, fetcher, payload, doc = market_fixture(tmp_path)
    payload["markets"].append(copy.deepcopy(payload["markets"][0]))
    Path(doc.path).write_text(json.dumps(payload))
    assert len(external_context.polymarket(source, fetcher).observations) == 1


def test_rcp_conflicting_duplicate_study_fails_closed(tmp_path):
    row = {"cells": ["Example Institute", "10/10 - 10/12", "600 LV", "4", "48", "45", "R+3"]}
    changed = copy.deepcopy(row)
    changed["cells"][4] = "49"
    source, fetcher, _, _ = rcp_fixture(tmp_path, rows=[row, changed])
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        external_context.rcp_capture(source, fetcher)


def test_rcp_empty_table_list_is_a_documented_schema_failure(tmp_path):
    source, fetcher, payload, path = rcp_fixture(tmp_path)
    payload["tables"] = []
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="schema"):
        external_context.rcp_capture(source, fetcher)


def test_rcp_missing_timezone_does_not_establish_an_exact_capture_instant(tmp_path):
    source, fetcher, payload, path = rcp_fixture(tmp_path)
    payload["captured_at"] = "2026-10-21T12:00:00"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="timezone"):
        external_context.rcp_capture(source, fetcher)


def test_inactive_placeholder_contract_is_skipped_before_null_prices(tmp_path):
    source, fetcher, payload, doc = market_fixture(tmp_path)
    stub = copy.deepcopy(payload["markets"][0])
    stub.update(id="99", groupItemTitle="Person A", active=False, outcomePrices=None)
    payload["markets"].append(stub)
    Path(doc.path).write_text(json.dumps(payload))
    assert len(external_context.polymarket(source, fetcher).observations) == 1


def test_active_placeholder_name_does_not_acquire_a_named_party_signal(tmp_path):
    source, fetcher, _, _ = market_fixture(tmp_path, label="Person A")
    with pytest.raises(ValueError, match="No explicit"):
        external_context.polymarket(source, fetcher)


def test_nonfinite_no_price_also_invalidates_binary_market(tmp_path):
    source, fetcher, payload, doc = market_fixture(tmp_path)
    payload["markets"][0]["outcomePrices"] = '["NaN", "0.6"]'
    Path(doc.path).write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Non-finite"):
        external_context.polymarket(source, fetcher)


def test_conflicting_duplicate_market_identity_fails_closed(tmp_path):
    source, fetcher, payload, doc = market_fixture(tmp_path)
    changed = copy.deepcopy(payload["markets"][0])
    changed["outcomePrices"] = '["0.3", "0.7"]'
    payload["markets"].append(changed)
    Path(doc.path).write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        external_context.polymarket(source, fetcher)


def test_rcp_wrong_office_title_cannot_become_a_senate_study(tmp_path):
    source, fetcher, _, _ = rcp_fixture(tmp_path, title="Ohio 2026 Governor")
    with pytest.raises(ValueError, match="office"):
        external_context.rcp_capture(source, fetcher)
