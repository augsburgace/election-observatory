"""Causality and effective-sample checks for the empirical stage audit.

Values in this file are deliberately synthetic algorithm fixtures, not app data.
"""
from __future__ import annotations

import pytest
from observatory.ev_backtesting import evaluate_cases, fit_conversion, stage_snapshot, summarize


def fixture_case(year, state='NC', *, stage=7, actual=2, feature=3):
    return {'case_id': f'{year}-{state}-{stage}', 'year': year, 'state': state,
            'contest_id': f'{state}-{year}', 'actual_outcome_year': year,
            'baseline_margin_pp': 4, 'actual_margin_pp': actual, 'feature_tilt_pp': feature,
            'reference_kind': 'final_candidate_vote_distribution', 'chronology': 'retrospective_report',
            'alignment': 'days_to_election', 'stage': stage}


def row(identifier, value, *, grain='county', basis='reported', published='2020-10-20T15:00:00+00:00',
        report='2020-10-20', mode='all', source='fixture-official'):
    return {'state': 'NC', 'cycle': 2020, 'date': report, 'metric': 'ballots_cast', 'mode': mode,
            'value': value, 'geography_type': grain, 'canonical_id': identifier, 'source_id': source,
            'time_basis': basis, 'published_at': published, 'observed_at': '2026-10-21T12:00:00+00:00',
            'metadata': {}, 'revision': 1}


def test_historical_bytes_recovered_later_are_never_strict_contemporary():
    rows = [row('state:NC', 1000, grain='state', published='2022-03-16T15:00:00+00:00'),
            row('county:37001', 600, published='2022-03-16T15:00:00+00:00'),
            row('county:37003', 400, published='2022-03-16T15:00:00+00:00')]
    assert stage_snapshot(rows, 2020, '2020-10-20', 'strict_contemporary') is None
    retrospective = stage_snapshot(rows, 2020, '2020-10-20', 'retrospective_report')
    assert retrospective['total'] == 1000 and retrospective['reconciles']
    assert retrospective['chronology'] == 'retrospective_report'


def test_reconstructed_event_dates_are_not_dated_report_snapshots():
    rows = [row('state:NC', 1000, grain='state', basis='reconstructed')]
    assert stage_snapshot(rows, 2020, '2020-10-20', 'retrospective_report') is None
    rows[0]['metadata']['reconstruction_basis'] = 'dated report snapshots, not individual event dates'
    assert stage_snapshot(rows, 2020, '2020-10-20', 'retrospective_report')['total'] == 1000
    assert stage_snapshot(rows, 2020, '2020-10-20', 'strict_contemporary') is None


def test_report_scope_cannot_mix_sources_methods_or_async_counties():
    rows = [row('state:NC', 1000, grain='state'), row('county:37001', 600),
            row('county:37003', 400, source='other'), row('county:37005', 400, mode='mail'),
            row('county:37007', 400, report='2020-10-19')]
    current = stage_snapshot(rows, 2020, '2020-10-20', 'strict_contemporary')
    assert current['total'] == 1000 and current['county_sum'] == 600
    assert not current['reconciles'] and current['coverage_pct'] == 60
    assert stage_snapshot(rows, 2020, '2020-10-24', 'strict_contemporary') is None


def test_future_report_and_placeholder_zero_cannot_create_positive_ev_feature():
    rows = [row('state:NC', 0, grain='state'), row('county:37001', 0),
            row('county:37003', 1000, report='2020-10-21')]
    current = stage_snapshot(rows, 2020, '2020-10-20', 'strict_contemporary')
    assert not current['reconciles'] and current['county_sum'] == 0
    assert current['coverage_pct'] is None


def test_dependent_checkpoints_do_not_inflate_independent_elections_or_fit_eligibility():
    repeated = [fixture_case(2020, stage=n) for n in range(100)]
    metrics = summarize(evaluate_cases(repeated))
    assert metrics['cases'] == 100
    assert metrics['independent_contests'] == metrics['independent_cycles'] == 1
    fit = fit_conversion(repeated, 2022)
    assert not fit['eligible'] and fit['training_contests'] == 1
    assert fit['coefficient'] is None


