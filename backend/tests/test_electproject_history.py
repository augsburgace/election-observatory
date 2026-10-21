"""Small synthetic source-format fixtures; these counts are not research evidence."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from observatory.connectors.electproject_history import parse_snapshot

COMMIT = {"sha": "a" * 40, "committed_at": "2020-10-21T16:00:00Z"}


def document(state="NC", *, rows=None, total=10, additional=""):
    county = {"fips": "37001", "name": "Alamance", "Voted.Tot": total,
              "Inperson.Tot": 6, "Mail.Rtn.Tot": 4, "Mail.Req.Tot": 5,
              "Voted.Dem": 4, "Voted.Rep": 4, "Voted.Minor": 0, "Voted.NPA": 2}
    data = {"x": {"hc_opts": {"series": [{"data": rows or [county]}]}}}
    html = f'''<p>Last Report: 10/20/2020</p><p>Total Voted: {total}</p>
    <p>In-Person Votes: 6</p><p>Ballots Returned: 4</p><p>Ballots Requested: 5</p>
    <script type="application/json">{json.dumps(data)}</script>{additional}'''
    return SimpleNamespace(text=html, url="https://raw.githubusercontent.com/original/commit/docs/NC.html",
                           sha256="hash", retrieved_at="2026-10-21T12:00:00Z")


def test_native_counties_reconcile_zeroes_survive_and_no_party_votes_inferred():
    rows, manifest = parse_snapshot({"state": "NC", "cycle": 2020}, document(), COMMIT)
    county = next(row for row in rows if row.geography_type == "county" and row.metric == "ballots_cast"
                  and row.mode == "all" and row.category_dimension is None)
    assert county.metadata["geoid"] == "37001"
    assert county.metadata["county_state_reconciles"] is True
    assert manifest["county_coverage"]["ballots_cast:all"]["county_sum"] == 10
    assert all(row.time_basis == "reconstructed" for row in rows)
    assert all(row.published_at == COMMIT["committed_at"] for row in rows)
    assert all(row.metadata["historical_publication_verified"] is False for row in rows)
    minor = next(row for row in rows if row.category == "OTHER")
    assert minor.value == 0
    assert "not candidate support" in minor.metadata["category_definition"]


def test_asynchronous_counts_stay_visible_without_fabricated_reconciliation():
    doc = document(total=11)
    doc.text = doc.text.replace('"Voted.Tot": 11', '"Voted.Tot": 10')
    rows, manifest = parse_snapshot({"state": "NC", "cycle": 2020}, doc, COMMIT)
    assert manifest["county_coverage"]["ballots_cast:all"]["reconciles"] is False
    assert next(row.value for row in rows if row.geography_type == "state" and row.metric == "ballots_cast" and row.mode == "all") == 11


def test_foreign_explicit_geoid_and_future_report_date_rejected():
    with pytest.raises(ValueError, match="Unmatched"):
        parse_snapshot({"state": "NC", "cycle": 2020}, document(rows=[{"fips": "39001", "name": "Alamance", "Voted.Tot": 10}]), COMMIT)
    with pytest.raises(ValueError, match="postdates"):
        parse_snapshot({"state": "NC", "cycle": 2020}, document(), {**COMMIT, "committed_at": "2020-10-19T16:00:00Z"})


def test_repeated_widget_disagreement_rejected_and_plain_js_never_executed():
    doc = document()
    payload = {"x": {"hc_opts": {"series": [{"data": [{"fips": "37001", "name": "Alamance", "Voted.Tot": 12}]}]}}}
    doc.text += f'<script type="application/json">{json.dumps(payload)}</script><script>throw Error("must not execute")</script>'
    with pytest.raises(ValueError, match="Conflicting embedded"):
        parse_snapshot({"state": "NC", "cycle": 2020}, doc, COMMIT)


def test_party_table_cannot_override_a_different_headline_total():
    html = '''<h3>Total Voted by Party Registration</h3><table><thead><tr><th>Party</th><th>Count</th></tr></thead>
    <tbody><tr><td>Democrats</td><td>7</td></tr><tr><td>Republicans</td><td>5</td></tr><tr><td>TOTAL</td><td>12</td></tr></tbody></table>'''
    rows, _ = parse_snapshot({"state": "NC", "cycle": 2020}, document(additional=html), COMMIT)
    assert not any(row.category_dimension == "registration" and row.geography_type == "state" for row in rows)
