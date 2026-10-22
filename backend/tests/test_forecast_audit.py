from copy import deepcopy

import pytest
from observatory import ev_backtesting
from observatory.forecast_audit import audit_call, validate_call_arithmetic
from observatory.forecast_reasoning import disagreement_review
from test_ev_backtesting import fixture_case


def call():
    return {'state': 'OH', 'call': {'margin_pp': 3, 'status': 'reference_only'}, 'evidence': {
        'historical_reference': {'margin_pp': 3, 'cycles': [{'year': 2022}]},
        'early_vote': {'metric': 'ballots_cast', 'mode': 'all'},
        'geographic_tilt': {'available': True, 'same_stage': False, 'adjustment_pp': 0,
            'matched_areas': 88, 'statewide_coverage_pct': 100, 'description': 'Final geography is context only.'}}}


def test_audit_does_not_inflate_matching_validation_with_other_cycles_states_or_features():
    rows = [fixture_case(2022, 'OH'), fixture_case(2020, 'OH'), fixture_case(2022, 'NC')]
    for row in rows:
        row.update(reference_kind='same_stage_early_vote', metric='ballots_cast', mode='all', predicted_margin_pp=3)
    rows += [{**rows[0], 'reference_kind': 'final_candidate_vote_distribution'}, {**rows[0], 'mode': 'mail'}]
    value = call()
    result = audit_call(value, {'cases': rows}, 2026)
    assert result['point_role'] == 'Historical context only'
    assert result['validation']['ev_assumption']['independent_state_cycles'] == 1
    assert result['validation']['independent_cycles'] == [2022]
    assert not result['validation']['promoted']
    assert 'partisan-primary' in result['state_note']


def test_large_outside_gap_triggers_review_without_changing_or_blending_point():
    value = call()
    original = deepcopy(value)
    result = disagreement_review(value, {'polls': {'studies': [{'producer': 'Synthetic source', 'margin_pp': -6}]},
        'markets': {'markets': [{'party': 'DEM', 'price_pct': 70}]}})
    assert result['status'] == 'review_required'
    assert result['studies'][0]['gap_pp'] == 9
    assert result['studies'][0]['opposite_direction']
    assert result['markets'][0]['challenges_direction']
    assert not result['point_changed'] and not result['market_margin_conversion']
    assert value == original
    off = disagreement_review(value, {'polls': {'status': 'off'}, 'markets': {'status': 'off'}})
    assert off['studies'] == off['markets'] == []


def test_forecast_integrity_gate_rejects_mixed_cycles_hidden_shifts_and_bad_arithmetic():
    point = call()
    point['evidence']['historical_reference']['cycles'][0].update(weight=1, margin_pp=3)
    assert validate_call_arithmetic([point], 2026)['status'] == 'passed'
    bad = deepcopy(point)
    bad['evidence']['historical_reference']['cycles'][0]['year'] = 2024
    with pytest.raises(ValueError, match='mixed election'):
        validate_call_arithmetic([bad], 2026)
    bad = deepcopy(point)
    bad['call']['margin_pp'] = 8
    with pytest.raises(ValueError, match='reconcile'):
        validate_call_arithmetic([bad], 2026)
    bad = deepcopy(point)
    bad['evidence']['geographic_tilt']['adjustment_pp'] = 2
    with pytest.raises(ValueError, match='context cannot'):
        validate_call_arithmetic([bad], 2026)
    bad = deepcopy(point)
    bad['call']['status'] = 'ev_informed'
    with pytest.raises(ValueError, match='eligible same-stage'):
        validate_call_arithmetic([bad], 2026)


def test_single_method_analogue_cannot_label_already_voted_other_methods_as_remaining(monkeypatch):
    monkeypatch.setattr(ev_backtesting, '_state_observations', lambda *args: [])
    monkeypatch.setattr(ev_backtesting, 'stage_snapshot', lambda *args, **kwargs: {'total': 1000, 'report_date': '2026-10-21', 'source_refs': []})
    monkeypatch.setattr(ev_backtesting, 'final_turnout_labels', lambda *args: {})
    monkeypatch.setattr(ev_backtesting, '_turnout_inputs', lambda *args: [
        {'year': 2018, 'early_total': 2000, 'final_total': 10000},
        {'year': 2022, 'early_total': 3000, 'final_total': 10000}])
    result = ev_backtesting.current_turnout_projection(None, 'OH', 0, '2026-10-21', 2026, 'ballots_cast', 'mail')
    assert result['available'] and result['projection'] == 4000
    assert result['remaining_participation'] is None
    whole = ev_backtesting.current_turnout_projection(None, 'OH', 0, '2026-10-21', 2026, 'ballots_cast', 'all')
    assert whole['remaining_participation'] == 3000
