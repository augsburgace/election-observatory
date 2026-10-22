"""Readable, reproducible checks of a conditional EV call, without outside signals."""
from __future__ import annotations

import math

from .election_context import election_type
from .ev_backtesting import summarize

METHOD_REFERENCES = [
    {'title': 'Census: turnout and early voting in the 2022 midterms',
     'url': 'https://www.census.gov/newsroom/press-releases/2024/congressional-election-voting-report.html',
     'lesson': 'Even midterms differ: both turnout and the share voting before Election Day changed between 2018 and 2022. Match election type, then inspect method and calendar changes.'},
    {'title': 'EAC: 2024 election administration findings',
     'url': 'https://www.eac.gov/sites/default/files/2025-06/EAVS_2024_One_Sheet_06_30_25_508.pdf',
     'lesson': 'Early in-person and Election Day are separate voting methods. A rise in one can reflect a timing shift instead of higher final turnout.'},
    {'title': 'Pew: validated-voter voting-method research',
     'url': 'https://www.pewresearch.org/politics/2025/08/22/majority-of-americans-continue-to-back-expanded-early-voting-voting-by-mail-voter-id/',
     'lesson': 'Party-method relationships change. Do not hard-code Republicans as Election Day voters or Democrats as mail voters. This methodological reference supplies no votes or polling adjustment to the model.'},
]


def validate_call_arithmetic(calls: list[dict], cycle: int) -> dict:
    """Fail before caching/publication if model roles and arithmetic disagree."""
    for item in calls:
        point, evidence = item['call'], item['evidence']
        history, tilt = evidence['historical_reference'], evidence['geographic_tilt']
        cycles = history.get('cycles', [])
        if any(election_type(row.get('election_cycle', row['year'])) != election_type(cycle) for row in cycles):
            raise ValueError('Forecast audit: mixed election environments entered the historical point')
        if cycles and not math.isclose(sum(row['weight'] for row in cycles), 1, abs_tol=1e-9):
            raise ValueError('Forecast audit: historical weights do not sum to one')
        adjusted = point['status'] == 'ev_informed'
        if adjusted and not (tilt.get('available') and tilt.get('same_stage') and tilt.get('adjustment_eligible')):
            raise ValueError('Forecast audit: an EV call lacks an eligible same-stage comparison')
        shift = tilt.get('adjustment_pp') or 0
        if not adjusted and shift != 0:
            raise ValueError('Forecast audit: historical context cannot move the EV point')
        if point['margin_pp'] is not None:
            baseline = history.get('margin_pp')
            expected = max(-99, min(99, baseline+shift)) if baseline is not None else None
            if expected is None or not math.isfinite(point['margin_pp']) or not math.isclose(point['margin_pp'], expected, abs_tol=1e-9):
                raise ValueError('Forecast audit: displayed point does not reconcile to its components')
        if point.get('eventual_winner_probability') is not None:
            raise ValueError('Forecast audit: this model has no validated winner probability')
    return {'status': 'passed', 'races': len(calls), 'same_type_references': True,
        'eligible_same_stage_adjustments': True, 'point_arithmetic': True, 'winner_probabilities_withheld': True}