def test_rolling_fit_ignores_current_future_labels_and_later_runoff_outcomes():
    training = [fixture_case(year, state=state, actual=5, feature=2) for year in (2014, 2016, 2018)
                for state in ('NC', 'OH', 'IA')]
    fitted = fit_conversion(training, 2020)
    assert fitted['eligible'] and fitted['training_cycles'] == [2014, 2016, 2018]
    assert fitted['training_contests'] == 9
    poison = [fixture_case(2020, state='TX', actual=-99, feature=-99),
              {**fixture_case(2018, state='GA'), 'actual_outcome_year': 2021}]
    assert fit_conversion(training+poison, 2020) == fitted
    # Repeating one contest's four checkpoints leaves that contest's total
    # training influence unchanged, rather than quadrupling the evidence.
    repeated = [*training, *[{**training[0], 'case_id': 'copy-'+str(n), 'stage': n} for n in range(3)]]
    assert fit_conversion(repeated, 2020)['coefficient'] == pytest.approx(fitted['coefficient'], abs=1e-6)


def test_fixed_assumption_and_earlier_fitted_predictions_are_separate_and_scores_honest():
    cases = evaluate_cases([fixture_case(2020), fixture_case(2022, actual=1)])
    for item in cases:
        assert item['predicted_margin_pp'] == pytest.approx(5.05)
        assert item['error_pp'] == pytest.approx(item['predicted_margin_pp']-item['actual_margin_pp'])
        assert item['fitted_margin_pp'] is None
        assert item['range_low_pp'] is None and item['range_high_pp'] is None
    metrics = summarize(cases)
    assert metrics['brier_score'] is None and metrics['log_loss'] is None
    assert metrics['interval_80_coverage'] is None and metrics['interval_95_coverage'] is None


def test_same_day_regular_special_contests_share_a_state_cycle_cluster_weight():
    a = fixture_case(2020, 'GA', actual=0, feature=0)
    b = {**fixture_case(2020, 'GA', actual=10, feature=0), 'contest_id': 'GA-special'}
    c = fixture_case(2020, 'NC', actual=4, feature=0)
    metrics = summarize(evaluate_cases([a, b, c]))
    assert metrics['distinct_contests'] == 3
    assert metrics['independent_state_cycles'] == 2
    # GA contributes mean(|4-0|, |4-10|)=5, NC contributes zero.
    assert metrics['margin_mae_pp'] == pytest.approx(2.5)


def test_manual_correction_created_after_cutoff_does_not_rewrite_strict_snapshot():
    total = {**row('state:NC', 2000, grain='state'), 'original_value': 1000,
             'correction': {'created_at': '2026-10-21T12:00:00+00:00', 'original': 1000, 'replacement': 2000}}
    snapshot = stage_snapshot([total, row('county:37001', 600), row('county:37003', 400)],
                              2020, '2020-10-20', 'strict_contemporary')
    assert snapshot['total'] == 1000 and snapshot['reconciles']


def test_later_runoff_label_is_not_evaluated_against_general_election_ev(monkeypatch):
    from observatory import ev_backtesting
    monkeypatch.setattr(ev_backtesting, '_state_observations', lambda *args: [])
    actual = {'year': 2021, 'election_cycle': 2020, 'contest_id': 'GA-final-runoff',
              'stage': 'RUNOFF', 'margin_pp': -1, 'source_refs': []}
    cases, exclusions = ev_backtesting.collect_feature_cases(None, 0, '2026-10-21', {'GA': [actual]})
    assert not cases
    assert len(exclusions) == 1 and 'runoff' in exclusions[0]['reason']
    assert exclusions[0]['actual_outcome_year'] == 2021


def test_current_call_can_use_later_archived_same_stage_report_without_backdating_validation(monkeypatch):
    from observatory import ev_backtesting
    rows = []
    for identifier, value, grain in [('state:NC', 1000, 'state'), ('county:37001', 600, 'county'), ('county:37003', 400, 'county')]:
        rows.append({**row(identifier, value, grain=grain, report='2022-10-26', published='2024-01-01T12:00:00Z'),
                     'cycle': 2022})
    monkeypatch.setattr(ev_backtesting, '_state_observations', lambda *args: rows)
    prior = ev_backtesting.current_same_stage_distribution(None, 'NC', 1, '2026-10-21', 2026,
        metric='ballots_cast', mode='all', current_date='2026-10-21')
    assert prior['cycle'] == 2022 and prior['date'] == '2022-10-26'
    assert prior['distribution'] == {'county:37001': 600, 'county:37003': 400}
    assert prior['chronology'] == 'retrospective_report_known_by_current_cutoff'
    assert ev_backtesting.stage_snapshot(rows, 2022, '2022-10-26', 'strict_contemporary') is None
    # An earlier research cutoff cannot acquire the later archived bytes.
    assert ev_backtesting.current_same_stage_distribution(None, 'NC', 1, '2023-10-21', 2026,
        metric='ballots_cast', mode='all', current_date='2026-10-21') is None
    rows[1]['metadata'] = {'final_status_cohort': True}
    assert ev_backtesting.current_same_stage_distribution(None, 'NC', 1, '2026-10-21', 2026,
        metric='ballots_cast', mode='all', current_date='2026-10-21') is None


