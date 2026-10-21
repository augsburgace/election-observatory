"""Synthetic algorithm fixtures, never seed data or displayed election evidence."""
from __future__ import annotations

import copy
import math

import pytest
from observatory.ev_feature_validation import (
    _fit,
    _party_balance,
    _precinct_feature,
    _share,
    _snapshot,
    evaluate_feature_cases,
    extract_case_features,
)

DATES = {2016: '2016-11-01', 2020: '2020-10-27', 2024: '2024-10-29'}


def observation(year, value, *, mode='all', category=None, basis='reconstructed', metadata=None,
                source=None, grain='state', precinct=None, vintage='2020'):
    meta = {'reconstruction_basis': 'dated report snapshots in original authority archive', **(metadata or {})}
    if precinct:
        meta.update(canonical_precinct_id=precinct, boundary_vintage=vintage, precinct_join_verified=True)
    return {'state': 'NC', 'cycle': year, 'date': DATES[year], 'metric': 'ballots_cast', 'mode': mode,
            'value': value, 'geography_type': grain, 'category_dimension': 'registration' if category else None,
            'category': category, 'time_basis': basis, 'source_id': source or f'fixture-{year}',
            'snapshot_id': year, 'id': f'{year}-{mode}-{category}-{precinct}', 'revision': year,
            'published_at': '2026-10-21T12:00:00Z', 'observed_at': '2026-10-21T12:00:00Z', 'metadata': meta}


def case():
    return {'case_id': 'case-2024-NC', 'state': 'NC', 'year': 2024, 'actual_outcome_year': 2024,
            'contest_id': 'NC-2024-senate', 'cutoff': DATES[2024], 'report_date': DATES[2024],
            'alignment': 'days_to_election', 'stage': 7, 'chronology': 'retrospective_report',
            'reference_kind': 'final_candidate_vote_distribution', 'metric': 'ballots_cast', 'mode': 'all',
            'early_total': 2000, 'feature_tilt_pp': 3, 'actual_margin_pp': 2, 'baseline_margin_pp': 4,
            'input_refs': [{'snapshot_id': 2024, 'source_id': 'fixture-2024'}]}


def state_rows():
    return [observation(2020, 1000), observation(2024, 2000),
            observation(2020, 400, mode='early_in_person'), observation(2024, 1200, mode='early_in_person'),
            observation(2020, 400, category='DEM'), observation(2020, 400, category='REP'), observation(2020, 200, category='UNA'),
            observation(2024, 600, category='DEM'), observation(2024, 900, category='REP'), observation(2024, 500, category='UNA')]


def labels():
    return {('NC', year): {**observation(year, total), 'metric': 'final_turnout', 'time_basis': 'final'}
            for year, total in [(2016, 8000), (2020, 10000), (2024, 99999999)]}


def test_stage_volume_turnout_mode_and_registration_use_only_observed_prior_context():
    result = extract_case_features(case(), state_rows(), labels())['features']
    assert result['stage_volume_log_change']['value'] == pytest.approx(math.log(2))
    assert result['turnout_pace_change_pp']['value'] == pytest.approx(7.5)
    assert result['turnout_pace_change_pp']['current_prior_final_year'] == 2020
    assert result['turnout_pace_change_pp']['prior_prior_final_year'] == 2016
    assert result['turnout_pace_change_pp']['target_final_used'] is False
    assert result['in_person_share_change_pp']['value'] == pytest.approx(20)
    assert result['registration_balance_change_pp']['value'] == pytest.approx(15)
    assert not result['precinct_distribution_shift_pp']['available']
    assert result['precinct_distribution_shift_pp']['value'] is None


def test_poisoning_heldout_final_turnout_does_not_change_any_feature():
    first = extract_case_features(case(), state_rows(), labels())
    changed = labels()
    changed[('NC', 2024)]['value'] = 1
    assert extract_case_features(case(), state_rows(), changed) == first


def test_received_ballots_cannot_become_a_counted_turnout_denominator():
    rows, item = state_rows(), case()
    for row in rows:
        row['metric'] = 'ballots_returned'
    item['metric'] = 'ballots_returned'
    result = extract_case_features(item, rows, labels())['features']
    assert result['stage_volume_log_change']['available']
    assert not result['turnout_pace_change_pp']['available']
    assert 'receipt-to-counted' in result['turnout_pace_change_pp']['reason']


def test_strict_chronology_never_relabels_later_retrieved_report_dates():
    item = {**case(), 'chronology': 'strict_contemporary'}
    result = extract_case_features(item, state_rows(), labels())['features']
    assert not result['stage_volume_log_change']['available']
    assert _snapshot(state_rows(), 2024, DATES[2024], 'strict_contemporary', metric='ballots_cast', mode='all') is None


