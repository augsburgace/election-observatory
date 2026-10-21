"""Experimental EV-geography research calls, separate from validated probabilities.

This is a transparent conditional party-margin projection. County partisanship
is context, never an observed early candidate vote. The EV coefficient is an
explicit research assumption and has NOT been trained on historical EV outcomes.
Historical-only rolling-origin diagnostics do not validate the EV adjustment.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from threading import RLock

import numpy as np
from sqlalchemy import select

from .atlas import result_query
from .atlas.models import BallotOption, Contest, ElectionResult, ensure_schema
from .atlas.store import _geographies, _rows
from .db import ObservationRecord, Snapshot, record_dict
from .domain import ResearchQuery
from .provenance import snapshot_references
from .registry import races, state_info
from .service import capabilities, workspace
from .settings import PROJECT_ROOT, local_today

MODEL_VERSION = 'ev-geography-research-1.2'
EV_COEFFICIENT = 0.35
MAX_ADJUSTMENT_PP = 5.0
MIN_SENSITIVITY_HALF_WIDTH_PP = 15.0
MIN_GEOGRAPHIC_COVERAGE = .90
MIN_STATEWIDE_COVERAGE = .80
ELIGIBLE_METRICS = ('ballots_cast', 'ballots_accepted', 'ballots_returned')
ASSUMPTIONS = [
    'This is a party-margin research projection, not observed candidate votes, a certified result, or a validated winner probability.',
    'The reference pools different Senate seats, candidates and classes. It is not nominee-adjusted; current ballot identities and incumbency are unverified and no historical candidate is assumed to be running.',
    'Historical reference: up to three most recent Senate-election years within 12 years, with a six-year recency half-life. Contests in the same state/year receive equal weight; unrelated candidate votes are never added.',
    'EV adjustment = 0.35 × the change in county-weighted historical party margin, capped at ±5 percentage points. Both the coefficient and cap are unvalidated research assumptions.',
    'Current early voters and later Election Day voters can differ sharply. Individual early-voter choice is unobserved; county correlations do not identify it.',
    'The reported range is a deliberately wide, unvalidated sensitivity range, not an 80% or 95% confidence/credible interval.',
    'Polling, party registration and demographic marginals do not enter this initial projection. No unreported age-by-party, religion, propensity or demographic intersections are manufactured.',
]


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _refs(rows):
    return list({(r.get('snapshot_id'), r.get('source_id'), r.get('result_id'), r.get('observation_id'), r.get('id')): r for r in rows}.values())


def _valid_party_margin(row):
    if row.get('partial_suppression') or row.get('rep_margin_pp') is None:
        return False
    if row.get('round') == 'reported_round_unspecified' or row.get('election_system') == 'ranked_choice':
        return False
    options = row.get('options', [])
    named = [r for r in options if r.get('votes') is not None]
    if not named:
        return False
    leading = max(named, key=lambda r: r['votes'])
    # An independent winning against major parties is not a D/R outcome.
    party_counts = {party: sum(r.get('party') == party for r in named) for party in ('DEM', 'REP')}
    return leading.get('party') in {'DEM', 'REP'} and all(n == 1 for n in party_counts.values()) and not any(r.get('partial_suppression') for r in named)


def weighted_reference(history, target_year, special=False):
    """Use only earlier outcomes, keeping a multi-contest year from overweighting."""
    eligible = [r for r in history if target_year-12 <= r['year'] < target_year]
    preferred = [r for r in eligible if bool(r.get('special', False)) == special]
    context_status = 'same_regular_special_category'
    if preferred:
        eligible = preferred
    elif special:
        context_status = 'regular_context_for_special_contest'
    else:
        eligible = []
    years = sorted({r['year'] for r in eligible}, reverse=True)[:3]
    selected = [r for r in eligible if r['year'] in years]
    by_year = defaultdict(list)
    for row in selected:
        by_year[row['year']].append(row)
    denominator = sum(2**(-(target_year-year)/6) for year in by_year)
    if not denominator:
        return {'margin_pp': None, 'cycles': [], 'description': 'No compatible prior Senate party-margin reference.'}
    cycles, margin = [], 0
    for year in sorted(by_year, reverse=True):
        year_weight = 2**(-(target_year-year)/6)/denominator
        for row in sorted(by_year[year], key=lambda r: r['contest_id']):
            weight = year_weight/len(by_year[year])
            margin += row['margin_pp']*weight
            cycles.append({**row, 'weight': weight})
    return {'margin_pp': margin, 'cycles': cycles, 'seat_context_status': context_status,
            'description': 'Recency-weighted historical Senate R-minus-D margin; different seats/candidates and election environments can make this a weak current-race reference.'}


@lru_cache(maxsize=12)
def _senate_history(database, revision):
    years = list(range(1976, 2025))
    rows = _rows(database, state=None, years=years, office='US SENATE', level='state', revision=revision)
    with database.session() as session:
        options = {r.id: record_dict(r) for r in session.scalars(select(BallotOption).where(BallotOption.id.in_({r['option_id'] for r in rows})))}
        contests = {r.id: record_dict(r) for r in session.scalars(select(Contest).where(Contest.id.in_({r['contest_id'] for r in rows})))}
    histories = defaultdict(list)
    rejected = defaultdict(list)
    for row in _geographies(rows, options, contests):
        contest = contests.get(row['contest_id'], {})
        if not _valid_party_margin(row):
            rejected[row['state']].append({'year': row['year'], 'contest_id': row['contest_id'],
                'reason': 'Missing major-party options, leading independent/nonmajor option, suppressed values, or unsupported ranked-choice round.',
                'source_refs': row['source_refs']})
            continue
        histories[row['state']].append({'year': row['year'], 'margin_pp': row['rep_margin_pp'], 'total_votes': row['total_votes'],
            'contest_id': row['contest_id'], 'contest_name': contest.get('name', 'U.S. Senate'),
            'special': bool(contest.get('payload', {}).get('special')), 'stage': contest.get('election_id', '').split(':')[-1],
            'election_cycle': row['year']-1 if row['state'] == 'GA' and row['year'] == 2021 and 'RUNOFF' in contest.get('election_id', '').upper() else row['year'],
            'source_refs': row['source_refs']})
    histories = {state: _final_rounds(history, rejected[state]) for state, history in histories.items()}
    return dict(histories), dict(rejected)


def _final_rounds(history, rejected):
    """Reviewed regular/special election families keep only their final round."""
    families = defaultdict(list)
    for row in history:
        families[(row.get('election_cycle', row['year']), bool(row.get('special', False)))].append(row)
    selected = []
    for family in families.values():
        runoffs = [r for r in family if 'RUNOFF' in r.get('stage', '').upper()]
        chosen = max(runoffs, key=lambda r: r['year']) if runoffs else None
        if chosen:
            selected.append(chosen)
            for row in family:
                if row is not chosen:
                    rejected.append({'year': row['year'], 'contest_id': row['contest_id'],
                        'reason': 'Documented final runoff supersedes the earlier round in this regular/special seat family.',
                        'source_refs': row['source_refs']})
        else:
            selected.extend(family)
    return selected


def historical_validation(histories):
    """Retrospective rolling origins; only prior-year labels enter each fit."""
    residuals = []
    calibration = []
    for origin in range(1990, 2025, 2):
        known = [abs(r['error_pp']) for r in residuals if r['year'] < origin]
        widths = {level: float(np.quantile(known, level)) if len(known) >= 20 else None for level in (.8, .95)}
        for state, history in histories.items():
            for actual in (r for r in history if r.get('election_cycle', r['year']) == origin):
                past = weighted_reference(history, origin, special=bool(actual.get('special', False)))
                if past['margin_pp'] is None:
                    continue
                error = past['margin_pp']-actual['margin_pp']
                item = {'state': state, 'year': origin, 'actual_outcome_year': actual['year'], 'contest_id': actual['contest_id'], 'predicted_margin_pp': past['margin_pp'],
                    'actual_margin_pp': actual['margin_pp'], 'error_pp': error,
                    'interval_80_half_width_pp': widths[.8], 'interval_95_half_width_pp': widths[.95],
                    'covered_80': abs(error) <= widths[.8] if widths[.8] is not None else None,
                    'covered_95': abs(error) <= widths[.95] if widths[.95] is not None else None,
                    'inputs': [{'year': r['year'], 'weight': r['weight'], 'margin_pp': r['margin_pp']} for r in past['cycles']],
                    'source_refs': actual['source_refs']+_refs([ref for r in past['cycles'] for ref in r['source_refs']])}
                residuals.append(item)
                if origin in {2018, 2020, 2022, 2024}:
                    calibration.append(item)
    def summarize(rows):
        errors = [r['error_pp'] for r in rows]
        return {'cases': len(rows), 'margin_mae_pp': float(np.mean(np.abs(errors))) if errors else None,
            'margin_rmse_pp': float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            'margin_bias_pp': float(np.mean(errors)) if errors else None,
            'interval_80_coverage': float(np.mean([r['covered_80'] for r in rows if r['covered_80'] is not None])) if any(r['covered_80'] is not None for r in rows) else None,
            'interval_95_coverage': float(np.mean([r['covered_95'] for r in rows if r['covered_95'] is not None])) if any(r['covered_95'] is not None for r in rows) else None}
    absolute = [abs(r['error_pp']) for r in calibration]
    return {'status': 'historical_reference_backtested_ev_component_unvalidated', 'metrics': summarize(calibration),
        'origins': [{'year': year, **summarize([r for r in calibration if r['year'] == year])} for year in (2018, 2020, 2022, 2024)],
        'cases': calibration, 'historical_error_80_pp': float(np.quantile(absolute, .8)) if absolute else None,
        'historical_error_95_pp': float(np.quantile(absolute, .95)) if absolute else None,
        'ev_backtest_cases': 0, 'ev_validation': 'No held-out EV-enhanced model evaluation is available. These metrics validate only the historical reference, not the EV adjustment or current experimental calls.',
        'methodology': 'Each historical test uses only earlier Senate-election outcomes and calibration residuals from earlier origins. Contemporary candidate rosters, polls and EV data are excluded.',
        'timestamp_limitations': 'Retrospective analysis of the collected final-return archive, not a reconstruction of the datasets available to forecasters on each historical date. Later source corrections cannot be audited fully.',
        'brier_score': None, 'log_loss': None, 'probabilities_published': False,
        'warnings': ['Historical Senate margins can change substantially with candidates, contested seats, national environment and turnout. This simple baseline can perform poorly.',
                     'The 80%/95% coverage figures concern rolling historical-only intervals. The displayed 2026 sensitivity ranges have no claimed probability coverage.']}


def geographic_tilt(current_rows, historical_rows, *, same_stage=None, statewide_total=None):
    """A geographic-mix covariate, not an estimate of individual ballot choices."""
    current = {r['id']: r for r in current_rows if r.get('value') is not None and r['value'] >= 0}
    historical = {r['id']: r for r in historical_rows if _valid_party_margin(r)}
    common = [identifier for identifier in current if identifier in historical]
    county_total = sum(r['value'] for r in current.values())
    matched_total = sum(current[i]['value'] for i in common)
    coverage = matched_total/county_total if county_total else 0
    statewide_coverage = matched_total/statewide_total if statewide_total is not None and math.isfinite(statewide_total) and statewide_total > 0 else None
    base = {'available': False, 'tilt_pp': None, 'coefficient': EV_COEFFICIENT, 'adjustment_pp': 0.0,
            'matched_areas': len(common), 'coverage_pct': coverage*100,
            'statewide_coverage_pct': statewide_coverage*100 if statewide_coverage is not None else None,
            'reference_kind': 'unavailable', 'same_stage': False, 'rows': []}
    dates = {current[i].get('date') for i in common}
    if statewide_total is None or not math.isfinite(statewide_total) or statewide_total <= 0:
        return {**base, 'description': 'A positive compatible statewide count is required. County context alone cannot establish statewide EV coverage.'}
    if len(common) < 2 or matched_total < 1000:
        return {**base, 'description': 'At least two matched counties and 1,000 reported ballots are required by the explicit minimum-evidence policy.'}
    tolerance = max(1.0, (statewide_total or 0)*1e-6)
    if statewide_total is not None and matched_total > statewide_total+tolerance:
        return {**base, 'description': 'Matched county counts exceed the statewide count. Definitions, reporting coverage or source vintages do not reconcile; the EV adjustment is withheld.'}
    if coverage < MIN_GEOGRAPHIC_COVERAGE or (statewide_coverage is not None and statewide_coverage < MIN_STATEWIDE_COVERAGE):
        return {**base, 'description': 'Matched counties do not cover enough known current activity for a statewide EV adjustment.'}
    if len(dates) != 1:
        return {**base, 'description': 'County reports are asynchronous. The apparent geographic mix is not treated as a comparable statewide signal.'}
    if same_stage and all(same_stage.get(i) is not None and same_stage[i] >= 0 for i in common) and sum(same_stage[i] for i in common) > 0:
        references = {i: same_stage[i] for i in common}
        reference_kind, comparable = 'same_stage_early_vote', True
    else:
        references = {i: historical[i]['total_votes'] for i in common}
        reference_kind, comparable = 'final_candidate_vote_distribution', False
    reference_total = sum(references.values())
    if reference_total <= 0:
        return {**base, 'description': 'No positive reference distribution exists.'}
    rows = []
    for identifier in common:
        early_share = current[identifier]['value']/matched_total
        reference_share = references[identifier]/reference_total
        historical_margin = historical[identifier]['rep_margin_pp']
        rows.append({'id': identifier, 'name': current[identifier]['name'], 'early_votes': current[identifier]['value'],
            'early_share_pct': early_share*100, 'reference_count': references[identifier], 'reference_share_pct': reference_share*100,
            'reference_margin_pp': historical_margin, 'contribution_pp': (early_share-reference_share)*historical_margin,
            'current_source_date': current[identifier]['date'],
            'source_refs': current[identifier].get('source_refs', [])+historical[identifier].get('source_refs', [])})
    tilt = sum(r['contribution_pp'] for r in rows)
    adjustment = max(-MAX_ADJUSTMENT_PP, min(MAX_ADJUSTMENT_PP, EV_COEFFICIENT*tilt))
    rows.sort(key=lambda r: -abs(r['contribution_pp']))
    return {**base, 'available': True, 'tilt_pp': tilt, 'adjustment_pp': adjustment,
        'reference_kind': reference_kind, 'same_stage': comparable, 'rows': rows,
        'description': ('Current county shares versus compatible same-stage historical early-vote shares.' if comparable else 'Current county shares versus historical final candidate-vote shares; this is NOT a same-stage early-voting comparison.')+
            ' Each share difference is weighted by that county’s historical R-minus-D margin. It does not reveal how current early voters voted.'}


@lru_cache(maxsize=256)
def _county_reference(database, state, revision, cycle):
    with database.session() as session:
        scopes = session.execute(select(ElectionResult.year, ElectionResult.office).where(ElectionResult.state == state,
            ElectionResult.geography_level == 'county', ElectionResult.revision <= revision,
            ElectionResult.year < cycle, ElectionResult.year >= 2000,
            ElectionResult.office.in_(['US SENATE', 'PRESIDENT'])).distinct()).all()
    ordered = sorted(scopes, key=lambda r: (r.office != 'US SENATE', -r.year))
    for year, office in ordered:
        view = result_query(database, state=state, year=year, office=office, geography_level='county', baseline=None, revision=revision)
        if len({r['contest_id'] for r in view['geographies']}) != 1:
            continue
        rows = [r for r in view['geographies'] if _valid_party_margin(r)]
        if len(rows) >= 2:
            return {'year': year, 'office': office, 'rows': rows, 'sources': view['sources'], 'warnings': view['warnings']}
    return None


def _early_view(database, state, revision, cutoff, cycle):
    capability = capabilities(database, state, cycle=cycle, revision=revision, as_of=cutoff, time_basis='reported')
    combinations = capability['combinations']
    options = [row for row in combinations if row['metric'] in ELIGIBLE_METRICS and not row.get('category_dimension')]
    mode_order = {'all': 0, 'early_in_person': 1, 'mail': 2}
    options.sort(key=lambda row: (ELIGIBLE_METRICS.index(row['metric']), mode_order.get(row['mode'], 3), row['mode']))
    fallback = None
    for selection in options:
        query = ResearchQuery(state=state, cycle=cycle, baseline=2022, metric=selection['metric'], mode=selection['mode'],
                              revision=revision, as_of=cutoff, time_basis='reported', alignment='days_to_election')
        view = workspace(database, query)
        if fallback is None or (fallback['summary']['total'] is None and view['summary']['total'] is not None):
            fallback = view
        county = [r for r in view['geographies'] if r['type'] == 'county' and (r.get('canonical_id') or '').startswith('county:')]
        if len(county) >= 2 and view['summary']['total'] and view['summary']['latest_date'] and (date.fromisoformat(cutoff[:10])-date.fromisoformat(view['summary']['latest_date'])).days <= 7:
            return view
    return fallback


def _call(database, race, revision, cutoff, cycle, histories, rejected, validation):
    state = race['state']
    reference = weighted_reference(histories.get(state, []), cycle, special=race['special'])
    reference['source_refs'] = _refs([ref for r in reference['cycles'] for ref in r['source_refs']])
    ev = _early_view(database, state, revision, cutoff, cycle)
    sources_refs = list(reference['source_refs'])
    early = {'total': None, 'date': None, 'metric': None, 'metric_label': 'No compatible reported early-ballot measure',
        'mode': None, 'source_refs': [], 'coverage': {}, 'available': False}
    tilt = {'available': False, 'tilt_pp': None, 'adjustment_pp': 0.0, 'coefficient': EV_COEFFICIENT, 'matched_areas': 0,
        'coverage_pct': 0, 'reference_kind': 'unavailable', 'same_stage': False, 'rows': [],
        'description': 'No compatible geographic early-ballot distribution is available.'}
    warnings, explanation = [], []
    composition = []
    if ev:
        latest_points = [r for r in ev['series'] if r['cycle'] == cycle]
        latest_ids = set(max(latest_points, key=lambda r: r['date']).get('observation_ids', [])) if latest_points else set()
        latest_ids.update(i for r in ev['geographies'] for i in r.get('observation_ids', []))
        early_refs = _refs([{'snapshot_id': o['snapshot_id'], 'source_id': o['source_id'], 'observation_id': o['id'], 'revision': o['revision']}
            for o in ev['observations'] if o['id'] in latest_ids and o['cycle'] == cycle and o['metric'] == ev['query']['metric'] and o['mode'] == ev['query']['mode']])
        sources_refs += early_refs
        early = {'total': ev['summary']['total'], 'date': ev['summary']['latest_date'], 'metric': ev['query']['metric'],
            'metric_label': ev['summary']['metric_label'], 'mode': ev['query']['mode'], 'source_refs': early_refs,
            'coverage': ev['coverage'], 'available': ev['summary']['total'] is not None,
            'query': ev['query'], 'unit': ev['summary']['unit'], 'composition_is_marginal': True}
        composition = ev['composition']
        with database.session() as session:
            native_metadata = [r.payload.get('metadata', {}) for r in session.scalars(select(ObservationRecord).where(ObservationRecord.id.in_(latest_ids)))]
        report_date_unverified = any(r.get('underlying_report_date_unverified') for r in native_metadata)
        early['report_date_verified'] = not report_date_unverified
        early['native_date_caveats'] = sorted({str(r.get('report_date_semantics')) for r in native_metadata if r.get('report_date_semantics')})
        if ev['query']['mode'] != 'all':
            warnings.append('The EV adjustment uses only the available '+ev['query']['mode'].replace('_', ' ')+' voting method. It does not represent the complete early-voting electorate.')
        warnings += ev['warnings']
        county = [{'id': r.get('canonical_id') or r['id'], 'name': r['name'], 'value': r['value'], 'date': r['date'],
            'source_refs': [{'observation_id': i, 'source_id': s} for i in r.get('observation_ids', []) for s in r.get('source_ids', [])]}
            for r in ev['geographies'] if r['type'] == 'county' and (r.get('canonical_id') or '').startswith('county:')]
        historic = _county_reference(database, state, revision, min(cycle, int(cutoff[:4]))) if county else None
        if historic:
            from .ev_backtesting import current_same_stage_distribution
            definitions = {r.get('metric_definition', ev['query']['metric']) for r in native_metadata}
            classifications = {r.get('mode_classification') for r in native_metadata}
            prior_stage = current_same_stage_distribution(database, state, revision, cutoff, cycle,
                metric=ev['query']['metric'], mode=ev['query']['mode'], current_date=early['date'],
                metric_definition=next(iter(definitions)) if len(definitions) == 1 else '__incompatible_current_definitions__',
                mode_classification=next(iter(classifications)) if len(classifications) == 1 else '__incompatible_mode_classifications__')
            same_stage = prior_stage['distribution'] if prior_stage else None
            tilt = geographic_tilt(county, historic['rows'], same_stage=same_stage, statewide_total=early['total'])
            tilt.update({'reference_office': historic['office'], 'reference_year': historic['year'],
                'boundary_assumption': 'Canonical current reporting-county IDs are associated with their historical context; no votes are allocated across boundaries. Current-vintage continuity is a modeling assumption, not a verified precinct crosswalk.'})
            if tilt['same_stage']:
                baseline_refs = prior_stage['source_refs']
                tilt.update({'same_stage_source_refs': baseline_refs, 'same_stage_baseline_year': prior_stage['cycle'],
                    'same_stage_baseline_date': prior_stage['date'], 'same_stage_chronology': prior_stage['chronology'],
                    'same_stage_explanation': prior_stage['explanation']})
                sources_refs += baseline_refs
            sources_refs += [ref for r in historic['rows'] for ref in r['source_refs']]
            warnings += historic['warnings']
            if historic['office'] != 'US SENATE':
                warnings.append(f'County {historic["year"]} presidential returns supply geographic context because compatible Senate county returns are unavailable. This is not observed Senate support.')
            if not tilt['same_stage']:
                warnings.append('The reference is a final candidate-vote distribution, not an equivalent day or voting opportunity in a prior early-voting cycle.')
        if report_date_unverified:
            tilt.update({'available': False, 'adjustment_pp': 0.0, 'description': 'The source date is an upload date; the underlying election-authority report date is unverified. It cannot support a dated EV adjustment.'})
            warnings.append('Underlying EV report date is unverified. The displayed source/upload date does not establish when these ballots were reported by the election authority; the point remains historical-only.')
        if early['date'] and (date.fromisoformat(cutoff[:10])-date.fromisoformat(early['date'])).days > 7:
            tilt.update({'available': False, 'adjustment_pp': 0.0, 'description': 'Latest compatible early voting is more than seven days old; a stale geographic mix does not adjust the point call.'})
            warnings.append('Stale EV reporting: latest compatible evidence is more than seven days before the cutoff.')
    margin = reference['margin_pp']
    status = 'ev_informed' if margin is not None and tilt['available'] else ('reference_only' if margin is not None else 'unavailable')
    if margin is not None:
        margin = max(-99, min(99, margin+tilt['adjustment_pp']))
    if race['election_system'] == 'ranked_choice':
        status, margin = 'unavailable', None
        warnings.append('An eventual-winner call is withheld: this election uses ranked-choice voting, current official ballot options are unverified, and the historical compilation does not establish comparable first/final rounds. Major-party subtraction is not a substitute for independent or transfer outcomes.')
    elif reference['cycles']:
        explanation.append(f'The historical Senate reference is {reference["margin_pp"]:+.1f} percentage points Republican minus Democratic, built from '+', '.join(str(y) for y in sorted({r['year'] for r in reference['cycles']}, reverse=True))+'.')
        if tilt['available']:
            explanation.append(f'County EV geography shifts the research point by {tilt["adjustment_pp"]:+.1f} pp (raw geographic tilt {tilt["tilt_pp"]:+.1f} pp × {EV_COEFFICIENT}, capped at ±{MAX_ADJUSTMENT_PP:g} pp).')
        else:
            explanation.append('The point call uses historical Senate returns only. It is explicitly not an EV-informed call: '+tilt['description'])
    if race['election_system'] == 'majority_runoff':
        warnings.append('This election can require a runoff. A D/R party-margin projection does not establish whether a named candidate reaches a majority or wins a later round.')
    if rejected.get(state):
        warnings.append('Some historical contests are excluded because major-party options, independent outcomes, suppression or ranked-choice rounds cannot support a comparable D/R party margin.')
    if reference.get('seat_context_status') == 'regular_context_for_special_contest':
        warnings.append('No recent comparable special-contest history is available; regular Senate contests provide the explicitly labeled reference for this special election. Seat-class and candidate correspondence is unverified.')
    warnings.append('Historical state Senate returns pool different seats, candidates and classes. Current nominees and incumbency are unverified; the projection is not candidate-adjusted.')
    if not reference['cycles']:
        explanation.append('No defensible historical Senate party-margin reference is available. The model does not invent a baseline from an incumbent roster.')
    half_width = max(MIN_SENSITIVITY_HALF_WIDTH_PP, validation.get('historical_error_95_pp') or 0)
    if len({r['year'] for r in reference['cycles']}) < 2:
        half_width = max(half_width, 22)
    if status == 'ev_informed' and not tilt['same_stage']:
        half_width += 3
    direction = 'Unavailable' if margin is None else ('Republican' if margin > 0 else 'Democratic' if margin < 0 else 'Tied')
    label = 'Unavailable — electoral/input limitations' if margin is None else ('R' if margin > 0 else 'D' if margin < 0 else 'Tie')+(f'+{abs(margin):.1f}' if margin else '')
    obs_ids = {i for r in composition for i in r.get('observation_ids', [])}
    if obs_ids:
        with database.session() as session:
            sources_refs += [{'snapshot_id': r.snapshot_id, 'source_id': r.source_id, 'observation_id': r.id, 'revision': r.revision}
                for r in session.scalars(select(ObservationRecord).where(ObservationRecord.id.in_(obs_ids)))]
    sources_refs = snapshot_references(database, sources_refs, revision)
    snapshot_ids = {r['snapshot_id'] for r in sources_refs if r.get('snapshot_id')}
    with database.session() as session:
        snapshots = [{k: v for k, v in record_dict(r).items() if k != 'path'} for r in session.scalars(select(Snapshot).where(Snapshot.id.in_(snapshot_ids)).order_by(Snapshot.id))]
    manifest = {'model_version': MODEL_VERSION, 'dataset_revision': revision, 'as_of': cutoff, 'cycle': cycle,
        'race_id': race['id'], 'state': state, 'deterministic': True, 'simulation_seed': None,
        'margin_definition': 'Republican minus Democratic percentage points; party-level conditional projection, not a named candidate result',
        'formula': 'historical_senate_reference + clip(0.35 * county_geographic_tilt, -5, 5)',
        'coefficient_status': 'explicit_unvalidated_assumption', 'probabilities_published': False,
        'candidate_verification': race['candidate_verification'], 'historical_context_policy': 'Retrospectively collected final returns from years before the cutoff calendar year, not contemporary reporting snapshots.', 'source_snapshots': [{'id': r['id'], 'source_id': r['source_id'], 'sha256': r['sha256'], 'url': r['url']} for r in snapshots],
        'input_sha256': _hash({'reference': reference, 'early_vote': early, 'geographic_tilt': tilt}),
        'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return {'race_id': race['id'], 'state': state, 'state_name': state_info(state)['name'], 'watchlist': race['watchlist'],
        'office': 'US SENATE', 'special': race['special'], 'election_system': race['election_system'],
        'call': {'margin_pp': margin, 'range_low_pp': max(-100, margin-half_width) if margin is not None else None,
            'range_high_pp': min(100, margin+half_width) if margin is not None else None,
            'direction': direction, 'label': label, 'status': status, 'range_label': 'Unvalidated sensitivity range',
            'eventual_winner_probability': None, 'candidate_verification': race['candidate_verification']},
        'evidence': {'early_vote': early, 'historical_reference': reference, 'geographic_tilt': tilt, 'composition': composition,
            'polls': {'count': ev['summary']['poll_count'] if ev else 0, 'role': 'Secondary research link only; excluded from this model.'}},
        'explanation': explanation, 'assumptions': ASSUMPTIONS,
        'warnings': list(dict.fromkeys(warnings)), 'sources': snapshots, 'manifest': manifest}


def _research_diagnostics(item, backtesting):
    """Evidence strength is separate from the probability that a call wins."""
    tilt = item['evidence']['geographic_tilt']
    reference = item['evidence']['historical_reference']
    margin = item['call']['margin_pp']
    raw_tilt = tilt.get('tilt_pp') if tilt.get('available') else 0
    independent = {_case['year'] for _case in backtesting['cases'] if _case['state'] == item['state']}
    from .ev_backtesting import summarize
    comparable_cases = [row for row in backtesting['cases'] if row['state'] == item['state']
                        and row['chronology'] == 'retrospective_report' and row['alignment'] == 'days_to_election'
                        and row['reference_kind'] == 'final_candidate_vote_distribution']
    state_errors = {'historical_reference': summarize(comparable_cases, 'baseline_margin_pp'),
                    'fixed_ev_assumption': summarize(comparable_cases),
                    'scope': 'Retrospective same-stage report study, fixed days-to-election checkpoints, final-result geographic context. This is not a calibrated reliability estimate.'}
    county_dates = {row.get('current_source_date') for row in tilt.get('rows', [])}
    checks = [
        {'label': 'Current EV', 'status': 'supported' if tilt.get('available') else 'limited',
         'detail': tilt['description']},
        {'label': 'Equivalent historical stage', 'status': 'supported' if tilt.get('same_stage') else 'limited',
         'detail': 'Compatible dated historical EV distribution.' if tilt.get('same_stage') else 'Final-result geography or no geographic comparison; same-stage EV behavior is not established.'},
        {'label': 'Independent state validation', 'status': 'limited',
         'detail': f'{len(independent)} historical election cycles for this state; repeated checkpoints do not add independent elections.'},
        {'label': 'Learned conversion', 'status': 'limited',
         'detail': '0.35 remains an explicit assumption. No empirical conversion is promoted from sparse or non-improving held-out evidence.'},
        {'label': 'Candidate/electoral identity', 'status': 'limited', 'detail': item['call']['candidate_verification']},
    ]
    confidence = {'grade': 'limited' if margin is not None else 'withheld',
        'label': 'Low forecasting confidence' if margin is not None else 'Call withheld',
        'reason': 'The direction is an explicit conditional research call. Current EV can describe participation, but limited independent historical validation and unknown candidate-specific behavior prevent a high-confidence electoral forecast.',
        'validated_probability': False, 'independent_validation_cycles': len(independent),
        'historical_error_summary': state_errors,
        'evidence_strength': 'Geographic participation supported' if tilt.get('available') and len(county_dates) == 1 else 'Historical reference only',
        'checks': checks}
    point = reference.get('margin_pp')
    points = [{'coefficient': coefficient,
               'adjustment_pp': max(-MAX_ADJUSTMENT_PP, min(MAX_ADJUSTMENT_PP, coefficient*raw_tilt)),
               'margin_pp': max(-99, min(99, point+max(-MAX_ADJUSTMENT_PP, min(MAX_ADJUSTMENT_PP, coefficient*raw_tilt)))) if point is not None else None}
              for coefficient in (-1., -.5, 0., .175, .35, .7, 1.)]
    stress = [{'label': 'Historical reference only', 'margin_pp': point,
               'delta_pp': point-margin if point is not None and margin is not None else None,
               'explanation': 'Set the assumed EV-to-margin conversion to zero.'}]
    for year in sorted({row['year'] for row in reference.get('cycles', [])}):
        reduced = weighted_reference([row for row in reference['cycles'] if row['year'] != year], item['manifest']['cycle'], special=item['special'])
        projected = max(-99, min(99, reduced['margin_pp']+tilt.get('adjustment_pp', 0))) if reduced['margin_pp'] is not None else None
        stress.append({'label': f'Omit {year} historical outcome', 'margin_pp': projected,
                      'delta_pp': projected-margin if projected is not None and margin is not None else None,
                      'explanation': 'Recompute the recency-weighted reference without this election year. No candidate vote is inferred.'})
    for row in tilt.get('rows', [])[:3]:
        alternative_tilt = raw_tilt-row['contribution_pp']
        projected = point+max(-MAX_ADJUSTMENT_PP, min(MAX_ADJUSTMENT_PP, EV_COEFFICIENT*alternative_tilt)) if point is not None else None
        stress.append({'label': f'Zero {row["name"]} contribution', 'margin_pp': projected,
                      'delta_pp': projected-margin if projected is not None and margin is not None else None,
                      'explanation': 'An explicit contribution stress test: set this area’s geographic-mix contribution to zero. This is not a recomputed electorate or an independent source estimate.'})
    sensitivity = {'parameters': [{'id': 'ev_coefficient', 'label': 'Assumed EV-to-margin conversion', 'default': EV_COEFFICIENT,
                   'min': -1, 'max': 1, 'unit': 'margin pp per geographic tilt pp',
                   'description': 'An unvalidated sensitivity assumption, capped at ±5 margin points. Negative values test reversal; zero removes the EV adjustment.'}],
                   'points': points, 'stress_tests': stress, 'range_kind': 'Unvalidated sensitivity range; no claimed 80%/95% coverage.',
                   'source_sensitivity': 'Only one source-selected statewide/county series enters a call. A producer-exclusion forecast cannot be estimated where no independent compatible producer exists.',
                   'turnout_policy': 'Current early counts cannot imply final turnout or candidate support without a supported same-stage participation model. A prior final total is context, never a current turnout denominator.'}
    if margin is None:
        sensitivity['points'] = []
        sensitivity['stress_tests'] = []
    return {**item, 'confidence': confidence, 'sensitivity': sensitivity}


MAX_RUN_CACHE_BYTES = 32 * 1024 * 1024
_RUN_BUILD_LOCK = RLock()


def _dependency_fingerprint():
    """Cover analysis, parsing, source policy, calendars and canonical joins."""
    files = sorted((PROJECT_ROOT/'backend'/'observatory').rglob('*.py'))
    files += sorted((PROJECT_ROOT/'config').glob('*.json'))
    files += sorted((PROJECT_ROOT/'frontend'/'public'/'geography').rglob('*.geojson'))
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    digest.update(sys.version.encode())
    digest.update(np.__version__.encode())
    return digest.hexdigest()


def _cached_run_read(path, key):
    if not path.exists() or path.stat().st_size > MAX_RUN_CACHE_BYTES:
        return None
    try:
        def reject_constant(value):
            raise ValueError(f'Nonfinite JSON constant: {value}')
        with path.open('rb') as handle:
            raw = handle.read(MAX_RUN_CACHE_BYTES+1)
        if len(raw) > MAX_RUN_CACHE_BYTES:
            return None
        stored = json.loads(raw, parse_constant=reject_constant)
        envelope = stored.pop('cache_envelope', None)
        if not envelope or envelope.get('schema') != 'observatory-frozen-ev-run-v1' or envelope.get('key') != key:
            return None
        if envelope.get('payload_sha256') != _hash(stored):
            return None
        if stored.get('revision') != key['revision'] or stored.get('as_of') != key['cutoff'] or stored.get('cycle') != key['cycle']:
            return None
        if stored.get('model_version') != key['model_version'] or not isinstance(stored.get('calls'), list) or 'backtesting' not in stored:
            return None
        return stored
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _cached_run_write(path, key, result):
    stored = {**result, 'cache_envelope': {'schema': 'observatory-frozen-ev-run-v1', 'key': key, 'payload_sha256': _hash(result)}}
    text = json.dumps(stored, indent=2, allow_nan=False)
    if len(text.encode()) > MAX_RUN_CACHE_BYTES:
        return
    pending = path.with_suffix(f'.json.{os.getpid()}.pending')
    pending.write_text(text)
    pending.replace(path)


def _selected_evidence(database, item, revision, cutoff, cycle):
    from .ev_backtesting import current_turnout_projection, same_stage_research
    early = item['evidence']['early_vote']
    metric, mode = early.get('metric') or 'ballots_cast', early.get('mode') or 'all'
    same_stage = same_stage_research(database, item['state'], revision, cutoff, cycle, metric, mode)
    turnout = current_turnout_projection(database, item['state'], revision, cutoff, cycle, metric, mode)
    return {**item, 'evidence': {**item['evidence'], 'same_stage': same_stage, 'turnout_projection': turnout}}


@lru_cache(maxsize=8)
def _run(database, revision, cutoff, cycle):
    fingerprint = _dependency_fingerprint()
    cache_key = {'revision': revision, 'cutoff': cutoff, 'cycle': cycle,
                 'model_version': MODEL_VERSION, 'dependency_sha256': fingerprint}
    directory = database.settings.data_dir/'model-runs'/'ev-research'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/f'r{revision}-{_hash(cache_key)[:24]}.json'
    cached = _cached_run_read(target, cache_key)
    if cached is not None:
        return cached
    with _RUN_BUILD_LOCK, (directory/'build.lock').open('a') as run_lock:
        # The scheduled worker and web server are separate processes. Serialize
        # cold runs across both, then check for the completed frozen result.
        fcntl.flock(run_lock, fcntl.LOCK_EX)
        cached = _cached_run_read(target, cache_key)
        if cached is not None:
            return cached
        histories, rejected = _senate_history(database, revision)
        # Later final returns cannot enter an earlier cutoff, even when the local
        # archive/revision includes them. Same-calendar-year final returns are
        # conservatively withheld until the following year.
        histories = {state: [r for r in rows if r['year'] < int(cutoff[:4])] for state, rows in histories.items()}
        validation = historical_validation(histories)
        from .ev_backtesting import build_backtesting
        backtesting = build_backtesting(database, revision, cutoff, histories)
        validation = {**validation, 'ev_backtest_cases': len(backtesting['cases']),
            'ev_validation': 'A separate chronology-stratified empirical audit now evaluates the frozen EV assumption against actual historical Senate returns. The historical-reference metrics in this object remain distinct; see backtesting for paired EV errors and sparse-history limits.'}
        calls = [_selected_evidence(database, _research_diagnostics(_call(database, race, revision, cutoff, cycle, histories, rejected, validation), backtesting), revision, cutoff, cycle) for race in races()]
        result = {'revision': revision, 'as_of': cutoff, 'cycle': cycle, 'model_version': MODEL_VERSION, 'calls': calls,
            'validation': validation, 'backtesting': backtesting, 'warnings': ['Experimental conditional party-margin research calls; not validated EV forecasts or winner probabilities.',
                'Actual EV-assumption backtests are separate from historical-reference validation. Sparse independent evidence has not established a transferable learned conversion or calibrated probabilities.',
                'The official 2026 ballot/candidate roster is not yet verified in this local dataset. Party labels do not certify candidate identities.'],
            'manifest': {'model_version': MODEL_VERSION, 'dataset_revision': revision, 'as_of': cutoff,
                'race_count': len(calls), 'ev_informed_races': sum(r['call']['status'] == 'ev_informed' for r in calls),
                'reference_only_races': sum(r['call']['status'] == 'reference_only' for r in calls),
                'unavailable_races': sum(r['call']['status'] == 'unavailable' for r in calls), 'deterministic': True,
                'simulation_seed': None, 'dependency_sha256': fingerprint, 'input_sha256': _hash([r['manifest']['input_sha256'] for r in calls])}}
        # A run is recoverable independently of the browser session. It contains
        # aggregate evidence only and never alters the source/validation revision.
        _cached_run_write(target, cache_key, result)
        # Raw statewide/county source rows can be hundreds of MB. The immutable
        # aggregate run now includes every state's selected diagnostics; retaining
        # those input lists is unnecessary for subsequent research selections.
        from .ev_backtesting import _state_observations
        _state_observations.cache_clear()
        return result


def early_vote_forecasts(database, state='NC', revision=None, as_of=None, cycle=2026):
    ensure_schema(database)
    state = state.upper()
    state_info(state)
    if cycle != 2026:
        raise ValueError('The experimental contest registry currently covers the 2026 Senate universe')
    bound = database.latest_revision() if revision is None else revision
    if not isinstance(bound, int) or isinstance(bound, bool) or not 0 <= bound <= database.latest_revision():
        raise ValueError('Dataset revision is outside the available evidence range')
    cutoff = as_of or local_today()
    ResearchQuery(state=state, revision=bound, as_of=cutoff)
    result = _run(database, bound, cutoff, cycle)
    selected = next((r for r in result['calls'] if r['state'] == state), None)
    return {**result, 'selected': selected,
        'selected_state': state, 'selected_note': None if any(r['state'] == state for r in result['calls']) else 'This state has no scheduled 2026 Senate contest. Its atlas and participation evidence remain available.'}
