"""Compact office-specific evidence desks. No Senate model is relabeled here.

District numbers are identities within a particular election, not geographic
crosswalks. A historical district margin never becomes a current House forecast
without a reviewed cross-vintage match and district-level participation.
"""
from collections import defaultdict
from functools import lru_cache

from sqlalchemy import select

from .atlas.models import BallotOption, Contest, Election, ensure_schema
from .atlas.store import _geographies, _rows
from .db import Snapshot, record_dict
from .domain import ResearchQuery
from .ev_forecast import _valid_party_margin, historical_validation, weighted_reference
from .office_registry import HOUSE_SEATS, SOURCES, race_catalog
from .provenance import snapshot_references
from .registry import state_info
from .settings import local_today

VERSION = 'office-research-1'


def district_number(value, *, at_large=False):
    text = str(value).strip().upper()
    if text in {'STATEWIDE', 'AT LARGE', 'AT-LARGE', 'AL', '0', '00', '000'}:
        return 1 if at_large else None
    try:
        number = int(text)
        return number if number > 0 else None
    except ValueError:
        return None


@lru_cache(maxsize=6)
def _history(database, revision, office):
    level = 'district' if office == 'US HOUSE' else 'state'
    rows = _rows(database, state=None, years=list(range(1976, 2026)), office=office, level=level, revision=revision)
    priorities = {r['contest_id']: (r['payload'].get('source_tier', 9), r['source_id'].startswith('snyder_'), r['source_id']) for r in rows}
    with database.session() as session:
        options = {r.id: record_dict(r) for r in session.scalars(select(BallotOption).where(BallotOption.id.in_({r['option_id'] for r in rows})))}
        contests = {r.id: record_dict(r) for r in session.scalars(select(Contest).where(Contest.id.in_({r['contest_id'] for r in rows})))}
        elections = {r.id: record_dict(r) for r in session.scalars(select(Election).where(Election.id.in_({r['election_id'] for r in contests.values()})))}
    history = defaultdict(list)
    for row in _geographies(rows, options, contests):
        contest = contests[row['contest_id']]
        stage = elections.get(contest['election_id'], {}).get('stage', '').upper()
        if stage not in {'GEN', 'GENERAL', 'GEN RUNOFF'} or contest['payload'].get('special') or (contest.get('magnitude') or 1) != 1:
            continue
        district = district_number(contest['district'], at_large=HOUSE_SEATS[row['state']] == 1) if office == 'US HOUSE' else None
        if office == 'US HOUSE' and district is None:
            continue
        history[(row['state'], district)].append({
            'year': row['year'], 'margin_pp': row['rep_margin_pp'] if _valid_party_margin(row) else None,
            'total_votes': row['total_votes'], 'contest_id': row['contest_id'], 'contest_name': contest['name'],
            'district': contest['district'], 'boundary_vintage': row['boundary_vintage'],
            'geography_level': row['level'], 'geography_id': row['id'],
            'election_system': row['election_system'], 'round': row['round'],
            'source_refs': row['source_refs'], 'options': row['options'],
            'margin_status': 'available' if _valid_party_margin(row) else 'Unsupported D/R comparison; inspect all published options and counting round.',
            '_priority': (0 if stage == 'GEN RUNOFF' else 1, *priorities[row['contest_id']])})
    # Producers spell the same district 1, 01 or 001. Resolve that identity
    # before choosing a complete producer's contest; never merge option rows or
    # count alternate publications as independent historical elections.
    output = {}
    for scope, members in history.items():
        years = defaultdict(list)
        for member in members:
            years[member['year']].append(member)
        output[scope] = []
        for alternatives in years.values():
            chosen = min(alternatives, key=lambda r: (r['_priority'], r['contest_id']))
            output[scope].append({k: v for k, v in chosen.items() if k != '_priority'})
    return output


def reference_for_race(race, history, cycle):
    valid = [r for r in history if r['margin_pp'] is not None]
    reference = weighted_reference(valid, cycle)
    scope = 'same_office_statewide' if race['office'] == 'GOVERNOR' else 'same_number_historical_district'
    reference['description'] = ('Recency-weighted, same-election-type governor history; candidates and current conditions are not modeled.'
        if race['office'] == 'GOVERNOR' else
        'Same-number district history only. Boundaries are election-specific; this is not a current-district reference or forecast.')
    if race['office'] == 'US HOUSE':
        # Even at-large seats need an office-specific EV model. Historic numbers
        # and same-election-type weights alone do not validate one.
        reference['margin_pp'] = None
    reference['scope'] = scope
    return reference


def office_research(database, office='GOVERNOR', revision=None, as_of=None, cycle=2026):
    ensure_schema(database)
    if office not in {'GOVERNOR', 'US HOUSE'} or cycle != 2026:
        raise ValueError('This office research desk supports 2026 GOVERNOR and US HOUSE; Senate retains its existing model interface')
    revision = database.latest_revision() if revision is None else revision
    if not isinstance(revision, int) or isinstance(revision, bool) or not 0 <= revision <= database.latest_revision():
        raise ValueError('Dataset revision is outside the available evidence range')
    cutoff = as_of or local_today()
    ResearchQuery(state='OH', revision=revision, as_of=cutoff)
    return _desk(database, office, revision, cutoff, cycle)


