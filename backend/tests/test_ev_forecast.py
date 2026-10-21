"""Conditional EV projections must disclose every assumption and never read votes into composition."""
from __future__ import annotations

import pytest
from observatory.ev_forecast import geographic_tilt, historical_validation, weighted_reference
from test_evidence_workflows import aggregate
from test_evidence_workflows import harness as harness


def historic(year, margin, state='NC', contest_id=None):
    return {'year': year, 'margin_pp': margin, 'total_votes': 1000, 'contest_id': contest_id or f'{state}-{year}',
            'contest_name': 'Explicit synthetic test contest', 'source_refs': []}


def county(identifier, margin, total=1000):
    return {'id': identifier, 'name': identifier, 'rep_margin_pp': margin, 'total_votes': total,
        'round': 'reported', 'election_system': 'plurality', 'partial_suppression': False,
        'options': [{'party': 'DEM', 'votes': total*(50-margin/2)/100}, {'party': 'REP', 'votes': total*(50+margin/2)/100}], 'source_refs': []}


def early(identifier, value, date='2026-10-20'):
    return {'id': identifier, 'name': identifier, 'value': value, 'date': date, 'source_refs': []}


def test_same_stage_tilt_is_a_share_change_not_an_inferred_candidate_vote():
    current = [early('county:A', 700), early('county:B', 300)]
    history = [county('county:A', 50), county('county:B', -50)]
    result = geographic_tilt(current, history, same_stage={'county:A': 500, 'county:B': 500}, statewide_total=1000)
    assert result['available'] and result['same_stage']
    assert result['reference_kind'] == 'same_stage_early_vote'
    assert result['tilt_pp'] == pytest.approx(20)
    assert result['adjustment_pp'] == 5  # 0.35 * 20 is explicitly capped, not fitted.
    assert next(r for r in result['rows'] if r['id'] == 'county:A')['early_share_pct'] == 70
    assert 'not reveal' in result['description']
    assert all('candidate_votes_cast' not in row for row in result['rows'])


def test_final_reference_is_never_labeled_same_point_and_incomplete_history_is_withheld():
    result = geographic_tilt([early('a', 700), early('b', 300)], [county('a', 20, 500), county('b', -20, 500)], statewide_total=1000)
    assert result['available'] and not result['same_stage']
    assert result['reference_kind'] == 'final_candidate_vote_distribution'
    assert 'NOT a same-stage' in result['description']
    partial = geographic_tilt([early('a', 700), early('b', 300)], [county('a', 20)], statewide_total=1000)
    assert partial['available'] is False
    assert partial['adjustment_pp'] == 0


def test_asynchronous_reports_missing_options_and_insufficient_state_coverage_do_not_adjust():
    history = [county('a', 20), county('b', -20)]
    asynchronous = geographic_tilt([early('a', 700), early('b', 300, '2026-10-19')], history, statewide_total=1000)
    assert not asynchronous['available'] and 'asynchronous' in asynchronous['description']
    incomplete = geographic_tilt([early('a', 700), early('b', 300)], history, statewide_total=3000)
    assert not incomplete['available'] and incomplete['statewide_coverage_pct'] == pytest.approx(100/3)
    history[0]['rep_margin_pp'] = None
    assert not geographic_tilt([early('a', 700), early('b', 300)], history)['available']


def test_independent_leader_and_unknown_rcv_round_are_never_recast_as_dr_votes():
    for change in ({'election_system': 'ranked_choice'}, {'round': 'reported_round_unspecified'},
                   {'options': [{'party': 'OTHER', 'votes': 900}, {'party': 'DEM', 'votes': 50}, {'party': 'REP', 'votes': 50}]}):
        row = {**county('a', 20), **change}
        result = geographic_tilt([early('a', 700), early('b', 300)], [row, county('b', -20)], statewide_total=1000)
        assert not result['available']


def test_reference_never_uses_future_years_or_overweights_two_contests_in_one_year():
    history = [historic(2018, 10), historic(2020, 4), historic(2020, 8, contest_id='other'), historic(2022, -2), historic(2024, -90)]
    result = weighted_reference(history, 2024)
    assert {r['year'] for r in result['cycles']} == {2018, 2020, 2022}
    assert sum(r['weight'] for r in result['cycles']) == pytest.approx(1)
    assert len([r for r in result['cycles'] if r['year'] == 2020]) == 2
    assert result['margin_pp'] > -2
    future = weighted_reference(history+[historic(2026, -100)], 2024)
    assert result == future


def test_historical_validation_is_rolling_and_explicitly_not_ev_validation():
    histories = {'NC': [historic(year, (year-2000)/2) for year in range(1990, 2025, 2)]}
    result = historical_validation(histories)
    assert result['metrics']['cases'] == 4
    assert result['ev_backtest_cases'] == 0
    assert not result['probabilities_published']
    for row in result['cases']:
        assert all(prior['year'] < row['year'] for prior in row['inputs'])
    assert result['brier_score'] is None and result['log_loss'] is None
    assert 'not' in result['ev_validation']