def test_asynchronous_or_different_definitions_withhold_same_stage_features():
    rows = state_rows()
    rows[0]['metadata']['status_classification'] = 'Received, not accepted'
    result = extract_case_features(case(), rows, labels())['features']
    assert not result['stage_volume_log_change']['available']
    rows = state_rows()
    rows[0]['date'] = '2020-10-26'
    result = extract_case_features(case(), rows, labels())['features']
    assert not result['stage_volume_log_change']['available']


def test_missing_party_partition_is_not_zero_and_primary_history_is_not_registration():
    rows = state_rows()
    total = _snapshot(rows, 2024, DATES[2024], 'retrospective_report', metric='ballots_cast', mode='all')
    missing = [row for row in rows if row.get('category') != 'UNA']
    result = _party_balance(missing, total, 'retrospective_report')
    assert not result['available'] and result['value'] is None
    for row in rows:
        if row.get('category'):
            row['metadata']['party_classification'] = 'Primary history, not party registration'
    assert not _party_balance(rows, total, 'retrospective_report')['available']


def test_unknown_registered_categories_can_reconcile_but_are_not_candidate_votes():
    rows = state_rows()
    rows[-1]['category'] = 'Unknown registration'
    total = _snapshot(rows, 2024, DATES[2024], 'retrospective_report', metric='ballots_cast', mode='all')
    result = _party_balance(rows, total, 'retrospective_report')
    assert result['available'] and result['categories']['Unknown registration'] == 500
    assert result['value'] == 15
    assert result['classification'] == 'Published registration; not candidate support'


def test_inferred_or_overlapping_voting_method_is_not_a_direct_share():
    rows = state_rows()
    total = _snapshot(rows, 2024, DATES[2024], 'retrospective_report', metric='ballots_cast', mode='all')
    for row in rows:
        if row['mode'] == 'early_in_person':
            row['metadata']['mode_classification'] = 'Inferred from receipt channel; not directly observed'
    assert not _share(rows, total, 'retrospective_report')['available']
    rows = state_rows()
    rows[3]['value'] = 3000
    assert not _share(rows, total, 'retrospective_report')['available']


def test_precinct_patterns_require_same_reviewed_ids_boundaries_and_complete_totals():
    rows = state_rows()
    current = _snapshot(rows, 2024, DATES[2024], 'retrospective_report', metric='ballots_cast', mode='all')
    prior = _snapshot(rows, 2020, DATES[2020], 'retrospective_report', metric='ballots_cast', mode='all')
    precincts = [observation(2020, 500, grain='precinct', precinct='A'), observation(2020, 500, grain='precinct', precinct='B'),
                 observation(2024, 1500, grain='precinct', precinct='A'), observation(2024, 500, grain='precinct', precinct='B')]
    result = _precinct_feature(precincts, current, prior, 'retrospective_report')
    assert result['available'] and result['value'] == 25
    precincts[-1]['metadata']['boundary_vintage'] = '2024'
    assert not _precinct_feature(precincts, current, prior, 'retrospective_report')['available']
    precincts[-1]['metadata']['boundary_vintage'] = '2020'
    precincts[-1]['value'] = 499
    # One ballot rounding tolerance is accepted, but an incomplete partition is not.
    precincts[-1]['value'] = 400
    assert not _precinct_feature(precincts, current, prior, 'retrospective_report')['available']


def experiment_case(year, state, *, stage=7, feature=1.0, outcome=4, available=True):
    base = {**case(), 'case_id': f'{state}-{year}-{stage}', 'state': state, 'year': year, 'actual_outcome_year': year,
            'contest_id': f'{state}-{year}', 'actual_margin_pp': outcome, 'stage': stage}
    base['features'] = {key: {'available': available, 'value': feature if available else None, 'reason': 'Fixture missing.', 'source_refs': []}
                        for key in ('geography_tilt_pp', 'stage_volume_log_change', 'turnout_pace_change_pp',
                                    'in_person_share_change_pp', 'registration_balance_change_pp', 'precinct_distribution_shift_pp')}
    return base


def experiment(result, identifier='stage_volume'):
    return next(row for row in result if row.get('experiment_id', row['id']) == identifier)


def test_repeated_checkpoints_do_not_create_training_eligibility():
    repeated = [experiment_case(2020, 'NC', stage=number) for number in range(100)]
    result = experiment(evaluate_feature_cases(repeated))
    assert result['eligible_cases'] == 100 and result['eligible_state_cycles'] == 1
    assert result['paired_metrics']['augmented']['cases'] == 0
    assert result['gains']['mae_pp'] is None
    assert result['promotion']['promoted'] is False