def test_frozen_run_disk_cache_checks_key_hash_and_size(tmp_path, monkeypatch):
    from observatory import ev_forecast
    path = tmp_path/'run.json'
    key = {'revision': 3, 'cutoff': '2026-10-21', 'cycle': 2026,
           'model_version': ev_forecast.MODEL_VERSION, 'dependency_sha256': 'fixture'}
    result = {'revision': 3, 'as_of': '2026-10-21', 'cycle': 2026, 'model_version': ev_forecast.MODEL_VERSION,
              'calls': [], 'backtesting': {}, 'manifest': {'deterministic': True}}
    ev_forecast._cached_run_write(path, key, result)
    assert ev_forecast._cached_run_read(path, key) == result
    assert ev_forecast._cached_run_read(path, {**key, 'dependency_sha256': 'different-code'}) is None
    import json
    tampered = json.loads(path.read_text())
    tampered['calls'] = [{'fake': 'edited value'}]
    path.write_text(json.dumps(tampered))
    assert ev_forecast._cached_run_read(path, key) is None
    path.write_text('{broken JSON')
    assert ev_forecast._cached_run_read(path, key) is None
    path.write_text(' ' * 65)
    monkeypatch.setattr(ev_forecast, 'MAX_RUN_CACHE_BYTES', 64)
    assert ev_forecast._cached_run_read(path, key) is None


def test_frozen_run_reopens_without_refitting_or_reloading_selected_histories(tmp_path, monkeypatch):
    from observatory import ev_backtesting, ev_forecast
    from observatory.atlas.models import ensure_schema
    from observatory.db import Database
    from observatory.settings import Settings
    database = Database(Settings(tmp_path))
    ensure_schema(database)
    monkeypatch.setattr(ev_forecast, '_dependency_fingerprint', lambda: 'fixture-code-v1')
    monkeypatch.setattr(ev_forecast, '_senate_history', lambda *args: ({}, {}))
    monkeypatch.setattr(ev_forecast, '_early_view', lambda *args: None)
    ev_forecast._run.cache_clear()
    first = ev_forecast.early_vote_forecasts(database, 'NC', revision=0, as_of='2026-10-21')
    def forbidden(*args, **kwargs):
        raise AssertionError('Frozen disk reuse must not refit or reload source histories')
    ev_forecast._run.cache_clear()
    monkeypatch.setattr(ev_forecast, '_senate_history', forbidden)
    monkeypatch.setattr(ev_backtesting, '_state_observations', forbidden)
    restored = ev_forecast.early_vote_forecasts(database, 'OH', revision=0, as_of='2026-10-21')
    assert restored['calls'] == first['calls']
    assert restored['selected']['state'] == 'OH'
    assert 'same_stage' in restored['selected']['evidence']
    assert 'turnout_projection' in restored['selected']['evidence']
    ev_forecast._run.cache_clear()


def test_original_authority_dated_report_wording_is_admitted_but_final_cohorts_are_not():
    rows = [row('state:OH', 1000, grain='state', basis='reconstructed')]
    rows[0]['metadata'] = {'reconstruction_basis': 'dated original-authority report snapshots, not individual ballot-event dates'}
    assert stage_snapshot(rows, 2020, '2020-10-20', 'retrospective_report')['total'] == 1000
    rows[0]['metadata']['final_status_cohort'] = True
    assert stage_snapshot(rows, 2020, '2020-10-20', 'retrospective_report') is None


def test_dependency_fingerprint_covers_nested_canonical_county_geometry(tmp_path, monkeypatch):
    from observatory import ev_forecast
    monkeypatch.setattr(ev_forecast, 'PROJECT_ROOT', tmp_path)
    geography = tmp_path/'frontend'/'public'/'geography'/'counties'
    geography.mkdir(parents=True)
    county = geography/'NC.geojson'
    county.write_text('{"type":"FeatureCollection","features":[]}')
    first = ev_forecast._dependency_fingerprint()
    county.write_text('{"type":"FeatureCollection","features":[],"review":"changed"}')
    assert ev_forecast._dependency_fingerprint() != first
