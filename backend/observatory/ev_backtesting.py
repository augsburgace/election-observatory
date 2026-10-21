"""Deterministic, chronology-stratified EV research-model evaluation.

A dated official report recovered later is useful retrospective evidence, but it
is never relabeled as a contemporary forecast input. Repeated snapshots of one
contest are dependent observations; training and metrics give each contest equal
weight and report the number of independent election cycles separately.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from .analytics.common import available_at, instant, source_refs
from .connectors.calendars import calendar_reference
from .registry import ELECTION_DATES, WATCHLIST

BACKTEST_VERSION = 'senate-ev-stage-audit-1.0'
STAGES = (30, 14, 7, 1)
OPENING_STAGES = (1, 5, 10, 15)
MIN_TRAINING_CYCLES = 3
MIN_TRAINING_CONTESTS = 8
MIN_CALIBRATION_CYCLES = 4
MIN_CALIBRATION_CONTESTS = 30
FIXED_COEFFICIENT = .35
MAX_ADJUSTMENT = 5.0
MAX_REPORT_AGE_DAYS = 3
CHRONOLOGIES = ('strict_contemporary', 'retrospective_report')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _contest_key(row):
    return (row['state'], row['year'], row['contest_id'])


def _weights(rows):
    counts = defaultdict(int)
    for row in rows:
        counts[row['state'], row['year']] += 1
    return np.array([1 / counts[row['state'], row['year']] for row in rows])


def summarize(rows, prediction='predicted_margin_pp'):
    """State-election balanced errors; four checkpoints are not four elections."""
    selected = [row for row in rows if row.get(prediction) is not None]
    if not selected:
        return {'cases': 0, 'independent_contests': 0, 'distinct_contests': 0, 'independent_state_cycles': 0, 'independent_cycles': 0,
                'margin_mae_pp': None, 'margin_rmse_pp': None, 'margin_bias_pp': None,
                'direction_accuracy': None, 'brier_score': None, 'log_loss': None,
                'interval_80_coverage': None, 'interval_95_coverage': None}
    weights = _weights(selected)
    errors = np.array([row[prediction]-row['actual_margin_pp'] for row in selected])
    direction = np.array([np.sign(row[prediction]) == np.sign(row['actual_margin_pp']) for row in selected])
    return {'cases': len(selected), 'independent_contests': len({_contest_key(row) for row in selected}),
            'distinct_contests': len({_contest_key(row) for row in selected}),
            'independent_state_cycles': len({(row['state'], row['year']) for row in selected}),
            'effective_weighting_unit': 'state/election cycle; same-day regular/special contests share one cluster weight',
            'independent_cycles': len({row['year'] for row in selected}),
            'margin_mae_pp': float(np.average(abs(errors), weights=weights)),
            'margin_rmse_pp': float(np.sqrt(np.average(errors**2, weights=weights))),
            'margin_bias_pp': float(np.average(errors, weights=weights)),
            'direction_accuracy': float(np.average(direction, weights=weights)),
            'brier_score': None, 'log_loss': None, 'interval_80_coverage': None, 'interval_95_coverage': None}


def fit_conversion(rows, origin_year, *, reference_kind=None, chronology=None):
    """Earlier-cycle Huber ridge regression; no intercept or target-cycle labels.

    The one learned coefficient translates a geographic-mix covariate into a
    margin residual. Fixed hyperparameters are deliberately not selected using
    the held-out outcome. A sparse history returns an explicit unavailable fit.
    """
    training = [row for row in rows if row['year'] < origin_year
                and row.get('actual_outcome_year', row['year']) < origin_year
                and (not reference_kind or row['reference_kind'] == reference_kind)
                and (not chronology or row['chronology'] == chronology)]
    contests = {_contest_key(row) for row in training}
    cycles = sorted({row['year'] for row in training})
    manifest = {'training_cycles': cycles, 'training_contests': len(contests), 'training_snapshots': len(training),
                'coefficient': None, 'eligible': False, 'training_state_cycles': len({(row['state'], row['year']) for row in training}),
                'minimum_cycles': MIN_TRAINING_CYCLES, 'minimum_contests': MIN_TRAINING_CONTESTS,
                'method': 'State-election-balanced Huber loss (delta 10 pp), ridge penalty 8, coefficient bounded -2 to +2; no intercept.',
                'training_case_ids': sorted(row['case_id'] for row in training)}
    if len(cycles) < MIN_TRAINING_CYCLES or len({(row['state'], row['year']) for row in training}) < MIN_TRAINING_CONTESTS:
        return {**manifest, 'reason': 'Too few independent earlier election cycles/state-election clusters to estimate an EV-to-margin conversion.'}
    weights = _weights(training)
    x = np.array([row['feature_tilt_pp'] for row in training])
    y = np.array([row['actual_margin_pp']-row['baseline_margin_pp'] for row in training])
    def loss(coefficient):
        residual = np.clip(coefficient*x, -MAX_ADJUSTMENT, MAX_ADJUSTMENT)-y
        absolute = abs(residual)
        huber = np.where(absolute <= 10, .5*residual**2, 10*(absolute-5))
        return float(np.sum(weights*huber) + 8*coefficient**2)
    result = minimize_scalar(loss, bounds=(-2, 2), method='bounded', options={'xatol': 1e-10})
    return {**manifest, 'eligible': bool(result.success), 'coefficient': float(result.x) if result.success else None,
            'reason': 'Estimated from earlier independent elections only.' if result.success else 'Numerical optimization failed.'}


def evaluate_cases(feature_cases):
    """Keep a frozen assumed model and a genuinely earlier-trained model separate."""
    rows = sorted(feature_cases, key=lambda row: (row['year'], row['state'], row['contest_id'], row['chronology'], row['alignment'], row['stage'], row['reference_kind']))
    results = []
    for row in rows:
        fit = fit_conversion(rows, row['year'], reference_kind=row['reference_kind'], chronology=row['chronology'])
        fixed = row['baseline_margin_pp'] + float(np.clip(FIXED_COEFFICIENT*row['feature_tilt_pp'], -MAX_ADJUSTMENT, MAX_ADJUSTMENT))
        fitted = row['baseline_margin_pp'] + float(np.clip(fit['coefficient']*row['feature_tilt_pp'], -MAX_ADJUSTMENT, MAX_ADJUSTMENT)) if fit['eligible'] else None
        results.append({**row, 'predicted_margin_pp': fixed, 'error_pp': fixed-row['actual_margin_pp'],
                        'baseline_error_pp': row['baseline_margin_pp']-row['actual_margin_pp'],
                        'fitted_margin_pp': fitted, 'fitted_error_pp': fitted-row['actual_margin_pp'] if fitted is not None else None,
                        'coefficient': FIXED_COEFFICIENT, 'coefficient_status': 'frozen_unvalidated_assumption',
                        'training_cycles': fit['training_cycles'], 'training_contests': fit['training_contests'], 'fit': fit,
                        'range_low_pp': None, 'range_high_pp': None, 'range_kind': 'No empirically calibrated interval: insufficient independent prior EV errors.'})
    return results


@lru_cache(maxsize=80)
def _state_observations(database, state, revision):
    rows = database.observations(state=state, revision=revision, uncategorized=True, all_versions=True)
    return [row for row in rows if row['metric'] in {'ballots_cast', 'ballots_accepted', 'ballots_returned'}
            and row.get('time_basis') in {'reported', 'reconstructed'}
            and not (row.get('validation') or {}).get('status') == 'quarantined'
            and not row.get('metadata', {}).get('underlying_report_date_unverified')]


def _eligible_row(row, cutoff, chronology):
    if row['date'] > cutoff or row.get('value') is None or row['value'] < 0:
        return False
    if chronology == 'strict_contemporary':
        known = available_at(row)
        return row.get('time_basis') == 'reported' and known is not None and known <= instant(cutoff, end_of_day=True)
    if row.get('time_basis') == 'reconstructed':
        # Dated report snapshots are not individual voter-history event records.
        metadata = row.get('metadata', {})
        basis = str(metadata.get('reconstruction_basis', '')).lower()
        return not metadata.get('final_status_cohort') and all(token in basis for token in ('dated', 'report', 'snapshot'))
    return row.get('time_basis') == 'reported'


def stage_snapshot(rows, year, cutoff, chronology, *, mode=None, metric=None):
    """A synchronous single-source statewide/county report, never interpolated."""
    groups = defaultdict(list)
    for row in rows:
        if row['cycle'] != year or not _eligible_row(row, cutoff, chronology):
            continue
        if mode is not None and row.get('mode', 'all') != mode:
            continue
        if metric is not None and row['metric'] != metric:
            continue
        if (date.fromisoformat(cutoff)-date.fromisoformat(row['date'])).days > MAX_REPORT_AGE_DAYS:
            continue
        correction = row.get('correction')
        if chronology == 'strict_contemporary' and correction and instant(correction['created_at']) > instant(cutoff, end_of_day=True):
            row = {**row, 'value': row.get('original_value', correction['original'])}
        groups[(row['source_id'], row['date'], row['metric'], row.get('mode', 'all'))].append(row)
    candidates = []
    for (source_id, report_date, current_metric, current_mode), members in groups.items():
        states = [row for row in members if row.get('geography_type', 'state') == 'state']
        if not states:
            continue
        states.sort(key=lambda row: (row.get('time_basis') != 'reported', -row.get('revision', 0)))
        state = states[0]
        counties = {}
        for row in sorted(members, key=lambda r: (r.get('time_basis') == 'reported', r.get('revision', 0))):
            if row.get('geography_type') == 'county' and str(row.get('canonical_id', '')).startswith('county:'):
                counties[row['canonical_id']] = row
        county_sum = sum(row['value'] for row in counties.values())
        total = state['value']
        difference = abs(county_sum-total)
        reconciliation = total > 0 and difference <= max(1, total*1e-6)
        priority = int(state.get('metadata', {}).get('source_priority', state.get('metadata', {}).get('source_tier', 1)))
        candidates.append({'year': year, 'report_date': report_date, 'target_date': cutoff, 'metric': current_metric,
            'mode': current_mode, 'total': total, 'counties': counties, 'county_sum': county_sum,
            'coverage_pct': 100*county_sum/total if total else None, 'reconciles': reconciliation,
            'age_days': (date.fromisoformat(cutoff)-date.fromisoformat(report_date)).days,
            'chronology': chronology, 'source_id': source_id, 'source_refs': source_refs([state, *counties.values()]),
            'definition': state.get('metadata', {}).get('metric_definition', current_metric),
            '_priority': priority})
    # Prefer a genuine all-method county report, then in-person/mail. A newer
    # incomplete statewide-only report remains a visible comparison alternative.
    candidates.sort(key=lambda row: (not row['reconciles'], {'all': 0, 'early_in_person': 1, 'mail': 2}.get(row['mode'], 3),
        row['_priority'], -date.fromisoformat(row['report_date']).toordinal()))
    return candidates[0] if candidates else None


def _snapshot_feature(snapshot, context, same_stage=None):
    from .ev_forecast import geographic_tilt
    current = [{'id': identifier, 'name': row.get('geography_name', identifier), 'value': row['value'],
                'date': row['date'], 'source_refs': source_refs([row])} for identifier, row in snapshot['counties'].items()]
    return geographic_tilt(current, context['rows'], same_stage=same_stage, statewide_total=snapshot['total'])


def _target_stages(state, year):
    election = date.fromisoformat(ELECTION_DATES[year])
    result = [('days_to_election', stage, (election-timedelta(days=stage)).isoformat(), None) for stage in STAGES]
    calendar = calendar_reference(state, year, 'early_in_person')
    if calendar:
        opening = date.fromisoformat(calendar['voting_open_date'])
        result += [('days_since_opening', stage, (opening+timedelta(days=stage-1)).isoformat(), 'early_in_person') for stage in OPENING_STAGES]
    return result


def _previous_stage(rows, state, year, snapshot, alignment, stage, chronology):
    candidates = sorted({row['cycle'] for row in rows if row['cycle'] < year}, reverse=True)
    for previous_year in candidates:
        if (previous_year % 4 == 0) != (year % 4 == 0) or previous_year % 2 != year % 2:
            continue
        if alignment == 'days_since_opening':
            calendar = calendar_reference(state, previous_year, snapshot['mode'])
            if not calendar:
                continue
            target = (date.fromisoformat(calendar['voting_open_date'])+timedelta(days=stage-1)).isoformat()
        else:
            target = (date.fromisoformat(ELECTION_DATES[previous_year])-timedelta(days=stage)).isoformat()
        prior = stage_snapshot(rows, previous_year, target, chronology, mode=snapshot['mode'], metric=snapshot['metric'])
        if not prior or not prior['reconciles'] or prior['definition'] != snapshot['definition']:
            continue
        # Same stage means actual report coordinates match; old observations can
        # support an as-of study but never an exact-day pace claim.
        if prior['age_days'] != snapshot['age_days']:
            continue
        return prior
    return None


def collect_feature_cases(database, revision, cutoff, histories):
    from .ev_forecast import _county_reference, weighted_reference
    cases, exclusions = [], []
    available_years = (2016, 2018, 2020, 2022, 2024)
    for state, history in sorted(histories.items(), key=lambda pair: (pair[0] not in WATCHLIST, pair[0])):
        rows = _state_observations(database, state, revision)
        for actual in (row for row in history if row.get('election_cycle', row['year']) in available_years
                       and row['year'] < int(cutoff[:4])):
            year = actual.get('election_cycle', actual['year'])
            if 'RUNOFF' in actual.get('stage', '').upper() or actual['year'] != year:
                exclusions.append({'state': state, 'year': year, 'contest_id': actual['contest_id'],
                    'reason': 'The stored final result is a later runoff. General-election EV/cutoffs cannot be treated as same-stage runoff-margin evidence without that round’s verified calendar and observations.',
                    'actual_outcome_year': actual['year'], 'actual_stage': actual.get('stage'), 'outcome_refs': actual['source_refs']})
                continue
            reference = weighted_reference(history, year, special=bool(actual.get('special', False)))
            if reference['margin_pp'] is None:
                exclusions.append({'state': state, 'year': year, 'contest_id': actual['contest_id'], 'reason': 'No prior-only compatible Senate reference.'})
                continue
            context = _county_reference(database, state, revision, year)
            for chronology in CHRONOLOGIES:
                for alignment, stage, target, mode in _target_stages(state, year):
                    base = {'state': state, 'year': year, 'contest_id': actual['contest_id'], 'cutoff': target,
                            'alignment': alignment, 'stage': stage, 'chronology': chronology}
                    snapshot = stage_snapshot(rows, year, target, chronology, mode=mode)
                    if not snapshot:
                        exclusions.append({**base, 'reason': 'No eligible dated statewide/county EV report within three days before this stage.'})
                        continue
                    if not context or not snapshot['reconciles']:
                        exclusions.append({**base, 'reason': 'No prior-only county result context, or county observations do not reconcile with the same-source statewide report.',
                                           'report_date': snapshot['report_date'], 'coverage_pct': snapshot['coverage_pct']})
                        continue
                    previous = _previous_stage(rows, state, year, snapshot, alignment, stage, chronology)
                    for previous_stage in (None, previous) if previous else (None,):
                        distribution = {identifier: row['value'] for identifier, row in previous_stage['counties'].items()} if previous_stage else None
                        feature = _snapshot_feature(snapshot, context, distribution)
                        if not feature['available'] or (previous_stage and not feature['same_stage']):
                            exclusions.append({**base, 'reason': feature['description']})
                            continue
                        kind = feature['reference_kind']
                        item = {**base, 'case_id': _digest([state, year, actual['contest_id'], alignment, stage, chronology, kind])[:24],
                            'actual_outcome_year': actual['year'], 'actual_margin_pp': actual['margin_pp'],
                            'baseline_margin_pp': reference['margin_pp'], 'feature_tilt_pp': feature['tilt_pp'],
                            'reference_kind': kind, 'metric': snapshot['metric'], 'mode': snapshot['mode'],
                            'report_date': snapshot['report_date'], 'report_age_days': snapshot['age_days'],
                            'early_total': snapshot['total'], 'matched_areas': feature['matched_areas'],
                            'coverage_pct': feature['coverage_pct'], 'statewide_coverage_pct': feature['statewide_coverage_pct'],
                            'context_year': context['year'], 'context_office': context['office'],
                            'same_stage_baseline_year': previous_stage['year'] if previous_stage else None,
                            'input_years': sorted({row['year'] for row in reference['cycles']}),
                            'input_refs': snapshot['source_refs'] + (previous_stage['source_refs'] if previous_stage else []) + [ref for row in context['rows'] for ref in row['source_refs']],
                            'outcome_refs': actual['source_refs'],
                            'baseline_refs': [ref for row in reference['cycles'] for ref in row['source_refs']],
                            'chronology_note': 'Documented publication no later than cutoff; outcome archive remains retrospectively collected.' if chronology == 'strict_contemporary' else 'Printed report dates are historical; current bytes may have been replaced or recovered later. This is not as-reported validation.'}
                        cases.append(item)
    return cases, exclusions


def build_backtesting(database, revision, cutoff, histories):
    features, exclusions = collect_feature_cases(database, revision, cutoff, histories)
    cases = evaluate_cases(features)
    # No pooling strict and reconstructed copies as additional elections. Default
    # headline stratum is retrospective, final-geographic feature at fixed DTE.
    headline = [row for row in cases if row['chronology'] == 'retrospective_report'
                and row['reference_kind'] == 'final_candidate_vote_distribution' and row['alignment'] == 'days_to_election']
    grouped = []
    for chronology in CHRONOLOGIES:
        for kind in sorted({row['reference_kind'] for row in cases}):
            for alignment in ('days_to_election', 'days_since_opening'):
                group = [row for row in cases if row['chronology'] == chronology and row['reference_kind'] == kind and row['alignment'] == alignment]
                if group:
                    grouped.append({'chronology': chronology, 'reference_kind': kind, 'alignment': alignment,
                        'historical_reference': summarize(group, 'baseline_margin_pp'), 'fixed_ev_assumption': summarize(group),
                        'fitted_ev': summarize(group, 'fitted_margin_pp'),
                        'checkpoints': [{'stage': stage, 'historical_reference': summarize([r for r in group if r['stage'] == stage], 'baseline_margin_pp'),
                            'fixed_ev_assumption': summarize([r for r in group if r['stage'] == stage])} for stage in sorted({r['stage'] for r in group})]})
    turnout = turnout_backtesting(database, revision, cutoff)
    result = {'turnout': turnout, 'model_version': BACKTEST_VERSION, 'status': 'limited_empirical_ev_audit' if cases else 'no_eligible_ev_cases',
        'method': 'Frozen EV-assumption audit plus strictly expanding-origin, state-election-balanced robust/ridge conversion when enough independent history exists. No target-cycle labels enter features, training or calibration.',
        'metrics': {'historical_reference': summarize(headline, 'baseline_margin_pp'), 'fixed_ev_assumption': summarize(headline), 'fitted_ev': summarize(headline, 'fitted_margin_pp')},
        'cases': cases, 'exclusions': exclusions, 'grouped_metrics': grouped,
        'independent_cycles': sorted({row['year'] for row in cases}),
        'independent_contests': len({_contest_key(row) for row in cases}),
        'distinct_contests': len({_contest_key(row) for row in cases}),
        'independent_state_cycles': len({(row['state'], row['year']) for row in cases}),
        'trained_ev_holdout_cases': sum(row['fitted_margin_pp'] is not None for row in cases),
        'strict_contemporary_cases': sum(row['chronology'] == 'strict_contemporary' for row in cases),
        'probabilities_published': False, 'promotion': {'promoted': False,
            'reason': 'No production EV conversion is promoted until earlier-trained held-out performance improves the baseline across adequate independent states/cycles and calibration coverage is evaluated.',
            'minimum_training_cycles': MIN_TRAINING_CYCLES, 'minimum_training_contests': MIN_TRAINING_CONTESTS,
            'minimum_calibration_cycles': MIN_CALIBRATION_CYCLES, 'minimum_calibration_contests': MIN_CALIBRATION_CONTESTS},
        'warnings': ['Repeated checkpoints, alignments and chronology copies are dependent; they do not increase the independent election count. Same-day regular/special races are distinct contests in a shared state/election cluster; the legacy independent_contests field counts distinct contests, not independent voters or independent national environments.',
            'County historical party margin is ecological context, not a current voter’s candidate choice.',
            'The frozen 0.35 coefficient was not learned from these outcomes or preregistered before those elections. This retrospective algorithm audit can expose errors but does not prove prospective generalization.',
            'Sparse historical EV coverage does not support calibrated probabilities, Brier/log-loss scores or 80%/95% EV interval-coverage claims.',
            'Same-stage calendar days do not establish equivalent voting opportunities or unchanged pandemic-era voting rules.',
            'Original contemporary final-result publication timestamps are not fully archived; final labels are actual later certified/compiled returns.',
            'Present-day source-quality quarantines clean the evaluation universe; strict-contemporary denotes eligible feature-publication chronology, not a fully archived historical production system.'],
        'manifest': {'dataset_revision': revision, 'as_of': cutoff, 'deterministic': True, 'seed': None,
            'feature_sha256': _digest(features), 'case_sha256': _digest(cases),
            'coefficient_preregistered_before_historical_elections': False,
            'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'checkpoints_days_to_election': list(STAGES),
            'checkpoint_opening_days_one_based': list(OPENING_STAGES), 'max_report_age_days': MAX_REPORT_AGE_DAYS}}
    directory = database.settings.data_dir/'model-runs'/'ev-backtesting'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/f'r{revision}-{_digest(result["manifest"])[:16]}.json'
    if not target.exists():
        pending = target.with_suffix('.json.pending')
        pending.write_text(json.dumps(result, indent=2, allow_nan=False))
        pending.replace(target)
    return result


def same_stage_research(database, state, revision, cutoff, cycle, metric, mode, alignment='days_to_election'):
    """Actual dated reports for current-vs-prior research; absent remains absent."""
    rows = _state_observations(database, state, revision)
    target_date = cutoff[:10]
    if alignment == 'days_since_opening':
        calendar = calendar_reference(state, cycle, mode)
        if not calendar:
            return {'alignment': alignment, 'target_date': target_date, 'stage': None, 'comparisons': [],
                    'explanation': 'No verified method-opening calendar exists for this selection. The first observed report is not substituted for opening day.'}
        stage = (date.fromisoformat(target_date)-date.fromisoformat(calendar['voting_open_date'])).days+1
    else:
        stage = (date.fromisoformat(ELECTION_DATES[cycle])-date.fromisoformat(target_date)).days
    current = stage_snapshot(rows, cycle, target_date, 'strict_contemporary', metric=metric, mode=mode)
    comparisons = []
    for previous in (2016, 2018, 2020, 2022, 2024):
        if previous >= cycle:
            continue
        if alignment == 'days_since_opening':
            calendar = calendar_reference(state, previous, mode)
            if not calendar:
                comparisons.append({'cycle': previous, 'status': 'unavailable', 'reason': 'Verified method-opening calendar absent.', 'source_refs': []})
                continue
            prior_date = (date.fromisoformat(calendar['voting_open_date'])+timedelta(days=stage-1)).isoformat()
        else:
            prior_date = (date.fromisoformat(ELECTION_DATES[previous])-timedelta(days=stage)).isoformat()
        strict = stage_snapshot(rows, previous, prior_date, 'strict_contemporary', metric=metric, mode=mode)
        report = strict or stage_snapshot(rows, previous, prior_date, 'retrospective_report', metric=metric, mode=mode)
        if not report:
            comparisons.append({'cycle': previous, 'target_date': prior_date, 'status': 'unavailable', 'reason': 'No compatible dated report within three days before the stage.', 'source_refs': []})
            continue
        exact = current is not None and report['age_days'] == current['age_days'] and report['definition'] == current['definition'] and report['total'] > 0
        comparisons.append({'cycle': previous, 'target_date': prior_date, 'report_date': report['report_date'], 'total': report['total'],
            'current_total': current['total'] if current else None, 'metric': report['metric'], 'mode': report['mode'],
            'ratio': current['total']/report['total'] if exact else None, 'coverage_pct': report['coverage_pct'],
            'report_age_days': report['age_days'], 'status': 'available' if exact else 'context_only',
            'reason': 'Actual reports at equal election-relative coordinates.' if exact else 'Report age or definition differs, or the current comparable report is absent; pace ratio withheld.',
            'chronology': report['chronology'], 'source_ids': [report['source_id']], 'source_refs': report['source_refs']})
    return {'alignment': alignment, 'target_date': target_date, 'stage': stage, 'comparisons': comparisons,
            'current_report_date': current['report_date'] if current else None,
            'explanation': 'Stage is days until Election Day.' if alignment == 'days_to_election' else 'Stage is the one-based calendar day since the verified method opened, including weekends; it is not a count of actual polling opportunities.'}


@lru_cache(maxsize=12)
def final_turnout_labels(database, revision):
    """Original administrative total-participation labels, never candidate sums."""
    choices = {}
    for row in database.observations(revision=revision, metric='final_turnout', mode='all', uncategorized=True):
        if row.get('time_basis') != 'final' or row['value'] <= 0 or row.get('geography_type', 'state') != 'state':
            continue
        if (row.get('validation') or {}).get('status') == 'quarantined':
            continue
        metadata = row.get('metadata', {})
        if metadata.get('endpoint_is_candidate_votes') is True:
            continue
        key = (row['state'], row['cycle'])
        rank = (int(metadata.get('source_priority', metadata.get('source_tier', 3))), -row.get('revision', 0))
        previous = choices.get(key)
        if previous is None or rank < previous[0]:
            choices[key] = (rank, row)
    return {key: row for key, (_, row) in choices.items()}


def turnout_projection(current_total, priors, *, minimum_cycles=2):
    """Conditional stage-fraction analogue; current target final is never an input."""
    valid = [row for row in priors if row['early_total'] > 0 and row['final_total'] >= row['early_total']]
    years = sorted({row['year'] for row in valid})
    base = {'available': False, 'projection': None, 'remaining_participation': None, 'validated_forecast': False,
            'range_includes_model_error': False,
            'prior_cycles': years, 'inputs': valid, 'range_low': None, 'range_high': None,
            'range_kind': 'Historical-analogue sensitivity span; no probability coverage.',
            'method': 'Current same-stage EV divided by the median prior same-election-type stage-EV/final-participation fraction. No candidate vote, target final total or target final registration enters the predictor.'}
    if current_total is None or current_total <= 0 or len(years) < minimum_cycles:
        return {**base, 'reason': f'At least {minimum_cycles} compatible earlier election cycles and a positive current EV total are required.'}
    fractions = [row['early_total']/row['final_total'] for row in valid]
    median = float(np.median(fractions))
    projection = current_total/median
    low, high = current_total/max(fractions), current_total/min(fractions)
    return {**base, 'available': True, 'projection': projection, 'remaining_participation': projection-current_total,
            'stage_fraction': median, 'range_low': max(current_total, low), 'range_high': max(current_total, high),
            'reason': 'Explicit prior-cycle participation analogue. Changes in voting modes, rules, reporting and final EV share can make this extrapolation wrong.'}


def _turnout_inputs(rows, labels, state, year, snapshot, alignment, stage, chronology):
    priors = []
    for prior_year in sorted({row['cycle'] for row in rows if row['cycle'] < year}, reverse=True):
        # Presidential, midterm and off-year behavior remain separate.
        if (prior_year % 4 == 0) != (year % 4 == 0) or prior_year % 2 != year % 2:
            continue
        label = labels.get((state, prior_year))
        if not label:
            continue
        if alignment == 'days_since_opening':
            calendar = calendar_reference(state, prior_year, snapshot['mode'])
            if not calendar:
                continue
            prior_date = (date.fromisoformat(calendar['voting_open_date'])+timedelta(days=stage-1)).isoformat()
        else:
            prior_date = (date.fromisoformat(ELECTION_DATES[prior_year])-timedelta(days=stage)).isoformat()
        previous = stage_snapshot(rows, prior_year, prior_date, chronology, mode=snapshot['mode'], metric=snapshot['metric'])
        if not previous or previous['definition'] != snapshot['definition'] or previous['age_days'] != snapshot['age_days']:
            continue
        if previous['total'] <= 0 or previous['total'] > label['value']:
            continue
        priors.append({'year': prior_year, 'early_total': previous['total'], 'final_total': label['value'],
            'stage_fraction': previous['total']/label['value'], 'report_date': previous['report_date'],
            'source_refs': previous['source_refs']+source_refs([label]),
            'final_definition': label.get('metadata', {}).get('native_definition', 'Source-reported final participation')})
    return priors[:3]


def turnout_backtesting(database, revision, cutoff):
    labels = final_turnout_labels(database, revision)
    cases, exclusions = [], []
    for state in sorted({key[0] for key in labels}):
        rows = _state_observations(database, state, revision)
        for year in (2016, 2018, 2020, 2022, 2024):
            if year >= int(cutoff[:4]):
                continue
            actual = labels.get((state, year))
            for chronology in CHRONOLOGIES:
                for alignment, stage, target, mode in _target_stages(state, year):
                    base = {'state': state, 'year': year, 'alignment': alignment, 'stage': stage,
                            'cutoff': target, 'chronology': chronology}
                    snapshot = stage_snapshot(rows, year, target, chronology, mode=mode)
                    if not actual or not snapshot:
                        exclusions.append({**base, 'reason': 'Missing actual administrative final-participation label or eligible dated stage report.'})
                        continue
                    if snapshot['metric'] == 'ballots_returned':
                        exclusions.append({**base, 'reason': 'Received ballots do not establish counted/accepted participation; a receipt-to-counted status conversion is not modeled.'})
                        continue
                    priors = _turnout_inputs(rows, labels, state, year, snapshot, alignment, stage, chronology)
                    projection = turnout_projection(snapshot['total'], priors, minimum_cycles=1)
                    if not projection['available']:
                        exclusions.append({**base, 'reason': projection['reason']})
                        continue
                    predicted = projection['projection']
                    cases.append({**base, 'case_id': _digest([state, year, alignment, stage, chronology, 'turnout'])[:24],
                        'predicted_turnout': predicted, 'actual_turnout': actual['value'],
                        'error_ballots': predicted-actual['value'], 'percentage_error': 100*(predicted/actual['value']-1),
                        'early_total': snapshot['total'], 'metric': snapshot['metric'], 'mode': snapshot['mode'],
                        'report_date': snapshot['report_date'], 'prior_cycles': projection['prior_cycles'],
                        'inputs': projection['inputs'], 'outcome_refs': source_refs([actual]),
                        'range_low': projection['range_low'], 'range_high': projection['range_high'],
                        'model': 'Prior-only stage fraction analogue; one-cycle benchmark allowed for an explicit sparse-data diagnostic.',
                        'calibrated': False})
    def metrics(group):
        # State/year is the independent turnout outcome; dependent snapshots
        # contribute equal total weight for each state/year.
        counts = defaultdict(int)
        for row in group:
            counts[row['state'], row['year']] += 1
        weights = [1/counts[row['state'], row['year']] for row in group]
        return {'cases': len(group), 'independent_state_cycles': len(counts),
            'independent_cycles': len({row['year'] for row in group}),
            'mean_absolute_percentage_error': float(np.average([abs(row['percentage_error']) for row in group], weights=weights)) if group else None,
            'mean_absolute_error_ballots': float(np.average([abs(row['error_ballots']) for row in group], weights=weights)) if group else None,
            'rmse_ballots': float(np.sqrt(np.average([row['error_ballots']**2 for row in group], weights=weights))) if group else None}
    headline = [row for row in cases if row['chronology'] == 'retrospective_report' and row['alignment'] == 'days_to_election']
    return {'status': 'limited_prior_only_analogue_audit' if cases else 'no_eligible_turnout_holdouts',
        'cases': cases, 'exclusions': exclusions, 'metrics': metrics(headline),
        'grouped_metrics': [{'chronology': chronology, **metrics([row for row in cases if row['chronology'] == chronology])} for chronology in CHRONOLOGIES],
        'current_projection_minimum_prior_cycles': 2, 'probabilities_published': False,
        'warnings': ['This evaluates total participation, not candidate margin or vote choice.',
            'Only earlier same-election-type stage fractions enter the predictor. The target final total is used only as the validation label.',
            'Endpoint source vintages may be revised. Strict-contemporary identifies stage feature chronology; complete contemporary final-label releases are not reconstructed.',
            'A one-prior-cycle analogue is an explicit audit benchmark, not adequate validation. Current projections require at least two comparable earlier cycles.',
            'No final-election registration denominators, current target-final turnout, or candidate vote sums enter these projections.']}


def current_turnout_projection(database, state, revision, cutoff, cycle, metric, mode):
    rows = _state_observations(database, state, revision)
    snapshot = stage_snapshot(rows, cycle, cutoff[:10], 'strict_contemporary', metric=metric, mode=mode)
    if not snapshot:
        return {**turnout_projection(None, []), 'reason': 'No eligible current stage report for this method/metric.'}
    if metric == 'ballots_returned':
        return {**turnout_projection(None, []), 'current_total': snapshot['total'], 'metric': metric, 'mode': mode,
                'reason': 'Returned receipts can include pending or rejected ballots. A receipt-to-counted status conversion is not modeled, so they are not subtracted from counted final participation.',
                'source_refs': snapshot['source_refs'], 'current_final_total_used': False}
    stage = (date.fromisoformat(ELECTION_DATES[cycle])-date.fromisoformat(cutoff[:10])).days
    priors = _turnout_inputs(rows, final_turnout_labels(database, revision), state, cycle, snapshot,
                            'days_to_election', stage, 'retrospective_report')
    result = turnout_projection(snapshot['total'], priors)
    return {**result, 'current_total': snapshot['total'], 'report_date': snapshot['report_date'],
            'metric': metric, 'mode': mode, 'alignment': 'days_to_election', 'stage': stage,
            'chronology': 'Current contemporary observations with explicitly retrospective historical analogues.',
            'source_refs': snapshot['source_refs'], 'current_final_total_used': False, 'candidate_votes_used': False}


def current_same_stage_distribution(database, state, revision, cutoff, cycle, *, metric, mode,
                                    current_date, metric_definition=None, mode_classification=None):
    """Previously collected dated reports can inform today's call retrospectively.

    Their past publication did not have to be known at the historical cutoff to
    be known today. This does not convert them into strict historical backtests.
    """
    if not current_date:
        return None
    deadline = instant(cutoff, end_of_day=True)
    rows = [row for row in _state_observations(database, state, revision)
            if available_at(row) is not None and available_at(row) <= deadline
            and not row.get('metadata', {}).get('final_status_cohort')]
    stage = (date.fromisoformat(ELECTION_DATES[cycle])-date.fromisoformat(current_date)).days
    for year in sorted({row['cycle'] for row in rows if row['cycle'] < cycle}, reverse=True):
        if (year % 4 == 0) != (cycle % 4 == 0) or year % 2 != cycle % 2:
            continue
        target = (date.fromisoformat(ELECTION_DATES[year])-timedelta(days=stage)).isoformat()
        prior = stage_snapshot(rows, year, target, 'retrospective_report', mode=mode, metric=metric)
        if not prior or not prior['reconciles'] or prior['age_days'] != 0:
            continue
        if prior['definition'] != (metric_definition or metric):
            continue
        if any(row.get('metadata', {}).get('mode_classification') != mode_classification for row in prior['counties'].values()):
            continue
        return {'distribution': {identifier: row['value'] for identifier, row in prior['counties'].items()},
                'cycle': year, 'date': prior['report_date'], 'target_date': target, 'chronology': 'retrospective_report_known_by_current_cutoff',
                'metric': metric, 'mode': mode, 'definition': prior['definition'], 'source_id': prior['source_id'],
                'source_refs': prior['source_refs'], 'total': prior['total'],
                'explanation': 'Same election type and days until Election Day, anchored to the latest actual current report. Historical dated-report evidence was available by the current research cutoff; it is not relabeled as contemporaneous historical validation.'}
    return None