def test_rolling_origin_does_not_train_on_same_or_future_outcomes():
    training = [experiment_case(year, state) for year in (2014, 2016, 2018) for state in ('NC', 'OH', 'IA')]
    later = experiment_case(2020, 'TX', outcome=-99)
    result = experiment(evaluate_feature_cases(training + [later]))
    origin = next(row for row in result['origins'] if row['year'] == 2020)
    assert origin['eligible']
    assert origin['augmented_fit']['training_years'] == [2014, 2016, 2018]
    assert origin['augmented_fit']['training_case_ids'] == origin['geography_fit']['training_case_ids']
    before = copy.deepcopy(origin['augmented_fit'])
    later['actual_margin_pp'] = 99
    after = experiment(evaluate_feature_cases(training + [later]))
    assert next(row for row in after['origins'] if row['year'] == 2020)['augmented_fit'] == before
    assert result['paired_metrics']['historical_baseline']['cases'] == result['paired_metrics']['augmented']['cases'] == 1
    assert result['promotion']['promoted'] is False


def test_extra_feature_complete_case_policy_pairs_comparator_training_and_holdout():
    training = [experiment_case(year, state) for year in (2014, 2016, 2018) for state in ('NC', 'OH', 'IA')]
    training[0]['features']['stage_volume_log_change'] = {'available': False, 'value': None, 'reason': 'Missing source.'}
    result = experiment(evaluate_feature_cases(training + [experiment_case(2020, 'TX')]))
    origin = next(row for row in result['origins'] if row['year'] == 2020)
    assert origin['augmented_fit']['training_cases'] == origin['geography_fit']['training_cases'] == 8
    assert training[0]['case_id'] not in origin['augmented_fit']['training_case_ids']
    assert any(row['case_id'] == training[0]['case_id'] and row['kind'] == 'missing_feature' for row in result['exclusions'])


def test_training_scales_are_earlier_only_and_duplicate_cluster_weights_stay_constant():
    training = [experiment_case(year, state, feature=float(index + 1), outcome=8)
                for index, (year, state) in enumerate((year, state) for year in (2014, 2016, 2018) for state in ('NC', 'OH', 'IA'))]
    fit = _fit(training, ['geography_tilt_pp', 'stage_volume_log_change'], 2020, 8)
    duplicate = {**training[0], 'case_id': 'duplicate'}
    repeated = _fit(training + [duplicate], ['geography_tilt_pp', 'stage_volume_log_change'], 2020, 8)
    assert fit['eligible'] and repeated['eligible']
    assert repeated['feature_scales'] == pytest.approx(fit['feature_scales'])
    assert repeated['coefficients'] == pytest.approx(fit['coefficients'], abs=1e-6)


def test_later_runoff_label_is_excluded_from_earlier_training():
    rows = [experiment_case(year, state) for year in (2014, 2016, 2018) for state in ('NC', 'OH', 'IA')]
    rows[0]['actual_outcome_year'] = 2021
    result = experiment(evaluate_feature_cases(rows + [experiment_case(2020, 'TX')]))
    origin = next(row for row in result['origins'] if row['year'] == 2020)
    assert rows[0]['case_id'] not in origin['augmented_fit']['training_case_ids']
    assert origin['augmented_fit']['training_state_cycles'] == 8


def test_explicit_highest_office_vote_proxy_cannot_enter_turnout_feature():
    inputs = labels()
    inputs[('NC', 2020)]['metadata']['native_highest_office_proxy_jurisdictions'] = 1
    feature = extract_case_features(case(), state_rows(), inputs)['features']['turnout_pace_change_pp']
    assert not feature['available'] and feature['value'] is None
    assert 'candidate-vote proxy' in feature['reason']


def test_quarantined_or_final_status_cohort_inputs_never_become_features():
    for key, value in [('final_status_cohort', True), ('underlying_report_date_unverified', True)]:
        rows = state_rows()
        rows[1]['metadata'][key] = value
        feature = extract_case_features(case(), rows, labels())['features']['stage_volume_log_change']
        assert not feature['available']
    rows = state_rows()
    rows[1]['validation'] = {'status': 'quarantined'}
    assert not extract_case_features(case(), rows, labels())['features']['stage_volume_log_change']['available']


def test_late_manual_correction_does_not_rewrite_strict_historical_feature():
    rows = state_rows()
    for row in rows:
        row['time_basis'] = 'reported'
        row['published_at'] = row['date'] + 'T12:00:00Z'
    item = {**case(), 'chronology': 'strict_contemporary'}
    baseline = extract_case_features(item, rows, labels())
    rows[1].update(value=999999, original_value=2000,
                   correction={'created_at': '2026-10-21T12:00:00Z', 'original': 2000, 'replacement': 999999})
    corrected = extract_case_features(item, rows, labels())
    assert corrected['features']['stage_volume_log_change'] == baseline['features']['stage_volume_log_change']
    assert corrected['features']['in_person_share_change_pp'] == baseline['features']['in_person_share_change_pp']