def audit_call(call: dict, backtesting: dict, cycle: int) -> dict:
    evidence, point = call['evidence'], call['call']
    reference, tilt, early = (evidence[key] for key in ('historical_reference', 'geographic_tilt', 'early_vote'))
    kind = election_type(cycle)
    compatible = [row for row in backtesting.get('cases', []) if row['state'] == call['state']
        and election_type(row['year']) == kind and row['reference_kind'] == 'same_stage_early_vote'
        and row['chronology'] == 'retrospective_report' and row['alignment'] == 'days_to_election'
        and row.get('metric') == early.get('metric') and row.get('mode') == early.get('mode')]
    metrics = {'historical_reference': summarize(compatible, 'baseline_margin_pp'),
               'ev_assumption': summarize(compatible)}
    base_error, ev_error = (metrics[key]['margin_mae_pp'] for key in ('historical_reference', 'ev_assumption'))
    improvement = base_error - ev_error if base_error is not None and ev_error is not None else None
    input_cycles = sorted({row['year'] for row in reference.get('cycles', [])})
    eligible = point['status'] == 'ev_informed'
    checks = [
        {'label': 'Same election environment', 'passed': bool(input_cycles),
         'detail': f'{kind.replace("_", " ").title()} reference: ' + (', '.join(map(str, input_cycles)) or 'no eligible earlier outcomes') + '. Other election types cannot move the point.'},
        {'label': 'Same stage and voting measure', 'passed': eligible,
         'detail': (tilt.get('same_stage_explanation') or tilt['description'])},
        {'label': 'Statewide geographic reconciliation',
         'passed': bool(tilt.get('available')) and (tilt.get('statewide_coverage_pct') or 0) >= 80,
         'detail': f"{tilt.get('matched_areas', 0)} matched reporting areas. " +
             (f"{tilt['statewide_coverage_pct']:.1f}% of the reported statewide measure is matched." if tilt.get('statewide_coverage_pct') is not None else 'Matched statewide coverage is not established.')},
        {'label': 'Added predictive value established', 'passed': False,
         'detail': f"{metrics['ev_assumption']['independent_state_cycles']} state/election outcomes in the matching historical stratum. No production EV conversion or win probability has passed validation."},
    ]
    state_note = {
        'OH': 'Ohio affiliation reflects partisan-primary participation, not a declared party at registration or a general-election vote. Mail and early in-person must keep their own dated histories.',
        'TX': 'Texas has no party registration. Primary-history groups are participation cohorts. A large final early-vote share can narrow the remaining turnout scenario, but does not disclose early candidate choices or guarantee a winner.',
        'AK': 'Alaska uses native reporting districts and ranked-choice voting. First-choice party margins cannot establish the eventual winner.',
        'ME': 'Maine ranked-choice transfers and standing absentee requests require separate treatment. Requests do not count as returned votes.',
    }.get(call['state'], 'Use this state’s published method and party definitions. National party-method averages cannot substitute for its own comparable history.')
    return {'version': 'ev-call-audit-1', 'election_type': kind,
        'point_role': 'Conditional same-stage EV research point' if eligible else 'Historical context only' if point['margin_pp'] is not None else 'Call unavailable',
        'conclusion': ('A compatible EV comparison contributes through an explicit, unvalidated conversion. The evidence supports investigating this direction, not declaring a validated winner.' if eligible else
                       'Incoming early-vote evidence does not support a like-for-like margin adjustment here. The displayed historical point must not be read as an early-vote prediction.'),
        'components': [
            {'label': 'Same-type Senate history', 'margin_pp': reference.get('margin_pp'), 'role': 'historical'},
            {'label': 'Eligible EV adjustment', 'margin_pp': tilt.get('adjustment_pp') or 0, 'role': 'assumed'},
            {'label': 'Displayed research point', 'margin_pp': point['margin_pp'], 'role': 'conditional' if eligible else 'historical'},
        ], 'checks': checks, 'validation': {**metrics, 'mae_improvement_pp': improvement,
            'scope': 'Same state, election type, voting measure/method, days-to-election alignment and same-stage geographic feature. Historical reports were recovered retrospectively; repeated checkpoints share a state/election weight.',
            'independent_cycles': sorted({row['year'] for row in compatible}), 'promoted': False},
        'state_note': state_note, 'interpretation': [
            'More ballots now can mean votes moved earlier, rather than more people voting overall.',
            'Mail returns, early in-person ballots, requests and accepted ballots are different quantities.',
            'County partisanship, registration and primary history do not identify candidate votes. Race, religion and propensity cannot be inferred from a place’s population.',
            '2020 is a pandemic-era comparison. Even within presidential cycles, rule and method changes must be checked.',
            'A narrow spread between historical turnout analogues excludes model error and is not a confidence interval.',
        ], 'references': METHOD_REFERENCES,
        'state_reference': ({'title': 'EAC: Ohio affiliation definition', 'url': 'https://www.eac.gov/ohio-voter-info'} if call['state'] == 'OH' else
                            {'title': 'EAC: Texas affiliation definition', 'url': 'https://www.eac.gov/taxonomy/term/18371'} if call['state'] == 'TX' else None)}