def test_all_contests_are_present_and_historical_cutoff_excludes_later_labels(tmp_path, monkeypatch):
    from observatory import ev_forecast
    from observatory.atlas.models import ensure_schema
    from observatory.db import Database
    from observatory.settings import PROJECT_ROOT, Settings
    database = Database(Settings(tmp_path, project_root=PROJECT_ROOT))
    ensure_schema(database)
    monkeypatch.setattr(ev_forecast, '_senate_history', lambda *args: ({'NC': [historic(2018, 2), historic(2020, 4), historic(2024, -90)]}, {}))
    monkeypatch.setattr(ev_forecast, '_early_view', lambda *args: None)
    ev_forecast._run.cache_clear()
    result = ev_forecast.early_vote_forecasts(database, state='NC', revision=0, as_of='2022-10-20')
    assert len(result['calls']) == 35
    selected = result['selected']
    assert selected['call']['status'] == 'reference_only'
    assert selected['call']['margin_pp'] > 0
    assert selected['call']['range_low_pp'] < 0 < selected['call']['range_high_pp']
    assert selected['call']['eventual_winner_probability'] is None
    assert all(r['year'] < 2022 for r in selected['evidence']['historical_reference']['cycles'])
    assert all(r['year'] < 2022 for r in result['validation']['cases'])
    assert selected['manifest']['deterministic']
    assert list((tmp_path/'model-runs'/'ev-research').glob('*.json'))
    again = ev_forecast.early_vote_forecasts(database, state='TX', revision=0, as_of='2022-10-20')
    assert again['calls'] is result['calls']
    ev_forecast._run.cache_clear()


def test_geographic_counts_above_statewide_total_fail_reconciliation():
    result = geographic_tilt([early('a', 700), early('b', 500)], [county('a', 20), county('b', -20)], statewide_total=1000)
    assert not result['available']
    assert result['adjustment_pp'] == 0
    assert result['statewide_coverage_pct'] == 120
    assert 'exceed' in result['description']


def test_final_runoffs_replace_earlier_rounds_and_keep_regular_special_seats_distinct():
    from observatory.ev_forecast import _final_rounds
    general = {**historic(2020, 2, contest_id='regular-general'), 'special': False, 'stage': 'GEN', 'election_cycle': 2020}
    special = {**historic(2020, 10, contest_id='special-general'), 'special': True, 'stage': 'GEN', 'election_cycle': 2020}
    regular_runoff = {**historic(2021, -1, contest_id='regular-runoff'), 'special': False, 'stage': 'RUNOFF', 'election_cycle': 2020}
    special_runoff = {**historic(2021, -2, contest_id='special-runoff'), 'special': True, 'stage': 'RUNOFF', 'election_cycle': 2020}
    general_2022 = {**historic(2022, -1, contest_id='2022-general'), 'special': False, 'stage': 'GEN', 'election_cycle': 2022}
    runoff_2022 = {**historic(2022, -3, contest_id='2022-runoff'), 'special': False, 'stage': 'GEN RUNOFF', 'election_cycle': 2022}
    rejected = []
    result = _final_rounds([general, special, regular_runoff, special_runoff, general_2022, runoff_2022], rejected)
    assert {r['contest_id'] for r in result} == {'regular-runoff', 'special-runoff', '2022-runoff'}
    assert len(rejected) == 3
    reference = weighted_reference(result, 2026, special=False)
    assert {r['contest_id'] for r in reference['cycles']} == {'regular-runoff', '2022-runoff'}
    # The 2020 holdout uses 2021's actual final outcome, but no 2021 value enters
    # the prediction inputs available before the 2020 election.
    diagnostics = historical_validation({'GA': [historic(2016, 10), *result]})
    test = next(r for r in diagnostics['cases'] if r['contest_id'] == 'regular-runoff')
    assert test['year'] == 2020 and test['actual_outcome_year'] == 2021
    assert all(r['year'] < 2020 for r in test['inputs'])


def test_no_state_total_or_jungle_primary_can_create_ev_informed_call():
    from observatory.ev_forecast import _valid_party_margin
    row = county('a', 10)
    row['options'] += [{'party': 'REP', 'votes': 150}]
    assert not _valid_party_margin(row)
    for total in (None, 0, float('nan')):
        value = geographic_tilt([early('a', 700), early('b', 300)], [county('a', 20), county('b', -20)], statewide_total=total)
        assert not value['available'] and value['adjustment_pp'] == 0


def test_unverified_underlying_report_date_preserves_evidence_but_withholds_adjustment(harness, monkeypatch):
    from observatory import ev_forecast
    from observatory.domain import ResearchQuery
    from observatory.service import workspace
    harness.state.payload['observations'] = [aggregate(1000), aggregate(700, geo='county:37001', name='Alamance', kind='county'),
        aggregate(300, geo='county:37003', name='Alexander', kind='county')]
    revision = harness.collect()['revision']
    from observatory.db import ObservationRecord
    from sqlalchemy import select
    with harness.database.session() as session:
        for row in session.scalars(select(ObservationRecord)):
            row.payload = {**row.payload, 'metadata': {**row.payload.get('metadata', {}), 'underlying_report_date_unverified': True, 'report_date_semantics': 'upstream_upload_date'}}
        session.commit()
    view = workspace(harness.database, ResearchQuery(state='NC', revision=revision, as_of='2026-10-20'))
    monkeypatch.setattr(ev_forecast, '_early_view', lambda database, state, *args: view if state == 'NC' else None)
    monkeypatch.setattr(ev_forecast, '_county_reference', lambda *args: {'year': 2024, 'office': 'PRESIDENT', 'warnings': [], 'sources': [],
        'rows': [county('county:37001', 50), county('county:37003', -50)]})
    monkeypatch.setattr(ev_forecast, '_senate_history', lambda *args: ({'NC': [historic(2020, 4)]}, {}))
    ev_forecast._run.cache_clear()
    result = ev_forecast.early_vote_forecasts(harness.database, 'NC', revision, '2026-10-20')['selected']
    assert result['evidence']['early_vote']['available']
    assert result['evidence']['early_vote']['report_date_verified'] is False
    assert result['call']['status'] == 'reference_only'
    assert result['evidence']['geographic_tilt']['adjustment_pp'] == 0
    assert any('underlying' in w.lower() and 'unverified' in w.lower() for w in result['warnings'])
    ev_forecast._run.cache_clear()