def test_statewide_features_are_not_blocked_by_missing_county_geography():
    from observatory.ev_feature_validation import collect_statewide_cases
    histories = {'NC': [{'year': year, 'contest_id': f'NC-{year}', 'margin_pp': margin, 'source_refs': [], 'special': False}
                         for year, margin in [(2016, 4), (2020, 3), (2024, 2)]]}
    cases, _ = collect_statewide_cases(histories, {'NC': state_rows()}, '2026-10-21', [])
    item = next(row for row in cases if row['year'] == 2024 and row['stage'] == 7 and row['alignment'] == 'days_to_election')
    assert item['reference_kind'] == 'statewide_ev_only'
    assert item['feature_tilt_pp'] is None
    result = extract_case_features(item, state_rows(), labels())
    assert not result['features']['geography_tilt_pp']['available']
    assert result['features']['stage_volume_log_change']['available']
    assert result['features']['in_person_share_change_pp']['value'] == pytest.approx(20)


def test_statewide_holdout_compares_same_cases_to_history_without_fabricated_geography():
    rows = [experiment_case(year, state) for year in (2014, 2016, 2018) for state in ('NC', 'OH', 'IA')]
    rows += [experiment_case(2020, 'TX', outcome=7)]
    for row in rows:
        row['reference_kind'] = 'statewide_ev_only'
        row['features']['geography_tilt_pp'] = {'available': False, 'value': None, 'reason': 'No county report.'}
    result = experiment(evaluate_feature_cases(rows), 'statewide_stage_volume')
    assert result['comparator'] == 'historical_baseline'
    assert result['paired']['baseline']['cases'] == result['paired']['augmented']['cases'] == 1
    assert result['paired']['geography_only']['cases'] == 0
    assert result['paired']['geography_only']['margin_mae_pp'] is None
    assert result['cases'][0]['geography_margin_pp'] is None
    assert result['gains']['mae_pp'] == pytest.approx(result['paired']['baseline']['margin_mae_pp'] - result['paired']['augmented']['margin_mae_pp'])


def test_statewide_family_deduplicates_geographic_reference_variants():
    from observatory.ev_feature_validation import collect_statewide_cases
    known = case()
    alternate = {**known, 'case_id': 'alternate', 'reference_kind': 'same_stage_ev_distribution'}
    histories = {'NC': [{'year': 2020, 'contest_id': 'NC-2020', 'margin_pp': 3, 'source_refs': [], 'special': False},
                         {'year': 2024, 'contest_id': known['contest_id'], 'margin_pp': 2, 'source_refs': [], 'special': False}]}
    cases, _ = collect_statewide_cases(histories, {'NC': state_rows()}, '2026-10-21', [known, alternate])
    selected = [row for row in cases if row['year'] == 2024 and row['stage'] == 7 and row['alignment'] == 'days_to_election']
    assert len(selected) == 1
    assert selected[0]['early_total'] == known['early_total']
    assert selected[0]['input_refs'] == known['input_refs']


def test_frozen_feature_cache_rejects_changed_payload_wrong_revision_and_nonfinite_values(tmp_path):
    import json

    from observatory.ev_feature_validation import VERSION, _read_feature_cache, _write_feature_cache
    path = tmp_path / 'r1.json'
    key = {'revision': 1, 'cutoff': '2026-10-21', 'dependency_sha256': 'code-a'}
    result = {'version': VERSION, 'revision': 1, 'as_of': '2026-10-21', 'experiments': [], 'feature_inventory': []}
    _write_feature_cache(path, key, result)
    assert _read_feature_cache(path, key) == result
    assert _read_feature_cache(path, {**key, 'revision': 2}) is None
    assert _read_feature_cache(path, {**key, 'dependency_sha256': 'code-b'}) is None
    changed = json.loads(path.read_text())
    changed['experiments'] = [{'invented': True}]
    path.write_text(json.dumps(changed))
    assert _read_feature_cache(path, key) is None
    path.write_text('{"value": NaN}')
    assert _read_feature_cache(path, key) is None
    assert not list(tmp_path.glob('*.pending'))


def test_generic_metric_does_not_hide_incompatible_native_definitions():
    rows = state_rows()
    rows[0]['metadata']['native_definition'] = 'Returned receipts, including pending ballots'
    rows[1]['metadata']['native_definition'] = 'Accepted participation'
    feature = extract_case_features(case(), rows, labels())['features']['stage_volume_log_change']
    assert not feature['available']


def test_explicitly_non_disjoint_methods_are_not_used_for_share_changes():
    rows = state_rows()
    rows[1]['metadata']['method_categories_disjoint'] = False
    feature = extract_case_features(case(), rows, labels())['features']['in_person_share_change_pp']
    assert not feature['available']
    assert 'disjoint' in feature['reason']