@lru_cache(maxsize=6)
def _desk(database, office, revision, cutoff, cycle):
    histories = _history(database, revision, office)
    before_cutoff = {key: [r for r in rows if r['year'] < min(cycle, int(cutoff[:4]))] for key, rows in histories.items()}
    validation = None
    if office == 'GOVERNOR':
        validation = historical_validation({state: [r for r in rows if r['margin_pp'] is not None]
            for (state, _), rows in before_cutoff.items()})
        validation['office'] = office
        validation['methodology'] = 'Retrospective rolling-origin governor reference: earlier governor results of the same election type only. This tests a historical baseline, not an early-vote forecast. Contemporary archive availability is not established.'
        validation['warnings'] = [text.replace('Senate', 'governor') for text in validation['warnings']]
    calls = []
    for race in race_catalog(office):
        rows = list(before_cutoff.get((race['state'], race['district']), []))
        # One exact contest/producer already selected by the shared result store.
        # Multiple records in the same year stay separate in the visible history.
        rows.sort(key=lambda r: (r['year'], r['contest_id']))
        reference = reference_for_race(race, rows, cycle)
        recent = [r for r in rows if r['year'] >= cycle-12]
        latest = rows[-1] if rows else None
        warnings = [race['candidate_verification'],
            'Participation records do not identify candidate votes. Registration, race, religion and past party context cannot reveal an individual ballot.',
            'No held-out same-stage EV validation has been completed for this office. No EV-adjusted margin or winner probability is published.']
        if office == 'US HOUSE':
            warnings.append('District numbers can refer to different boundaries in different years, including changes after 2024. No verified 2026 crosswalk is installed. Statewide or county EV is never allocated into these districts.')
        if race['election_system'] != 'plurality':
            warnings.append('The actual election system requires ranked choices or a possible runoff. First-round D/R shares do not establish the eventual winner.')
        if not rows:
            warnings.append('No eligible general-election returns at this office and geography are loaded at the pinned revision. Source coverage is incomplete, not a tied race.')
        point = reference['margin_pp'] if race['election_system'] == 'plurality' else None
        # These points are explicitly history, never promoted as an EV forecast.
        direction = ('Republican' if point > 0 else 'Democratic' if point < 0 else 'Even') if point is not None else None
        if latest:
            label = 'U.S. House' if office == 'US HOUSE' else 'governor'
            finding = f"Latest archived {label} result: {latest['year']}, {latest['total_votes']:,.0f} candidate votes. "
            finding += ('The same-type governor reference is historical context, not a prediction from current early voters.' if office == 'GOVERNOR' else
                'Open the candidate shares and election-specific district history below. A current House call awaits verified district boundaries and office-specific validation.')
        else:
            finding = 'The scheduled race is available for research. Historical returns for this office are not yet loaded; state EV remains separate participation evidence.'
        calls.append({**race, 'race_id': race['id'], 'history': recent, 'history_range': [rows[0]['year'], rows[-1]['year']] if rows else [],
            'latest_result': latest, 'historical_reference': reference,
            'call': {'status': 'reference_only' if point is not None else 'unavailable', 'margin_pp': point,
                'direction': direction, 'eventual_winner_probability': None, 'ev_adjustment_pp': None,
                'label': 'Historical governor context only' if point is not None else 'EV direction not established'},
            'finding': finding, 'warnings': warnings,
            'validation': {'office': office, 'ev_model_promoted': False, 'ev_backtest_cases': 0,
                'reason': 'Senate backtest scores and coefficients are not transferred to House or governor races.'}})
    references = snapshot_references(database, calls, revision)
    ids = {r['snapshot_id'] for r in references if r.get('snapshot_id') is not None}
    with database.session() as session:
        sources = [{'id': s.id, 'snapshot_id': s.id, 'source_id': s.source_id, 'url': s.url,
            'sha256': s.sha256, 'retrieved_at': s.retrieved_at} for s in session.scalars(
                select(Snapshot).where(Snapshot.id.in_(ids), Snapshot.revision <= revision))]
    return {'model_version': VERSION, 'revision': revision, 'as_of': cutoff, 'cycle': cycle, 'office': office,
        'calls': calls, 'sources': sources, 'registry_sources': SOURCES, 'validation': validation,
        'coverage': {'scheduled_races': len(calls), 'states': len({r['state'] for r in calls}),
            'races_with_history': sum(r['latest_result'] is not None for r in calls),
            'states_with_history': len({r['state'] for r in calls if r['latest_result']}), 'ev_forecasts': 0},
        'scope_note': 'Regular 2026 seats across the 50 states. Territories, delegates and separately scheduled special House elections are outside this registry. Governor history reflects loaded official records only.',
        'chronology_note': 'Retrospective final-return archive, bounded by dataset revision and excluding cutoff-year or later finals. It does not prove contemporary publication availability.',
        'state_names': {s: state_info(s)['name'] for s in HOUSE_SEATS}}
