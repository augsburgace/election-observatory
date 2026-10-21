"""Endpoint definitions and missing survey fields must survive normalization."""
from __future__ import annotations

import csv
import io
import zipfile
from types import SimpleNamespace

import pytest
from observatory.connectors.turnout_historical import _nonnegative, parse_eac, parse_nc
from observatory.ev_backtesting import turnout_projection


def document(path, text=None):
    return SimpleNamespace(path=path, text=text, url='https://official.example/explicit-test-fixture',
                           sha256='fixture-hash', retrieved_at='2026-10-21T12:00:00+00:00')


def test_eavs_missing_codes_remain_missing_and_incomplete_state_is_withheld(tmp_path):
    path = tmp_path/'fixture.zip'
    data = io.StringIO()
    writer = csv.DictWriter(data, fieldnames=['State_Abbr', 'FIPSCode', 'Jurisdiction_Name', 'F1a', 'F1b'])
    writer.writeheader()
    writer.writerows([{'State_Abbr': 'OH', 'FIPSCode': '39001', 'Jurisdiction_Name': 'A', 'F1a': '1000', 'F1b': '500'},
                      {'State_Abbr': 'OH', 'FIPSCode': '39003', 'Jurisdiction_Name': 'B', 'F1a': '-99', 'F1b': '300'},
                      {'State_Abbr': 'IA', 'FIPSCode': '19001', 'Jurisdiction_Name': 'C', 'F1a': '900', 'F1b': '-88'}])
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('fixture.csv', data.getvalue())
    result = parse_eac({'state': 'US', 'cycle': 2024}, document(path))
    assert not any(row.state == 'OH' and row.mode == 'all' for row in result.observations)
    assert next(row for row in result.observations if row.state == 'IA').value == 900
    assert next(row for row in result.observations if row.state == 'OH').mode == 'election_day'
    assert any(row['state'] == 'OH' and row['field'] == 'F1a' for row in result.metadata['coverage_findings'])
    assert _nonnegative(0) == 0
    assert all(_nonnegative(value) is None for value in ('-88', '-99', '-66', '', None, 'suppressed'))


def test_eavs_native_statewide_row_excludes_constituent_jurisdictions(tmp_path):
    path = tmp_path/'fixture.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('fixture.csv', 'State_Abbr,FIPSCode,Jurisdiction_Name,F1a\nOH,39,STATEWIDE,2000\nOH,39001,A,1000\nOH,39003,B,1000\n')
    result = parse_eac({'state': 'US', 'cycle': 2024}, document(path))
    assert next(row for row in result.observations if row.mode == 'all').value == 2000


def test_nc_main_summary_ignores_primary_tables_and_preserves_vintage():
    general = ''.join(f'<tr><td>{year} General</td><td>2,000</td><td>1,000</td><td>50%</td></tr>' for year in (2016, 2018, 2020, 2022, 2024))
    html = f'<table><tr><th>Election</th><th>Eligible</th><th>Ballots Cast</th></tr>{general}</table><table><tr><td>2024 Primary</td><td>2,000</td><td>2</td><td>0.1%</td></tr></table>'
    result = parse_nc({'state': 'NC'}, document(None, html))
    assert len(result.observations) == 5
    assert all(row.value == 1000 and row.time_basis == 'final' for row in result.observations)
    assert all(row.denominator is None for row in result.observations)
    assert all(row.metadata['source_priority'] == 0 for row in result.observations)
    assert 'detail page' in result.observations[-1].metadata['version_note']


def test_turnout_analogue_never_accepts_target_final_and_obeys_already_observed_constraint():
    priors = [{'year': 2018, 'early_total': 500, 'final_total': 1000},
              {'year': 2022, 'early_total': 600, 'final_total': 1000}]
    result = turnout_projection(700, priors)
    assert result['available']
    assert result['projection'] == pytest.approx(700/.55)
    assert result['range_low'] >= 700 and result['range_high'] >= result['range_low']
    assert result['remaining_participation'] == pytest.approx(result['projection']-700)
    assert 'probability' in result['range_kind']
    assert not turnout_projection(700, priors[:1])['available']
    assert not turnout_projection(700, [{'year': 2018, 'early_total': 1100, 'final_total': 1000}, priors[1]])['available']
