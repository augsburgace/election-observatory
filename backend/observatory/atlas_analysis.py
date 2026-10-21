"""Descriptive calculations over collected results, shared by research clients."""
from __future__ import annotations

from .atlas import context_query, result_query


def result_analysis(database, **query):
    view = result_query(database, **query)
    rows = view['geographies']
    total = view['summary']['total_votes']
    ranked = []
    concentration = [{'geographies_pct': 0, 'candidate_votes_pct': 0}]
    cumulative = 0
    if total:
        for index, row in enumerate(sorted(rows, key=lambda r: -(r['total_votes'] or 0))):
            cumulative += row['total_votes']
            share = row['total_votes'] / total * 100
            ranked.append({'id': row['id'], 'name': row['name'], 'votes': row['total_votes'],
                           'share_pct': share, 'cumulative_share_pct': cumulative / total * 100,
                           'source_refs': row['source_refs']})
            concentration.append({'geographies_pct': (index + 1) / len(rows) * 100,
                                  'candidate_votes_pct': cumulative / total * 100})
    context = context_query(database, state=query.get('state'), metric='population', revision=view['revision'])
    populations = {r['geography_id']: r for r in context['estimates']}
    scatter = [{'id': r['id'], 'name': r['name'], 'candidate_votes': r['total_votes'],
                'population_estimate': populations[r['id']]['estimate'], 'population_moe': populations[r['id']]['moe'],
                'period_start': populations[r['id']]['period_start'], 'period_end': populations[r['id']]['period_end'],
                'source_refs': r['source_refs'],
                'context_source_refs': [{'snapshot_id': populations[r['id']]['snapshot_id'],
                                         'context_id': populations[r['id']]['id'],
                                         'revision': populations[r['id']]['revision']}]}
               for r in rows if r['id'] in populations and populations[r['id']]['estimate'] is not None]
    options = view.get('summary', {}).get('options', [])
    if not options and len({r['contest_id'] for r in rows}) == 1:
        totals = {}
        for row in rows:
            for option in row['options']:
                item = totals.setdefault(option['id'], {'id': option['id'], 'name': option['name'], 'party': option['party'], 'votes': 0})
                item['votes'] += option['votes'] or 0
        options = [{**o, 'share_pct': o['votes'] / total * 100 if total else None} for o in totals.values()]
    options.sort(key=lambda o: -(o['votes'] or 0))
    findings = []
    if total:
        findings.append({'id': 'volume', 'text': f"{total:,.0f} candidate votes are represented across {len(rows):,} {query.get('geography_level', 'reporting')} areas in this view.",
                         'source_refs': [ref for row in rows for ref in row['source_refs']]})
    if ranked:
        top = ranked[0]
        findings.append({'id': 'concentration', 'text': f"{top['name']} accounts for {top['share_pct']:.1f}% of the candidate votes in the displayed geographic coverage.", 'source_refs': top['source_refs']})
    if query.get('state'):
        scope = f"{query['state']} · {query.get('year', 2024)} {query.get('office', 'PRESIDENT')}"
    else:
        scope = f"United States · {query.get('year', 2024)} {query.get('office', 'PRESIDENT')}"
    return {'revision': view['revision'], 'query': view['query'], 'scope': scope, 'unit': 'candidate votes',
            'findings': findings, 'rankings': ranked, 'concentration': concentration,
            'candidate_distribution': options, 'population_context_scatter': scatter,
            'definitions': {'concentration': 'Share of candidate votes accumulated by reporting areas ranked from largest to smallest.',
                'scatter': 'Final candidate votes versus ACS resident population; this is geographic context, not voter demographics or a turnout rate.',
                'candidate_distribution': 'Shares of candidate votes. Multi-seat, ranked-choice, and ballot-measure qualifications remain attached to each contest.'},
            'coverage': view['coverage'],
            'sources': list({s['id']: s for s in [*view['sources'], *context['sources']]}.values()),
            'warnings': view['warnings'] + context['warnings']}
