"""Prior-only, paired feature experiments for Senate early-vote research.

This module does not change a research call. It asks whether an additional
*observed historical* feature improves an earlier-trained model on later races.
Missing features are never imputed to zero, and a target election's final turnout
is never a feature denominator. Repeated checkpoints share one state/year weight.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from collections import Counter, OrderedDict
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
from scipy import __version__ as SCIPY_VERSION
from scipy.optimize import minimize

from .analytics.common import instant, source_refs
from .connectors.calendars import CONFIG as CALENDAR_CONFIG
from .connectors.calendars import calendar_reference
from .ev_backtesting import (
    MAX_ADJUSTMENT,
    MAX_REPORT_AGE_DAYS,
    _eligible_row,
    _target_stages,
    final_turnout_labels,
    summarize,
)
from .participation_definitions import metric_definition
from .provenance import snapshot_references
from .registry import ELECTION_DATES

VERSION = 'senate-ev-extra-features-1.1'
MAX_CACHE_BYTES = 32 * 1024 * 1024
MIN_TRAINING_CYCLES = 3
MIN_TRAINING_CLUSTERS = 8
MIN_EVALUATION_CYCLES = 4
MIN_EVALUATION_CLUSTERS = 30
FEATURES = {
    'geography_tilt_pp': {
        'label': 'Where early voters live', 'unit': 'percentage points',
        'definition': 'Existing county-weighted historical party-margin tilt; ecological context, never observed early-voter choice.',
    },
    'stage_volume_log_change': {
        'label': 'How quickly early voting is growing', 'unit': 'log ratio',
        'definition': 'Natural log of current stage EV divided by the most recent compatible earlier same-election-type stage report. This is volume growth, not a turnout rate.',
    },
    'turnout_pace_change_pp': {
        'label': 'Early participation relative to earlier turnout', 'unit': 'percentage points',
        'definition': 'Current stage EV / previous same-type administrative final participation, minus prior stage EV / its own earlier same-type final participation, multiplied by 100. All final denominators precede the case election.',
    },
    'in_person_share_change_pp': {
        'label': 'Change in the early in-person share', 'unit': 'percentage points',
        'definition': 'Change in directly reported early-in-person / all-method EV at the same stage. Numerator and denominator must share source, date, status metric and a compatible non-inferred method definition. Receipt channels are not voting methods.',
    },
    'registration_balance_change_pp': {
        'label': 'Change in party registration of early voters', 'unit': 'percentage points',
        'definition': 'Change in (registered Republican minus registered Democrat) / all reported EV at the same stage. Published registration categories must form a complete partition; primary history and candidate choice are separate concepts.',
    },
    'precinct_distribution_shift_pp': {
        'label': 'Change in which precincts turn out', 'unit': 'percentage points of total variation',
        'definition': 'Half the sum of absolute changes in precinct shares at the same stage. Requires complete, reconciled precinct EV reports, verified stable precinct identifiers and matching boundary vintage. This measures spatial redistribution, not individual party or candidate support.',
    },
}
EXPERIMENTS = [
    ('stage_volume', ['geography_tilt_pp', 'stage_volume_log_change']),
    ('turnout_pace', ['geography_tilt_pp', 'turnout_pace_change_pp']),
    ('voting_methods', ['geography_tilt_pp', 'in_person_share_change_pp']),
    ('party_registration', ['geography_tilt_pp', 'registration_balance_change_pp']),
    ('precinct_patterns', ['geography_tilt_pp', 'precinct_distribution_shift_pp']),
    ('volume_methods_party', ['geography_tilt_pp', 'stage_volume_log_change', 'in_person_share_change_pp', 'registration_balance_change_pp']),
]
STATEWIDE_EXPERIMENTS = [
    ('statewide_stage_volume', ['stage_volume_log_change']),
    ('statewide_turnout_pace', ['turnout_pace_change_pp']),
    ('statewide_voting_methods', ['in_person_share_change_pp']),
    ('statewide_party_registration', ['registration_balance_change_pp']),
    ('statewide_volume_methods_party', ['stage_volume_log_change', 'in_person_share_change_pp', 'registration_balance_change_pp']),
]
METRICS = {'ballots_cast', 'ballots_accepted', 'ballots_returned'}
_FEATURE_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_FEATURE_CACHE_LOCK = RLock()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def _refs(refs: list[dict]) -> list[dict]:
    """Document-level provenance keeps a large county report from duplicating IDs."""
    result = {}
    for ref in refs:
        key = (ref.get('source_id'), ref.get('snapshot_id'), ref.get('sha256'), ref.get('role'))
        result.setdefault(key, ref)
    return list(result.values())


def _missing(reason: str, *, refs: list[dict] | None = None, **details: Any) -> dict:
    return {'available': False, 'value': None, 'reason': reason, 'source_refs': _refs(refs or []), **details}


def _feature(value: float, refs: list[dict], **details: Any) -> dict:
    if not math.isfinite(value):
        return _missing('The calculated feature is not finite.', refs=refs)
    return {'available': True, 'value': float(value), 'reason': 'Observed inputs passed definition, chronology and same-stage checks.',
            'source_refs': _refs(refs), **details}


def _class(year: int) -> str:
    return 'presidential' if year % 4 == 0 else 'midterm' if year % 2 == 0 else 'off_year'


def _weight(rows: list[dict]) -> np.ndarray:
    counts = Counter((row['state'], row['year']) for row in rows)
    return np.array([1.0 / counts[row['state'], row['year']] for row in rows])


def _usable(row: dict, cutoff: str, chronology: str) -> bool:
    metadata = row.get('metadata') or {}
    return (row.get('metric') in METRICS and _eligible_row(row, cutoff, chronology)
            and not metadata.get('underlying_report_date_unverified')
            and not metadata.get('final_status_cohort')
            and (row.get('validation') or {}).get('status') != 'quarantined')


def _correct(row: dict, cutoff: str, chronology: str) -> dict:
    correction = row.get('correction')
    if chronology == 'strict_contemporary' and correction and instant(correction['created_at']) > instant(cutoff, end_of_day=True):
        return {**row, 'value': row.get('original_value', correction['original'])}
    return row


def _definition(row: dict) -> tuple:
    meta = row.get('metadata') or {}
    return (metric_definition(meta, row['metric'], row.get('state')), meta.get('mode_classification'), meta.get('status_classification'))


def _snapshot(rows: list[dict], year: int, cutoff: str, chronology: str, *, metric: str, mode: str,
              source_id: str | None = None, report_date: str | None = None) -> dict | None:
    choices = {}
    for original in rows:
        if (original.get('cycle') != year or original.get('metric') != metric or original.get('mode', 'all') != mode
                or original.get('geography_type', 'state') != 'state' or original.get('category_dimension')
                or (source_id and original.get('source_id') != source_id)
                or (report_date and original['date'] != report_date) or not _usable(original, cutoff, chronology)):
            continue
        age = (date.fromisoformat(cutoff) - date.fromisoformat(original['date'])).days
        if age > MAX_REPORT_AGE_DAYS:
            continue
        row = _correct(original, cutoff, chronology)
        key = row['source_id'], row['date']
        previous = choices.get(key)
        if previous is None or row.get('revision', 0) >= previous.get('revision', 0):
            choices[key] = row
    candidates = sorted(choices.values(), key=lambda row: (
        int(row.get('metadata', {}).get('source_priority', row.get('metadata', {}).get('source_tier', 1))),
        -date.fromisoformat(row['date']).toordinal(), -row.get('revision', 0)))
    if not candidates:
        return None
    row = candidates[0]
    return {'year': year, 'report_date': row['date'], 'target_date': cutoff, 'metric': metric, 'mode': mode,
            'source_id': row['source_id'], 'total': row['value'], 'definition': _definition(row), '_row': row,
            'age_days': (date.fromisoformat(cutoff) - date.fromisoformat(row['date'])).days,
            'source_refs': source_refs([row])}


def _target(case: dict, year: int) -> str | None:
    if case['alignment'] == 'days_since_opening':
        calendar = calendar_reference(case['state'], year, case['mode'])
        return (date.fromisoformat(calendar['voting_open_date']) + timedelta(days=case['stage'] - 1)).isoformat() if calendar else None
    election = ELECTION_DATES.get(year)
    return (date.fromisoformat(election) - timedelta(days=case['stage'])).isoformat() if election else None


def _prior_snapshot(rows: list[dict], case: dict, current: dict) -> tuple[dict | None, str]:
    for year in sorted({row['cycle'] for row in rows if row['cycle'] < case['year'] and _class(row['cycle']) == _class(case['year'])}, reverse=True):
        target = _target(case, year)
        if not target:
            continue
        prior = _snapshot(rows, year, target, case['chronology'], metric=current['metric'], mode=current['mode'])
        if (prior and prior['definition'] == current['definition'] and prior['age_days'] == current['age_days']
                and prior['total'] > 0):
            return prior, 'Compatible earlier report.'
    return None, 'No earlier same-election-type report matches the stage, report age, metric and method/status definitions.'


def _share(rows: list[dict], snapshot: dict, chronology: str) -> dict:
    if snapshot['mode'] != 'all':
        return _missing('The denominator is a single method rather than all-method EV.')
    numerator = _snapshot(rows, snapshot['year'], snapshot['target_date'], chronology,
                          metric=snapshot['metric'], mode='early_in_person', source_id=snapshot['source_id'], report_date=snapshot['report_date'])
    refs = snapshot['source_refs'] + (numerator['source_refs'] if numerator else [])
    if not numerator or snapshot['total'] <= 0:
        return _missing('No directly reported early-in-person numerator with the same source, date and status metric.', refs=refs)
    if any(item['_row'].get('metadata', {}).get('method_categories_disjoint') is False for item in (snapshot, numerator)):
        return _missing('The source explicitly does not establish a disjoint method partition; a direct method share is withheld.', refs=refs)
    semantic = str(numerator['_row'].get('metadata', {}).get('mode_classification', '')).lower()
    if any(token in semantic for token in ('inferred', 'not directly observed', 'receipt channel', 'includes in-person', 'all absentee methods combined')):
        return _missing('The source method is inferred, combined or a receipt channel; it cannot support this direct method-share feature.', refs=refs)
    if not 0 <= numerator['total'] <= snapshot['total']:
        return _missing('The in-person numerator exceeds the all-method total.', refs=refs)
    return _feature(100 * numerator['total'] / snapshot['total'], refs, numerator=numerator['total'], denominator=snapshot['total'],
                    definition=numerator['definition'])


def _party_balance(rows: list[dict], snapshot: dict, chronology: str) -> dict:
    parts = {}
    for original in rows:
        if (original.get('source_id') != snapshot['source_id'] or original.get('cycle') != snapshot['year']
                or original.get('date') != snapshot['report_date'] or original.get('metric') != snapshot['metric']
                or original.get('mode', 'all') != snapshot['mode'] or original.get('category_dimension') != 'registration'
                or original.get('geography_type', 'state') != 'state' or not _usable(original, snapshot['target_date'], chronology)):
            continue
        metadata = original.get('metadata') or {}
        semantics = ' '.join(str(metadata.get(key, '')) for key in ('party_classification', 'category_definition')).lower()
        if any(token in semantics for token in ('primary history', 'primary participation', 'not party registration', 'inferred', 'modeled')):
            continue
        row = _correct(original, snapshot['target_date'], chronology)
        category = row.get('category')
        old = parts.get(category)
        if old is None or row.get('revision', 0) >= old.get('revision', 0):
            parts[category] = row
    refs = snapshot['source_refs'] + source_refs(list(parts.values()))
    if not {'DEM', 'REP'} <= set(parts) or snapshot['total'] <= 0:
        return _missing('A directly published statewide Democrat/Republican registration partition is absent. Primary-history cohorts are not substituted.', refs=refs)
    if abs(sum(row['value'] for row in parts.values()) - snapshot['total']) > max(1, snapshot['total'] * 1e-6):
        return _missing('Published registration categories do not reconcile to this exact EV total; missing groups are not imputed.', refs=refs)
    return _feature(100 * (parts['REP']['value'] - parts['DEM']['value']) / snapshot['total'], refs,
                    categories={key: row['value'] for key, row in parts.items()}, denominator=snapshot['total'],
                    classification='Published registration; not candidate support')


def _turnout_feature(case: dict, current: dict, prior: dict, labels: dict) -> dict:
    refs = current['source_refs'] + prior['source_refs']
    if current['metric'] == 'ballots_returned' or any(
            'submitted for counting' in str(item['_row'].get('metadata', {}).get('native_definition', '')).lower() for item in (current, prior)):
        return _missing('Received/returned ballots do not establish counted participation; no receipt-to-counted conversion is assumed.', refs=refs)
    def denominator(before: int) -> dict | None:
        years = sorted((year for state, year in labels if state == case['state'] and year < before and _class(year) == _class(before)), reverse=True)
        return labels[(case['state'], years[0])] if years else None
    current_denominator, prior_denominator = denominator(current['year']), denominator(prior['year'])
    if not current_denominator or not prior_denominator:
        return _missing('Two earlier compatible administrative participation endpoints are required; the held-out final turnout is never a denominator.', refs=refs)
    refs += source_refs([current_denominator, prior_denominator])
    for label in (current_denominator, prior_denominator):
        meta = label.get('metadata') or {}
        if (label['value'] <= 0 or meta.get('endpoint_is_candidate_votes')
                or (meta.get('native_highest_office_proxy_jurisdictions') or 0) > 0
                or 'highest office' in str(meta.get('native_definition', '')).lower()):
            return _missing('A positive administrative turnout denominator without an explicit candidate-vote proxy is required.', refs=refs)
    current_rate, prior_rate = current['total'] / current_denominator['value'], prior['total'] / prior_denominator['value']
    return _feature(100 * (current_rate - prior_rate), refs,
                    current_prior_final_year=current_denominator['cycle'], prior_prior_final_year=prior_denominator['cycle'],
                    current_prior_final=current_denominator['value'], prior_prior_final=prior_denominator['value'],
                    current_stage_fraction=current_rate, prior_stage_fraction=prior_rate, target_final_used=False,
                    current_prior_final_definition=current_denominator.get('metadata', {}).get('native_definition', 'Source-reported final participation'),
                    prior_prior_final_definition=prior_denominator.get('metadata', {}).get('native_definition', 'Source-reported final participation'),
                    denominator_caveats=sorted({row.get('metadata', {}).get('participation_measurement_caveat') for row in (current_denominator, prior_denominator)
                                               if row.get('metadata', {}).get('participation_measurement_caveat')}))


def _precinct_snapshot(rows: list[dict], snapshot: dict, chronology: str) -> dict:
    chosen = {}
    for original in rows:
        if (original.get('source_id') != snapshot['source_id'] or original.get('cycle') != snapshot['year']
                or original.get('date') != snapshot['report_date'] or original.get('metric') != snapshot['metric']
                or original.get('mode', 'all') != snapshot['mode'] or original.get('category_dimension')
                or original.get('geography_type') != 'precinct' or not _usable(original, snapshot['target_date'], chronology)):
            continue
        meta = original.get('metadata') or {}
        identifier, vintage = meta.get('canonical_precinct_id'), meta.get('boundary_vintage')
        if not identifier or not vintage or meta.get('precinct_join_verified') is not True:
            return _missing('Precinct EV records lack a reviewed stable ID and boundary vintage; native labels alone do not prove a cross-cycle join.')
        row = _correct(original, snapshot['target_date'], chronology)
        key = str(identifier)
        previous = chosen.get(key)
        if previous and previous.get('value') != row.get('value') and previous.get('revision') == row.get('revision'):
            return _missing('Conflicting precinct values prevent a unique geographic partition.')
        if not previous or row.get('revision', 0) >= previous.get('revision', 0):
            chosen[key] = row
    refs = source_refs(list(chosen.values()))
    vintages = {str(row['metadata']['boundary_vintage']) for row in chosen.values()}
    if not chosen:
        return _missing('No compatible dated precinct-level EV observations. Historical precinct election results alone cannot supply historical early-vote patterns.')
    if len(vintages) != 1 or abs(sum(row['value'] for row in chosen.values()) - snapshot['total']) > max(1, snapshot['total'] * 1e-6):
        return _missing('Precinct reports have mixed boundary vintages or do not reconcile to the statewide EV total.', refs=refs)
    return {'available': True, 'rows': chosen, 'vintage': next(iter(vintages)), 'source_refs': refs}


def _precinct_feature(rows: list[dict], current: dict, prior: dict, chronology: str) -> dict:
    a, b = _precinct_snapshot(rows, current, chronology), _precinct_snapshot(rows, prior, chronology)
    refs = a.get('source_refs', []) + b.get('source_refs', [])
    if not a['available'] or not b['available']:
        return _missing(a.get('reason') if not a['available'] else b['reason'], refs=refs)
    if a['vintage'] != b['vintage'] or set(a['rows']) != set(b['rows']):
        return _missing('Precinct IDs or boundary vintages differ. No reviewed common-boundary crosswalk is present.', refs=refs)
    if current['total'] <= 0 or prior['total'] <= 0:
        return _missing('A positive complete precinct EV denominator is required.', refs=refs)
    value = 50 * sum(abs(a['rows'][key]['value'] / current['total'] - b['rows'][key]['value'] / prior['total']) for key in a['rows'])
    return _feature(value, refs, matched_precincts=len(a['rows']), boundary_vintage=a['vintage'], metric='total variation distance')


def extract_case_features(case: dict, state_rows: list[dict], labels: dict, *, precinct_rows: list[dict] | None = None) -> dict:
    """Attach historical evidence features to one already eligible Senate case."""
    features = {'geography_tilt_pp': (_feature(case['feature_tilt_pp'], case.get('input_refs', []),
                    description='Existing county-mix feature; final or same-stage context as specified by the case.')
                    if case.get('feature_tilt_pp') is not None else
                    _missing('No eligible reconciled county EV/context pair for a geographic model. Statewide features remain independently testable.'))}
    source_id = next((ref.get('source_id') for ref in case.get('input_refs', []) if ref.get('snapshot_id')), None)
    current = _snapshot(state_rows, case['year'], case['cutoff'], case['chronology'], metric=case['metric'], mode=case['mode'],
                        source_id=source_id, report_date=case['report_date'])
    if not current or abs(current['total'] - case['early_total']) > max(1, case['early_total'] * 1e-6):
        reason = 'The exact statewide EV report used by this case cannot be reproduced from the pinned revision.'
        features.update({key: _missing(reason) for key in FEATURES if key != 'geography_tilt_pp'})
        return {**case, 'features': features}
    prior, reason = _prior_snapshot(state_rows, case, current)
    if not prior:
        features.update({key: _missing(reason, refs=current['source_refs']) for key in FEATURES if key != 'geography_tilt_pp'})
        return {**case, 'features': features}
    shared = {'prior_cycle': prior['year'], 'current_report_date': current['report_date'], 'prior_report_date': prior['report_date'],
              'alignment': case['alignment'], 'stage': case['stage'], 'chronology': case['chronology']}
    features['stage_volume_log_change'] = (_feature(math.log(current['total'] / prior['total']), current['source_refs'] + prior['source_refs'],
                    current_total=current['total'], prior_total=prior['total'], **shared)
                    if current['total'] > 0 else _missing('A positive current total is required for a log ratio.'))
    features['turnout_pace_change_pp'] = {**_turnout_feature(case, current, prior, labels), **shared}
    current_share, prior_share = _share(state_rows, current, case['chronology']), _share(state_rows, prior, case['chronology'])
    refs = current_share['source_refs'] + prior_share['source_refs']
    if current_share['available'] and prior_share['available'] and current_share['definition'] == prior_share['definition']:
        features['in_person_share_change_pp'] = _feature(current_share['value'] - prior_share['value'], refs,
                          current_share_pp=current_share['value'], prior_share_pp=prior_share['value'], **shared)
    else:
        features['in_person_share_change_pp'] = _missing(current_share['reason'] if not current_share['available'] else prior_share['reason'] if not prior_share['available'] else 'The method definition changes across cycles.', refs=refs, **shared)
    current_party, prior_party = _party_balance(state_rows, current, case['chronology']), _party_balance(state_rows, prior, case['chronology'])
    refs = current_party['source_refs'] + prior_party['source_refs']
    features['registration_balance_change_pp'] = (_feature(current_party['value'] - prior_party['value'], refs,
                    current_balance_pp=current_party['value'], prior_balance_pp=prior_party['value'], **shared)
                    if current_party['available'] and prior_party['available'] else
                    _missing(current_party['reason'] if not current_party['available'] else prior_party['reason'], refs=refs, **shared))
    features['precinct_distribution_shift_pp'] = {**_precinct_feature(precinct_rows or [], current, prior, case['chronology']), **shared}
    return {**case, 'features': features}



def collect_statewide_cases(histories: dict, state_rows: dict[str, list[dict]], cutoff: str,
                            geographic_cases: list[dict]) -> tuple[list[dict], list[dict]]:
    """Statewide evidence can be tested without inventing missing county values.

    A separate, deduplicated family contains one report per stage and chronology.
    When the geographic audit already chose a reconciled report, reuse it so its
    statewide and geographic investigations cannot quietly disagree on evidence.
    """
    from .ev_forecast import weighted_reference
    existing = {}
    for row in sorted(geographic_cases, key=lambda r: r['reference_kind'] != 'final_candidate_vote_distribution'):
        key = row['state'], row['year'], row['contest_id'], row['alignment'], row['stage'], row['chronology']
        existing.setdefault(key, row)
    cases, exclusions = [], []
    for state, history in sorted(histories.items()):
        rows = state_rows.get(state, [])
        for actual in history:
            year = actual.get('election_cycle', actual['year'])
            if year not in (2016, 2018, 2020, 2022, 2024) or year >= int(cutoff[:4]):
                continue
            if actual['year'] != year or 'RUNOFF' in actual.get('stage', '').upper():
                exclusions.append({'state': state, 'year': year, 'contest_id': actual['contest_id'],
                    'reason': 'A later runoff outcome is not matched to general-election statewide EV.'})
                continue
            reference = weighted_reference(history, year, special=bool(actual.get('special', False)))
            if reference['margin_pp'] is None:
                exclusions.append({'state': state, 'year': year, 'contest_id': actual['contest_id'],
                                   'reason': 'No earlier compatible Senate reference for statewide feature testing.'})
                continue
            for chronology in ('strict_contemporary', 'retrospective_report'):
                for alignment, stage, target, mode in _target_stages(state, year):
                    base = {'state': state, 'year': year, 'contest_id': actual['contest_id'], 'cutoff': target,
                            'alignment': alignment, 'stage': stage, 'chronology': chronology}
                    key = state, year, actual['contest_id'], alignment, stage, chronology
                    known = existing.get(key)
                    if known:
                        cases.append({**known, 'case_id': _digest([*key, 'statewide_ev_only'])[:24],
                                      'reference_kind': 'statewide_ev_only'})
                        continue
                    candidates = []
                    for metric in sorted(METRICS):
                        for selected_mode in (mode,) if mode else ('all', 'early_in_person', 'mail'):
                            candidate = _snapshot(rows, year, target, chronology, metric=metric, mode=selected_mode)
                            if candidate and candidate['total'] > 0:
                                election_date = candidate['_row'].get('election_date')
                                if election_date and election_date != ELECTION_DATES.get(year):
                                    continue
                                candidates.append(candidate)
                    candidates.sort(key=lambda r: (
                        {'all': 0, 'early_in_person': 1, 'mail': 2}.get(r['mode'], 3),
                        int(r['_row'].get('metadata', {}).get('source_priority', r['_row'].get('metadata', {}).get('source_tier', 1))),
                        {'ballots_cast': 0, 'ballots_accepted': 1, 'ballots_returned': 2}.get(r['metric'], 3), r['age_days']))
                    if not candidates:
                        exclusions.append({**base, 'reason': 'No eligible dated statewide EV report within three days of this stage.'})
                        continue
                    snapshot = candidates[0]
                    cases.append({**base, 'case_id': _digest([*key, 'statewide_ev_only'])[:24],
                        'reference_kind': 'statewide_ev_only', 'actual_outcome_year': actual['year'],
                        'actual_margin_pp': actual['margin_pp'], 'baseline_margin_pp': reference['margin_pp'],
                        'feature_tilt_pp': None, 'metric': snapshot['metric'], 'mode': snapshot['mode'],
                        'report_date': snapshot['report_date'], 'report_age_days': snapshot['age_days'], 'early_total': snapshot['total'],
                        'input_refs': snapshot['source_refs'], 'outcome_refs': actual.get('source_refs', []),
                        'baseline_refs': [ref for row in reference['cycles'] for ref in row.get('source_refs', [])],
                        'input_years': sorted({r['year'] for r in reference['cycles']})})
    return cases, exclusions

def _available(row: dict, keys: list[str]) -> bool:
    return all(row.get('features', {}).get(key, {}).get('available') and isinstance(row['features'][key].get('value'), (int, float))
               and math.isfinite(row['features'][key]['value']) for key in keys)


def _stratum(row: dict) -> tuple:
    return row['chronology'], row['alignment'], row['reference_kind']


def _fit(training: list[dict], keys: list[str], origin: int, minimum_clusters: int) -> dict:
    cycles = sorted({row['year'] for row in training})
    clusters = len({(row['state'], row['year']) for row in training})
    manifest = {'eligible': False, 'origin_year': origin, 'training_years': cycles,
                'training_state_cycles': clusters, 'training_contests': len({(r['state'], r['year'], r['contest_id']) for r in training}),
                'training_cases': len(training), 'training_case_ids': sorted(row['case_id'] for row in training),
                'feature_ids': keys, 'coefficients': None, 'feature_scales': None,
                'minimum_training_cycles': MIN_TRAINING_CYCLES, 'minimum_training_state_cycles': minimum_clusters}
    if len(cycles) < MIN_TRAINING_CYCLES or clusters < minimum_clusters:
        return {**manifest, 'reason': 'Too little independent earlier evidence to fit this feature set. Repeated checkpoints do not increase the state-election count.'}
    weights = _weight(training)
    x = np.array([[row['features'][key]['value'] for key in keys] for row in training], dtype=float)
    y = np.array([row['actual_margin_pp'] - row['baseline_margin_pp'] for row in training])
    scales = np.maximum(1e-8, np.sqrt(np.average(x ** 2, weights=weights, axis=0)))
    normalized = x / scales
    def objective(coefficients):
        errors = normalized @ coefficients - y
        absolute = abs(errors)
        huber = np.where(absolute <= 10, .5 * errors ** 2, 10 * (absolute - 5))
        return float(np.sum(weights * huber) + 8 * np.sum(coefficients ** 2))
    def gradient(coefficients):
        errors = normalized @ coefficients - y
        return normalized.T @ (weights * np.clip(errors, -10, 10)) + 16 * coefficients
    result = minimize(objective, np.zeros(len(keys)), method='L-BFGS-B', jac=gradient, bounds=[(-10, 10)] * len(keys),
                      options={'ftol': 1e-12, 'gtol': 1e-8, 'maxiter': 1000})
    return {**manifest, 'eligible': bool(result.success), 'coefficients': dict(zip(keys, (float(value) for value in result.x))),
            'feature_scales': dict(zip(keys, (float(value) for value in scales))),
            'reason': 'Earlier-cycle-only, state-election-balanced Huber ridge fit; no intercept or target-cycle scaling.' if result.success else 'Numerical fit did not converge.'}


def _predict(row: dict, fit: dict) -> float | None:
    if not fit['eligible']:
        return None
    adjustment = sum(row['features'][key]['value'] / fit['feature_scales'][key] * fit['coefficients'][key] for key in fit['feature_ids'])
    return row['baseline_margin_pp'] + float(np.clip(adjustment, -MAX_ADJUSTMENT, MAX_ADJUSTMENT))


def _promote(cases: list[dict], baseline: dict, augmented: dict, *, comparison_key='geography_margin_pp') -> dict:
    years = sorted({row['year'] for row in cases})
    clusters = len({(row['state'], row['year']) for row in cases})
    adequate = len(years) >= MIN_EVALUATION_CYCLES and clusters >= MIN_EVALUATION_CLUSTERS
    gain = baseline['margin_mae_pp'] - augmented['margin_mae_pp'] if cases else None
    rmse_gain = baseline['margin_rmse_pp'] - augmented['margin_rmse_pp'] if cases else None
    yearly = []
    for year in years:
        selected = [row for row in cases if row['year'] == year]
        a, b = summarize(selected, comparison_key), summarize(selected, 'augmented_margin_pp')
        yearly.append({'year': year, 'paired_cases': len(selected), 'comparator_mae_pp': a['margin_mae_pp'], 'augmented_mae_pp': b['margin_mae_pp']})
    improved_years = sum(row['augmented_mae_pp'] < row['comparator_mae_pp'] for row in yearly)
    # Even passing these exploratory error gates does not validate probabilities
    # or automatically replace the production model: an independent review is due.
    candidate = bool(adequate and gain is not None and gain >= .25 and rmse_gain is not None and rmse_gain >= 0 and improved_years >= 3)
    return {'promoted': False, 'candidate_for_review': candidate,
            'reason': ('Error gates pass for independent review; production promotion and calibration are separate decisions.' if candidate else
                       'Insufficient independent held-out coverage or no consistent paired improvement. This feature does not change the live EV call.'),
            'minimum_heldout_cycles': MIN_EVALUATION_CYCLES, 'minimum_heldout_state_cycles': MIN_EVALUATION_CLUSTERS,
            'minimum_mae_improvement_pp': .25, 'heldout_cycles': years, 'heldout_state_cycles': clusters,
            'yearly_errors': yearly, 'intervals_or_probabilities_validated': False}


def evaluate_feature_cases(feature_cases: list[dict]) -> list[dict]:
    """Identical complete-case training sets and holdouts for each paired test."""
    experiments = []
    strata = sorted({_stratum(row) for row in feature_cases})
    for chronology, alignment, reference_kind in strata:
        universe = [row for row in feature_cases if _stratum(row) == (chronology, alignment, reference_kind)]
        statewide_only = reference_kind == 'statewide_ev_only'
        for experiment_id, keys in STATEWIDE_EXPERIMENTS if statewide_only else EXPERIMENTS:
            eligible = [row for row in universe if _available(row, keys)]
            exclusions = []
            for row in universe:
                missing = [key for key in keys if not row['features'].get(key, {}).get('available')]
                if missing:
                    exclusions.append({'case_id': row['case_id'], 'state': row['state'], 'year': row['year'], 'kind': 'missing_feature',
                                       'missing_features': missing, 'reasons': {key: row['features'].get(key, {}).get('reason', 'Feature absent.') for key in missing}})
            origins, evaluated = [], []
            for year in sorted({row['year'] for row in eligible}):
                heldout = [row for row in eligible if row['year'] == year]
                training = [row for row in eligible if row['year'] < year and row.get('actual_outcome_year', row['year']) < year
                            and _class(row['year']) == _class(year)]
                minimum_clusters = max(MIN_TRAINING_CLUSTERS, 4 * len(keys))
                geography_fit = (_fit(training, ['geography_tilt_pp'], year, minimum_clusters) if not statewide_only else
                                 {'eligible': False, 'reason': 'Geographic comparator does not apply to this statewide-only experiment.'})
                augmented_fit = _fit(training, keys, year, minimum_clusters)
                fit_ok = augmented_fit['eligible'] and (statewide_only or geography_fit['eligible'])
                origins.append({'year': year, 'heldout_cases': len(heldout), 'eligible': fit_ok,
                                'training_years': augmented_fit['training_years'], 'reason': augmented_fit['reason'],
                                'geography_fit': geography_fit, 'augmented_fit': augmented_fit})
                for row in heldout:
                    if not fit_ok:
                        exclusions.append({'case_id': row['case_id'], 'state': row['state'], 'year': year,
                                           'kind': 'insufficient_earlier_training', 'reason': augmented_fit['reason'],
                                           'training_years': augmented_fit['training_years'], 'training_state_cycles': augmented_fit['training_state_cycles']})
                        continue
                    a, b = (_predict(row, geography_fit) if not statewide_only else None), _predict(row, augmented_fit)
                    evaluated.append({key: row[key] for key in ('case_id', 'state', 'year', 'contest_id', 'actual_margin_pp', 'baseline_margin_pp', 'cutoff')})
                    evaluated[-1].update(geography_margin_pp=a, augmented_margin_pp=b,
                        feature_values={key: row['features'][key]['value'] for key in keys}, training_years=augmented_fit['training_years'])
            baseline, geographic, augmented = summarize(evaluated, 'baseline_margin_pp'), summarize(evaluated, 'geography_margin_pp'), summarize(evaluated, 'augmented_margin_pp')
            experiments.append({'id': f'{experiment_id}:{chronology}:{alignment}:{reference_kind}', 'experiment_id': experiment_id,
                'label': ('Statewide: ' if statewide_only else 'With geography: ') + ' + '.join(FEATURES[key]['label'] for key in keys if key != 'geography_tilt_pp'),
                'comparator': 'historical_baseline' if statewide_only else 'geography_only',
                'feature_ids': keys, 'features': keys, 'chronology': chronology, 'alignment': alignment,
                'reference_kind': reference_kind, 'status': 'prior_only_holdouts_evaluated' if evaluated else 'insufficient_prior_only_holdouts',
                'eligible_cases': len(eligible), 'eligible_state_cycles': len({(r['state'], r['year']) for r in eligible}),
                'eligible_cycles': sorted({r['year'] for r in eligible}), 'universe_cases': len(universe),
                'paired_metrics': {'historical_baseline': baseline, 'geography_only': geographic, 'augmented': augmented},
                'paired': {'baseline': baseline, 'geography_only': geographic, 'augmented': augmented},
                'gains': {'mae_pp': (baseline if statewide_only else geographic)['margin_mae_pp'] - augmented['margin_mae_pp'] if evaluated else None,
                          'rmse_pp': (baseline if statewide_only else geographic)['margin_rmse_pp'] - augmented['margin_rmse_pp'] if evaluated else None},
                'origins': origins, 'cases': evaluated, 'exclusions': exclusions,
                'promotion': _promote(evaluated, baseline if statewide_only else geographic, augmented,
                                      comparison_key='baseline_margin_pp' if statewide_only else 'geography_margin_pp')})
    return experiments


def _inventory(cases: list[dict]) -> list[dict]:
    result = []
    for key, description in FEATURES.items():
        valid = [row for row in cases if row['features'][key]['available']]
        missing = [row for row in cases if not row['features'][key]['available']]
        result.append({'id': key, **description, 'available_cases': len(valid),
            'available_state_cycles': len({(r['state'], r['year']) for r in valid}),
            'available_cycles': sorted({r['year'] for r in valid}), 'missing_cases': len(missing),
            'missing_reasons': [{'reason': reason, 'cases': count} for reason, count in Counter(row['features'][key]['reason'] for row in missing).most_common()],
            'source_refs': _refs([ref for row in valid for ref in row['features'][key]['source_refs']])})
    return result



def _read_feature_cache(path: Path, key: dict) -> dict | None:
    try:
        if not path.exists() or path.stat().st_size > MAX_CACHE_BYTES:
            return None
        def reject_constant(value):
            raise ValueError(f'Nonfinite JSON constant: {value}')
        with path.open('rb') as handle:
            raw = handle.read(MAX_CACHE_BYTES + 1)
        if len(raw) > MAX_CACHE_BYTES:
            return None
        stored = json.loads(raw, parse_constant=reject_constant)
        envelope = stored.pop('cache_envelope', None)
        if (not envelope or envelope.get('schema') != 'observatory-frozen-ev-features-v1'
                or envelope.get('key') != key or envelope.get('payload_sha256') != _digest(stored)
                or stored.get('version') != VERSION or stored.get('revision') != key['revision']
                or stored.get('as_of') != key['cutoff'] or not isinstance(stored.get('experiments'), list)
                or not isinstance(stored.get('feature_inventory'), list)):
            return None
        return stored
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _write_feature_cache(path: Path, key: dict, result: dict) -> None:
    stored = {**result, 'cache_envelope': {'schema': 'observatory-frozen-ev-features-v1', 'key': key,
                                        'payload_sha256': _digest(result)}}
    text = json.dumps(stored, indent=2, allow_nan=False)
    if len(text.encode()) > MAX_CACHE_BYTES:
        return
    pending = path.with_suffix(f'.json.{os.getpid()}.pending')
    pending.write_text(text)
    pending.replace(path)

def build_feature_validation(database, revision: int | None, cutoff: str, *, backtesting: dict | None = None) -> dict:
    """Read pinned aggregate evidence; do not collect or modify the database.

    Passing the existing stage audit avoids a second national geographic pass.
    Statewide records are small; precinct evidence loads only for eligible states.
    """
    revision = database.latest_revision() if revision is None else revision
    if backtesting is None:
        from .ev_backtesting import build_backtesting
        from .ev_forecast import _senate_history
        histories, _ = _senate_history(database, revision)
        backtesting = build_backtesting(database, revision, cutoff, histories)
    if backtesting.get('manifest', {}).get('dataset_revision') not in (None, revision):
        raise ValueError('The existing backtest revision does not match the requested feature evidence revision.')
    if backtesting.get('manifest', {}).get('as_of') not in (None, cutoff):
        raise ValueError('The existing backtest cutoff does not match the requested feature evidence cutoff.')
    from .ev_forecast import _dependency_fingerprint
    fingerprint = _dependency_fingerprint()
    cache_key = {'revision': revision, 'cutoff': cutoff, 'version': VERSION,
                 'dependency_sha256': fingerprint, 'scipy_version': SCIPY_VERSION,
                 'input_backtest_sha256': _digest(backtesting.get('manifest', {}))}
    memory_key = str(database.settings.database_path), _digest(cache_key)
    directory = database.settings.data_dir / 'model-runs' / 'ev-features'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'r{revision}-{_digest(cache_key)[:24]}.json'
    with _FEATURE_CACHE_LOCK:
        if memory_key in _FEATURE_CACHE:
            _FEATURE_CACHE.move_to_end(memory_key)
            return deepcopy(_FEATURE_CACHE[memory_key])
        with (directory / 'build.lock').open('a') as run_lock:
            fcntl.flock(run_lock, fcntl.LOCK_EX)
            result = _read_feature_cache(target, cache_key)
            if result is None:
                result = _build_feature_validation(database, revision, cutoff, backtesting)
                result['manifest']['dependency_sha256'] = fingerprint
                _write_feature_cache(target, cache_key, result)
        _FEATURE_CACHE[memory_key] = result
        while len(_FEATURE_CACHE) > 2:
            _FEATURE_CACHE.popitem(last=False)
        return deepcopy(result)



def _build_feature_validation(database, revision: int, cutoff: str, backtesting: dict) -> dict:
    from .ev_forecast import _senate_history
    histories, _ = _senate_history(database, revision)
    source_cases = backtesting.get('cases', [])
    labels = final_turnout_labels(database, revision)
    state_rows = {state: database.observations(state=state, revision=revision, geography_type='state', all_versions=True)
                  for state in sorted(set(histories) | {row['state'] for row in source_cases})}
    statewide_cases, statewide_exclusions = collect_statewide_cases(histories, state_rows, cutoff, source_cases)
    augmented = []
    for state in sorted({row['state'] for row in [*source_cases, *statewide_cases]}):
        precinct_rows = database.observations(state=state, revision=revision, geography_type='precinct', uncategorized=True, all_versions=True)
        for case in (row for row in [*source_cases, *statewide_cases] if row['state'] == state):
            augmented.append(extract_case_features(case, state_rows[state], labels, precinct_rows=precinct_rows))
    experiments = evaluate_feature_cases(augmented)
    headline = [row for row in experiments if row['chronology'] == 'retrospective_report' and row['alignment'] == 'days_to_election'
                and row['reference_kind'] in {'final_candidate_vote_distribution', 'statewide_ev_only'}]
    public_cases = [{key: row[key] for key in ('case_id', 'state', 'year', 'contest_id', 'cutoff', 'chronology', 'alignment', 'stage',
                      'reference_kind', 'metric', 'mode', 'report_date', 'actual_margin_pp', 'baseline_margin_pp', 'features')} |
                    {key: row.get(key) for key in ('actual_outcome_year', 'outcome_refs', 'baseline_refs', 'input_years', 'context_year', 'context_office')} for row in augmented]
    manifest = {'dataset_revision': revision, 'as_of': cutoff, 'version': VERSION,
                'input_backtest_sha256': _digest(backtesting.get('manifest', {})), 'feature_sha256': _digest(public_cases),
                'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'calendar_configuration_sha256': hashlib.sha256(CALENDAR_CONFIG.read_bytes()).hexdigest(),
                'runtime_versions': {'numpy': np.__version__, 'scipy': SCIPY_VERSION}, 'deterministic': True,
                'hyperparameters': {'huber_delta_pp': 10, 'ridge_penalty': 8, 'coefficient_bounds_standardized': [-10, 10],
                    'no_intercept': True, 'prediction_adjustment_cap_pp': MAX_ADJUSTMENT, 'training_only_rms_scaling': True},
                'complete_case_policy': 'No missing-feature zero fill. Each augmented model and geography-only comparator use identical earlier complete-case rows and identical held-out cases.',
                'effective_weighting_unit': 'State/election year. Repeated checkpoints and same-year regular/special contests share a single unit of weight.',
                'feature_policy_frozen_before_this_run': True, 'historically_preregistered': False,
                'source_refs': _refs([ref for row in augmented for feature in row['features'].values() for ref in feature.get('source_refs', [])]),
                'outcome_refs': _refs([ref for row in augmented for ref in row.get('outcome_refs', [])]),
                'baseline_refs': _refs([ref for row in augmented for ref in row.get('baseline_refs', [])]),
                'resolved_snapshot_refs': snapshot_references(database, public_cases, revision)}
    return {'version': VERSION, 'revision': revision, 'as_of': cutoff,
            'status': 'additional_features_under_evaluation' if augmented else 'no_eligible_historical_feature_cases',
            'conclusion': ('Some later elections can be scored using earlier evidence. Compare each added factor against its stated comparator on the same races; no factor is automatically promoted.'
                           if any(row['cases'] for row in experiments) else
                           'The archive contains useful participation, method and registration evidence, but not enough independent earlier elections to score added-factor forecasts honestly. No added factor is yet demonstrated to improve the live call.'),
            'feature_inventory': _inventory([row for row in augmented if row['reference_kind'] == 'statewide_ev_only']),
            'geographic_feature_inventory': _inventory([row for row in augmented if row['reference_kind'] != 'statewide_ev_only']),
            'coverage_scope': {'states': sorted(state_rows), 'states_with_statewide_cases': sorted({row['state'] for row in statewide_cases}),
                               'states_with_geographic_cases': sorted({row['state'] for row in source_cases}),
                               'statewide_cases': len(statewide_cases), 'geographic_cases': len(source_cases),
                               'inventory_family': 'Unique statewide case family; geography inventory is available separately.'},
            'headline_experiments': headline, 'experiments': experiments, 'feature_cases': public_cases,
            'upstream_exclusions': backtesting.get('exclusions', []), 'statewide_exclusions': statewide_exclusions,
            'frozen_geography_audit': {'policy': 'Separate, untrained 0.35 conversion; not evidence that added features generalize.',
                                        'metrics': backtesting.get('metrics', {})},
            'promotion': {'promoted': False, 'reason': 'Feature experiments are exploratory and do not alter live calls. No calibrated intervals or win probabilities are inferred.'},
            'warnings': [
                'More rows do not mean more independent elections. State-election clustering balances repeated reports and related contests.',
                'Every learned holdout uses only earlier-cycle outcomes and training-only feature scales. Current-cycle final turnout and final registration cannot enter predictors.',
                'Historical source revisions are retrospectively collected; strict-contemporary feature publication is a separate stratum, not a reconstructed production system.',
                'Published registration categories and historical geographic party margins do not reveal early voters’ choices. No religion, demographic intersections or individual propensity is inferred.',
                'Different feature availability creates different case sets. Compare models within a paired experiment, not headline errors across experiments.',
                'These are multiple exploratory ablations with fixed hyperparameters, not historically preregistered experiments. Sparse or selected coverage cannot establish nationwide forecast accuracy.',
                'Precinct election-result maps cannot substitute for missing dated precinct early-vote reports. Missing features remain unavailable.',
            ], 'manifest': manifest}
