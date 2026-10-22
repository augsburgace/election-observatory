"""One pinned document model drives the composer preview, vector PDF and research ZIP.

Figures contain renderer-neutral drawing primitives. Geography comes from archived
Census files, and candidate votes, participation and resident estimates never share
a denominator or an implicit aggregation. The package stores the layout as evidence.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from html import escape
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .atlas import context_query, result_query
from .atlas_reporting import party_color, report_footer
from .db import ObservationRecord, Snapshot, record_dict
from .domain import ResearchQuery, utc_now
from .geography import BOUNDARY_ROOT, canonicalize_observation
from .registry import METRICS, state_info
from .service import workspace
from .settings import PROJECT_ROOT

SCHEMA = 'observatory-composed-report-v1'
ACS_RELEASE = {'period_end': '2024-12-31', 'release_date': '2026-01-29',
    'source_url': 'https://www.census.gov/programs-surveys/acs/news/data-releases/2024/release.html',
    'basis': 'Census revised 2020-2024 ACS 5-year public release schedule; original December 2025 plan was superseded.'}
TEAL = '#087f8c'
VIOLET = '#8552b6'
GOLD = '#b87b0c'
NAVY = '#16324c'
MUTED = '#52687d'
CYCLE_COLORS = {2026: TEAL, 2024: VIOLET, 2022: GOLD, 2020: '#39946c', 2018: '#60748f'}
SECTION_CATALOG = [
    {'id': 'ev_call', 'title': 'Experimental Senate EV-led research call', 'kind': 'ev_forecast', 'description': 'The exact conditional margin, turnout assumptions, paired historical evaluation and validation limits.'},
    {'id': 'summary', 'title': 'Research findings', 'kind': 'summary', 'description': 'What the selected evidence supports, with exact scope and dates.'},
    {'id': 'ev_trajectory', 'title': 'Participation through time', 'kind': 'participation', 'description': 'Actual observation steps and compatible historical alignment.'},
    {'id': 'ev_changes', 'title': 'Newly reported ballots', 'kind': 'participation', 'description': 'Snapshot changes, including negative revisions; not voting-event dates.'},
    {'id': 'ev_map', 'title': 'Participation geography', 'kind': 'participation', 'description': 'Area-proportional symbols on verified county boundaries.'},
    {'id': 'ev_places', 'title': 'Geographic contributors', 'kind': 'participation', 'description': 'Selected reporting-area totals and distinct trajectories.'},
    {'id': 'ev_composition', 'title': 'Published composition', 'kind': 'participation', 'description': 'Only directly published groups; no invented joint filters.'},
    {'id': 'results_map', 'title': 'Historical results map', 'kind': 'results', 'description': 'Original contest returns, with numeric legends and boundary vintage.'},
    {'id': 'results_distribution', 'title': 'Candidates and ballot options', 'kind': 'results', 'description': 'Published response distribution and full option lookup.'},
    {'id': 'historical_trend', 'title': 'Long-run historical context', 'kind': 'results', 'description': 'Statewide presidential party shares across collected cycles.'},
    {'id': 'comparison', 'title': 'Current and historical comparison', 'kind': 'results', 'description': 'Paired original returns; differences require compatible boundaries and rounds.'},
    {'id': 'context_map', 'title': 'Resident context map', 'kind': 'context', 'description': 'ACS estimates and their period; these are not voter demographics.'},
    {'id': 'context_ranking', 'title': 'Population and household context', 'kind': 'context', 'description': 'Ranked estimates with published 90% margins of error.'},
    {'id': 'polls', 'title': 'Original polling inventory', 'kind': 'participation', 'description': 'Fieldwork, population, sample and complete reported responses.'},
    {'id': 'evidence', 'title': 'Sources, definitions and limitations', 'kind': 'evidence', 'description': 'Archived source hashes, boundary files and reproducibility instructions.'},
]
SECTION_LOOKUP = {s['id']: s for s in SECTION_CATALOG}


def _poll_responses(estimates: list[dict]) -> str:
    """Readable published options; raw estimate objects remain in the evidence package."""
    responses = []
    for estimate in estimates:
        name = estimate.get('name') or estimate.get('candidate') or 'Unnamed published response'
        party = f" ({estimate['party']})" if estimate.get('party') else ''
        if estimate.get('suppressed'):
            value = 'Suppressed'
        elif estimate.get('reported') not in (None, ''):
            value = str(estimate['reported'])
        elif estimate.get('value') is not None:
            value = f"{estimate['value']:g}%" if isinstance(estimate['value'], (int, float)) else str(estimate['value'])
        else:
            value = 'Not reported'
        responses.append(f'{name}{party}: {value}')
    return '; '.join(responses) or 'No published response estimates'


TEMPLATES = [
    {'id': 'ev_senate', 'label': 'Senate EV-led forecast dossier', 'sections': ['ev_call', 'summary', 'ev_trajectory', 'ev_changes', 'ev_map', 'ev_composition', 'polls', 'evidence']},
    {'id': 'state', 'label': 'Complete state research dossier', 'sections': ['summary', 'ev_trajectory', 'ev_changes', 'ev_map', 'ev_places', 'ev_composition', 'results_map', 'results_distribution', 'historical_trend', 'comparison', 'context_ranking', 'polls', 'evidence']},
    {'id': 'daily', 'label': 'Early-voting daily brief', 'sections': ['summary', 'ev_trajectory', 'ev_changes', 'ev_map', 'ev_places', 'evidence']},
    {'id': 'history', 'label': 'Historical election comparison', 'sections': ['summary', 'results_map', 'results_distribution', 'historical_trend', 'comparison', 'evidence']},
    {'id': 'context', 'label': 'Resident context and geography', 'sections': ['summary', 'context_map', 'context_ranking', 'evidence']},
    {'id': 'polls', 'label': 'Polling methodology review', 'sections': ['summary', 'polls', 'evidence']},
    {'id': 'custom', 'label': 'Custom research packet', 'sections': ['summary', 'results_map', 'ev_trajectory', 'context_map', 'evidence']},
]


class ReportSection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    enabled: bool = True
    caption: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def known_section(self):
        if self.id not in SECTION_LOOKUP:
            raise ValueError('Unknown report section')
        return self


class ResultsScope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    year: int = Field(default=2024, ge=1700, le=2100)
    baseline: int | None = Field(default=2020, ge=1700, le=2100)
    office: str = Field(default='PRESIDENT', max_length=150)
    contest_id: str | None = Field(default=None, max_length=500)
    geography_level: Literal['state', 'county', 'district', 'municipality', 'precinct'] = 'county'
    geography_ids: list[str] = Field(default_factory=list, max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=200)


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='Election research dossier', min_length=1, max_length=250)
    template: str = Field(default='state', max_length=50)
    query: ResearchQuery
    results: ResultsScope = Field(default_factory=ResultsScope)
    context_metric: Literal['population', 'median_age', 'median_household_income'] = 'population'
    map_metric: Literal['dem_margin_pp', 'total_votes'] = 'dem_margin_pp'
    sections: list[ReportSection] = Field(default_factory=lambda: [ReportSection(id=s) for s in next(t for t in TEMPLATES if t['id'] == 'state')['sections']], min_length=1, max_length=30)
    notes: str = Field(default='', max_length=30000)
    include_notes: bool = False

    @model_validator(mode='after')
    def unique_sections(self):
        ids = [s.id for s in self.sections]
        if len(set(ids)) != len(ids):
            raise ValueError('A report section can appear only once')
        if not any(s.enabled for s in self.sections):
            raise ValueError('Choose at least one report section')
        return self


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _public(value):
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if k not in {'path', 'archive_path', 'directory'}}
    if isinstance(value, list):
        return [_public(v) for v in value]
    return value


def _text(x, y, text, color=NAVY, size=12, anchor='start'):
    return {'type': 'text', 'x': x, 'y': y, 'text': str(text), 'color': color, 'size': size, 'anchor': anchor}


def _line(x1, y1, x2, y2, color='#d9e3eb', width=1):
    return {'type': 'line', 'points': [[x1, y1], [x2, y2]], 'color': color, 'width': width}


def _fmt(value, digits=0):
    return 'Unavailable' if value is None else f'{value:,.{digits}f}'


def _figure(title, explanation, primitives, height=330, **extra):
    return {'title': title, 'what': explanation, 'width': 900, 'height': height, 'primitives': primitives, **extra}


def _bars(title, rows, unit, color=TEAL):
    rows = [r for r in rows if r.get('value') is not None][:16]
    if not rows:
        return None
    maximum = max(abs(r['value']) for r in rows) or 1
    primitives = []
    for i, row in enumerate(rows):
        y = 26 + 28 * i
        primitives += [_text(0, y+12, row['name'][:35]),
                       {'type': 'rect', 'x': 275, 'y': y, 'width': abs(row['value']) / maximum * 410,
                        'height': 18, 'color': row.get('color', color)},
                       _text(700, y+13, row.get('label') or _fmt(row['value']), size=11)]
    return _figure(title, f'Largest {len(rows)} displayed groups; values in {unit}. The full evidence table follows.', primitives,
                   max(120, 28 * len(rows) + 55), unit=unit)


def _trajectory(title, groups, unit, xlabel='Days relative to Election Day (0 = Election Day)', step=True):
    available = [(label, [(x, y) for x, y in points if x is not None and y is not None], color) for label, points, color in groups if any(x is not None and y is not None for x, y in points)]
    values = [p for _, points, _ in available for p in points]
    if not values:
        return None
    xmin, xmax = min(p[0] for p in values), max(p[0] for p in values)
    ymin, ymax = min(0, min(p[1] for p in values)), max(p[1] for p in values)
    if ymax == ymin:
        ymax = ymin + 1
    ymax += (ymax-ymin)*.09
    primitives = []
    for fraction in (0, .25, .5, .75, 1):
        y = 270 - fraction * 205
        primitives += [_line(90, y, 835, y), _text(80, y+4, _fmt(ymin+fraction*(ymax-ymin)), size=11, anchor='end')]
    for index, (label, points, color) in enumerate(available):
        xy = []
        for x, value in sorted(points):
            px, py = 90+(x-xmin)/max(1, xmax-xmin)*745, 270-(value-ymin)/(ymax-ymin)*205
            if xy and step:
                xy.append([px, xy[-1][1]])
            xy.append([px, py])
        primitives.append({'type': 'polyline', 'points': xy, 'color': color, 'width': 2.8})
        primitives += [_line(95+index%4*195, 22+index//4*18, 112+index%4*195, 22+index//4*18, color, 3),
                       _text(118+index%4*195, 26+index//4*18, label[:25], color, 11)]
    primitives += [_text(90, 294, f'{xmin:g}'), _text(835, 294, f'{xmax:g}', anchor='end'),
                   _text(460, 320, xlabel, MUTED, 12, 'middle')]
    return _figure(title, f'{unit}. Actual observations only. '+('Step segments carry the last observed value; they do not invent intermediate reports.' if step else 'Markers are connected for orientation; intermediate estimates are not published observations.'), primitives, 340, unit=unit)


def _map_features(state, level):
    name = f'{state}.geojson' if level == 'county' else 'states.geojson'
    path = BOUNDARY_ROOT/name
    if not path.exists() or level not in {'county', 'state'}:
        return [], []
    raw = json.loads(path.read_text())
    features = raw.get('features', [])
    if state and level == 'state':
        features = [f for f in features if f.get('properties', {}).get('STUSPS') == state]
    return features, [{'file': f'geography/{name}', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'vintage': '2024', 'source': 'US Census Bureau cartographic boundaries'}]


def _rings(feature):
    geometry = feature.get('geometry') or {}
    return geometry.get('coordinates', []) if geometry.get('type') == 'Polygon' else [ring for polygon in geometry.get('coordinates', []) for ring in polygon]


def _map(title, state, level, rows, metric, unit, boundary_files, *, features_override=None, boundaries_override=None, vintage='2024'):
    features, boundaries = _map_features(state, level) if features_override is None else (features_override, boundaries_override or [])
    if not features:
        return None
    boundary_files.extend(boundaries)
    # A fixed local projection over the actual archived geometry. Alaska is
    # unwrapped around -150 degrees to preserve its dateline-spanning islands.
    center = -150 if state == 'AK' else sum(p[0] for f in features for ring in _rings(f) for p in ring) / max(1, sum(len(r) for f in features for r in _rings(f)))
    def project(p):
        lon = p[0]
        while lon-center > 180:
            lon -= 360
        while lon-center < -180:
            lon += 360
        return (lon * math.cos(math.radians(40 if state != 'AK' else 60)), -p[1])
    points = [project(p) for f in features for ring in _rings(f) for p in ring]
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    scale = min(820/max(x1-x0, .01), 345/max(y1-y0, .01))
    def screen(p):
        x, y = project(p)
        return [40+(820-(x1-x0)*scale)/2+(x-x0)*scale, 20+(345-(y1-y0)*scale)/2+(y-y0)*scale]
    lookup = {r['id']: r for r in rows}
    values = [r['value'] for r in rows if r.get('value') is not None]
    maximum = max(values or [1]) or 1
    is_margin = metric == 'dem_margin_pp'
    colors = ['#b52342', '#d15b6a', '#e7a1a8', '#f2e6e7', '#adc6ec', '#6197d4', '#1e5ca6'] if is_margin else ['#e2f3ed', '#b8e4d7', '#78c7b9', '#36a59c', '#087f8c']
    bins = [-30, -15, -5, 5, 15, 30] if is_margin else [maximum*f for f in (.2, .4, .6, .8)]
    volume = metric == 'volume'
    primitives, populated, unmatched = [], 0, []
    for feature in features:
        p = feature['properties']
        identifier = str(feature.get('id') or p.get('id')) if level == 'precinct' else ('county:'+str(p['GEOID']) if level == 'county' else 'state:'+p['STUSPS'])
        row = lookup.get(identifier)
        value = row.get('value') if row else None
        index = sum(value > b for b in bins) if value is not None else 0
        fill = '#eff3f6' if volume or value is None else colors[index]
        if value is not None:
            populated += 1
        projected_rings = []
        for ring in _rings(feature):
            vertices = [screen(point) for point in ring]
            # Preserve ring topology while omitting redundant subpixel vertices.
            kept = [point for i, point in enumerate(vertices) if i == 0 or i == len(vertices)-1 or math.dist(point, vertices[i-1]) > .25]
            if len(kept) > 2:
                projected_rings.append(kept)
        primitives.append({'type': 'polygon', 'rings': projected_rings, 'color': fill, 'stroke': '#8797a5', 'width': .45,
                           'geography_id': identifier, 'value': value})
        if volume and value is not None and value > 0 and projected_rings:
            outer = max(projected_rings, key=len)
            # The position is a display centroid; area (r squared), not radius,
            # represents value. No allocation into smaller places occurs.
            cx, cy = sum(x for x, _ in outer)/len(outer), sum(y for _, y in outer)/len(outer)
            primitives.append({'type': 'circle', 'x': cx, 'y': cy, 'r': 24*math.sqrt(value/maximum), 'color': TEAL,
                               'geography_id': identifier, 'value': value})
    known = {p.get('geography_id') for p in primitives}
    unmatched = [r['id'] for r in rows if r['id'] not in known and r.get('value') is not None]
    legend = []
    if volume:
        for i, fraction in enumerate((.1, .5, 1)):
            radius = 24*math.sqrt(fraction)
            primitives += [{'type': 'circle', 'x': 110+i*235, 'y': 405, 'r': radius, 'color': TEAL},
                           _text(145+i*235, 409, _fmt(maximum*fraction)+' '+unit, size=11)]
        legend = [{'value': maximum*f, 'color': TEAL} for f in (.1, .5, 1)]
    else:
        for i, color in enumerate(colors):
            lower, upper = (None if i == 0 else bins[i-1]), (bins[i] if i < len(bins) else None)
            label = f'≤ {_fmt(upper, 0)}' if lower is None else (f'> {_fmt(lower, 0)}' if upper is None else f'{_fmt(lower, 0)} to {_fmt(upper, 0)}')
            primitives += [{'type': 'rect', 'x': 20+i*118, 'y': 385, 'width': 100, 'height': 14, 'color': color}, _text(20+i*118, 415, label, size=10)]
            legend.append({'lower': lower, 'upper': upper, 'color': color})
    primitives += [_text(20, 442, f'Pale slate = outside selected/page scope or unavailable; never zero. Vintage {vintage}.', MUTED, 11),
                   _text(20, 463, f'{populated} populated geographic marks; {len(unmatched)} unmatched source areas remain in the evidence table.', MUTED, 11)]
    return _figure(title, ('Blue = Democratic advantage, red = Republican advantage; DEM minus REP percentage points.' if is_margin else ('Circle area represents '+unit+'.' if volume else 'Sequential magnitude scale in '+unit+'.'))+' Original counts and geographic identifiers remain unchanged.', primitives, 480,
                   unit=unit, legend=legend, boundary_vintage=vintage, join={'populated': populated, 'unmatched_ids': unmatched})


def _section(section_id):
    return {'id': section_id, 'title': SECTION_LOOKUP[section_id]['title'], 'paragraphs': [], 'figures': [], 'tables': [], 'warnings': []}


def _table(columns, rows, title='Evidence lookup'):
    return {'title': title, 'columns': columns, 'rows': rows}


def _participation_points(view):
    groups = []
    for cycle in sorted({p['cycle'] for p in view['series']}, reverse=True):
        points = []
        for row in view['series']:
            if row['cycle'] != cycle:
                continue
            x = row.get('x', row.get('days_to_election'))
            if x is None:
                continue
            points.append((x, row['value']))
        groups.append((str(cycle), points, CYCLE_COLORS.get(cycle, MUTED)))
    return groups


def _document(database, request: ReportRequest):
    revision = database.latest_revision() if request.query.revision is None else request.query.revision
    if revision < 0 or revision > database.latest_revision():
        raise ValueError('Dataset revision does not exist')
    selected = [s for s in request.sections if s.enabled]
    kinds = {SECTION_LOOKUP[s.id]['kind'] for s in selected}
    if kinds <= {'summary', 'evidence'}:
        kinds.add('participation')
    ev = workspace(database, request.query.model_copy(update={'revision': revision})) if 'participation' in kinds else None
    pinned_query = ev['query'] if ev else {**request.query.model_dump(), 'revision': revision}
    pinned_request = request.model_copy(deep=True)
    pinned_request.query = ResearchQuery.model_validate(pinned_query)
    if not request.include_notes:
        pinned_request.notes = ''
    result_args = request.results.model_dump()
    future_baseline_withheld = bool(pinned_query.get('as_of') and result_args.get('baseline') is not None and result_args['baseline'] > int(pinned_query['as_of'][:4])-1)
    if future_baseline_withheld:
        # Remove the future baseline before computing any margin, swing or
        # matched-coverage field; filtering only its table would leak derivatives.
        result_args['baseline'] = None
    # Native selected participation IDs do not silently become historical places.
    results = result_query(database, state=request.query.state, revision=revision, **result_args) if 'results' in kinds else None
    context = context_query(database, state=request.query.state, metric=request.context_metric, revision=revision) if 'context' in kinds else None
    if context:
        context['publication_evidence'] = ACS_RELEASE
        if pinned_query.get('as_of'):
            cutoff_date = pinned_query['as_of'][:10]
            context['estimates'] = [r for r in context['estimates'] if r['period_end'] < cutoff_date and (r['period_end'] != ACS_RELEASE['period_end'] or ACS_RELEASE['release_date'] <= cutoff_date)]
            if not context['estimates']:
                context['warnings'].append('Resident context is withheld: its estimate period and documented ACS release date must precede the selected cutoff. The 2020-2024 five-year estimates were released January 29, 2026, not during the estimate period.')
                context['sources'] = []
    if context and request.query.geography_ids:
        ids = set(request.query.geography_ids)
        context = {**context, 'estimates': [r for r in context['estimates'] if r['geography_id'] in ids]}
    if results and future_baseline_withheld:
        results['warnings'].append('The requested historical baseline is from the cutoff calendar year or later. Its values and all derived comparisons are withheld before calculation.')
    # The current-participation cutoff also prevents a saved investigation from
    # silently acquiring later final returns. Final-return publication dates are
    # not established by this archive, so same-year finals are conservative gaps.
    if results and pinned_query.get('as_of'):
        latest_final_year = int(pinned_query['as_of'][:4])-1
        results['history'] = [r for r in results['history'] if r['year'] <= latest_final_year]
        results['baseline_geographies'] = [r for r in results['baseline_geographies'] if r['year'] <= latest_final_year]
        if request.results.year > latest_final_year:
            results = {**results, 'geographies': [], 'contests': [], 'pagination': None,
                'summary': {'total_votes': None, 'geography_count': 0, 'contest_count': 0, 'matched_baseline_count': 0, 'unit': 'candidate votes'},
                'coverage': {'status': 'withheld_future_final_returns', 'source_reconciliation': None},
                'warnings': ['Requested final returns are from the cutoff calendar year or later and are withheld. The final-return archive does not establish when contemporary final data was published; choose an earlier election or a later explicit cutoff.']}
        allowed_refs = {ref['snapshot_id'] for row in [*results['geographies'], *results['baseline_geographies'], *results['history']] for ref in row.get('source_refs', [])}
        results['sources'] = [r for r in results['sources'] if r['id'] in allowed_refs]
    projection = None
    if 'ev_forecast' in kinds:
        from .ev_forecast import early_vote_forecasts
        model_run = early_vote_forecasts(database, state=request.query.state, revision=revision, as_of=pinned_query.get('as_of'), cycle=request.query.cycle)
        if not pinned_query.get('as_of'):
            pinned_query['as_of'] = model_run['as_of']
            pinned_request.query = ResearchQuery.model_validate(pinned_query)
        projection = {'selected': model_run['selected'], 'validation': model_run['validation'] if model_run['selected'] else {},
            'backtesting': model_run.get('backtesting', {}), 'manifest': model_run['manifest'], 'warnings': model_run['warnings']}
        projection = _public(projection)
    precinct_bundle = None
    precinct_boundaries = []
    if results and results['coverage'].get('status') != 'withheld_future_final_returns' and request.results.geography_level == 'precinct' and any(s.id == 'results_map' for s in selected):
        from .precincts import _manifest, precinct_map
        precinct_bundle = precinct_map(database, state=request.query.state, year=request.results.year, office=request.results.office, revision=revision, contest_id=request.results.contest_id)
        if precinct_bundle['availability']['status'] == 'loaded':
            metadata = _manifest(database, precinct_bundle['availability']['dataset_id'], revision)
            descriptor = metadata['files']['overview']
            geometry_path = Path(metadata['directory'])/descriptor['filename']
            precinct_boundaries = [{'storage': 'data', 'file': str(geometry_path.relative_to(database.settings.data_dir)), 'sha256': descriptor['sha256'], 'vintage': metadata['boundary_vintage'], 'source': metadata['title']}]
    evidence = {}
    if projection:
        evidence['ev_projection'] = projection
    if ev:
        evidence['participation'] = {k: ev[k] for k in ('query', 'revision', 'summary', 'series', 'geographies', 'geographic_research', 'comparison', 'composition', 'polls', 'observations', 'coverage', 'warnings', 'brief')}
    if results:
        evidence['results'] = _public(results)
    if precinct_bundle:
        # Geometry itself is separately hashed; retain its exact metadata and
        # source references, without duplicating large polygon arrays in data.
        evidence['precinct_map'] = _public({k: v for k, v in precinct_bundle.items() if k != 'features'})
    if context:
        evidence['context'] = _public(context)
    snapshot_ids = set()
    if projection and projection['selected']:
        snapshot_ids.update(r['id'] for r in projection['selected']['sources'])
        def collect_projection_refs(value):
            if isinstance(value, dict):
                if isinstance(value.get('snapshot_id'), int):
                    snapshot_ids.add(value['snapshot_id'])
                for nested in value.values():
                    collect_projection_refs(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect_projection_refs(nested)
        collect_projection_refs(projection)
    for view in (results, context):
        if view:
            snapshot_ids.update(s['id'] for s in view['sources'])
    if precinct_bundle:
        snapshot_ids.update(s['snapshot_id'] for s in precinct_bundle['sources'])
    if ev:
        snapshot_ids.update(r['snapshot_id'] for r in [*ev['observations'], *ev['polls']] if r.get('snapshot_id'))
        composition_ids = {i for r in ev['composition'] for i in r.get('observation_ids', [])}
        if composition_ids:
            with database.session() as session:
                snapshot_ids.update(session.scalars(select(ObservationRecord.snapshot_id).where(ObservationRecord.id.in_(composition_ids))))
    from .provenance import snapshot_references
    snapshot_ids.update(r['snapshot_id'] for r in snapshot_references(database, evidence, revision)
                        if r.get('snapshot_id'))
    with database.session() as session:
        sources = [_public(record_dict(s)) for s in session.scalars(select(Snapshot).where(Snapshot.id.in_(snapshot_ids)).order_by(Snapshot.id))]
    boundaries, sections = [], []
    for choice in selected:
        item = _section(choice.id)
        item['researcher_caption'] = choice.caption
        sid = choice.id
        if sid == 'ev_call':
            call = projection['selected'] if projection else None
            if not call:
                item['warnings'].append('No scheduled 2026 Senate contest exists in this state, or a supported model call is unavailable. Participation research remains separate.')
            else:
                output = call['call']
                call_audit = call.get('audit', {})
                point_role = call_audit.get('point_role') or ('Historical context only' if output['status'] == 'reference_only' else 'Conditional research point')
                item['paragraphs'] = [f'{call["state_name"]} Senate: {output["label"]}. Basis: {output["status"].replace("_", " ")}. Margin is Republican minus Democratic percentage points.',
                    'This is an experimental conditional party-margin projection. No winner probability is published. The current official candidate roster is unverified; historical candidates are not assumed to be current nominees.', *call['explanation']]
                if call_audit:
                    item['paragraphs'].extend([call_audit['conclusion'], call_audit['state_note']])
                if output['margin_pp'] is not None:
                    margin, low, high = output['margin_pp'], output['range_low_pp'], output['range_high_pp']
                    left, right = min(-30, math.floor(low/10)*10), max(30, math.ceil(high/10)*10)
                    def px(value):
                        return 80+(value-left)/(right-left)*730
                    primitives = [_text(80, 30, output['label']+' · '+point_role, NAVY, 22),
                        _text(80, 55, f'Unvalidated sensitivity range: {low:+.1f} to {high:+.1f} pp', MUTED, 13),
                        _line(80, 115, 810, 115, '#c9d6e0', 5), _line(px(low), 115, px(high), 115, '#b9c7d3', 12),
                        _line(px(0), 85, px(0), 150, NAVY, 1),
                        {'type': 'circle', 'x': px(margin), 'y': 115, 'r': 9, 'color': '#c41439' if margin > 0 else '#1559be' if margin < 0 else TEAL},
                        _text(80, 175, f'Democratic advantage ({left:g})', '#1559be', 12), _text(810, 175, f'Republican advantage (+{right:g})', '#c41439', 12, 'end'),
                        _text(px(0), 175, '0 = tied', MUTED, 11, 'middle')]
                    item['figures'] = [_figure(point_role+' · Senate research', point_role+'. '+call_audit.get('conclusion', 'The point is a conditional research call.')+' The gray band is an unvalidated sensitivity range, with no claimed probability coverage. Current early-ballot candidate choices remain unobserved.', primitives, 205, unit='R minus D percentage points')]
                early = call['evidence']['early_vote']
                tilt = call['evidence']['geographic_tilt']
                reference = call['evidence']['historical_reference']
                item['tables'] = [_table(['Model input', 'Value', 'Meaning'], [
                    ['Historical Senate reference', reference.get('margin_pp'), 'R minus D pp; earlier Senate contests, not current candidate votes'],
                    ['Current early-ballot measure', early.get('total'), str(early.get('metric_label'))+' / '+str(early.get('mode'))+' / source date '+str(early.get('date'))],
                    ['Geographic EV tilt', tilt.get('tilt_pp'), tilt.get('description')],
                    ['Applied EV adjustment', tilt.get('adjustment_pp'), 'Unvalidated coefficient 0.35; capped at ±5 pp'],
                    ['Matched county count', tilt.get('matched_areas'), str(tilt.get('coverage_pct'))+'% of known county activity'],
                    ['EV held-out audit checkpoints', len(projection.get('backtesting', {}).get('cases', [])),
                     'Repeated stages of the same contest are dependent; chronology strata remain separate']], 'Model components and evidence scopes'),
                    _table(['Election', 'Contest', 'Special', 'R minus D pp', 'Weight'], [[r['year'], r['contest_name'], r.get('special', False), r['margin_pp'], r['weight']] for r in reference['cycles']], 'Historical Senate reference inputs'),
                    _table(['County', 'Early count', 'Early share %', 'Reference share %', 'Historical R-D pp', 'Raw tilt contribution pp'], [[r['name'], r['early_votes'], r['early_share_pct'], r['reference_share_pct'], r['reference_margin_pp'], r['contribution_pp']] for r in tilt['rows']], 'Geographic-mix contributions'),
                    _table(['Held-out origin', 'Cases', 'Historical-only MAE pp', 'Historical-only RMSE pp', '80% interval coverage', '95% interval coverage'], [[r['year'], r['cases'], r['margin_mae_pp'], r['margin_rmse_pp'], r['interval_80_coverage'], r['interval_95_coverage']] for r in projection['validation']['origins']], 'Historical-reference diagnostics, not EV-model validation')]
                item['tables'].append(_table(['Explicit modeling assumption'], [[text] for text in call['assumptions']], 'Research assumptions'))
                if call_audit:
                    item['tables'].append(_table(['Check', 'Supported', 'Explanation'],
                        [[row['label'], 'Yes' if row['passed'] else 'Not established', row['detail']] for row in call_audit['checks']],
                        'Comparable-evidence audit'))
                audit = projection.get('backtesting', {})
                if audit:
                    rows = []
                    for label, key in [('Historical reference', 'historical_reference'), ('Fixed EV assumption', 'fixed_ev_assumption'), ('Earlier-cycle fitted EV', 'fitted_ev')]:
                        stats = audit.get('metrics', {}).get(key, {})
                        rows.append([label, stats.get('cases'), stats.get('independent_contests'), stats.get('independent_cycles'), stats.get('margin_mae_pp'), stats.get('margin_rmse_pp')])
                    item['tables'].append(_table(['Model', 'Checkpoints', 'Independent contests', 'Cycles', 'MAE pp', 'RMSE pp'], rows, 'Paired held-out audit: retrospective dated-report stratum'))
                    item['tables'].append(_table(['State', 'Year', 'Stage', 'Chronology', 'Actual R-D pp', 'Reference pp', 'EV pp', 'EV error pp'],
                        [[r['state'], r['year'], r.get('stage'), r.get('chronology'), r.get('actual_margin_pp'), r.get('baseline_margin_pp'), r.get('predicted_margin_pp'), r.get('error_pp')] for r in audit.get('cases', [])], 'All eligible EV evaluation cases'))
                    item['paragraphs'].append(str(audit.get('promotion', {}).get('reason', 'No additional EV conversion is promoted without independent held-out improvement.')))
                turnout = call['evidence'].get('turnout_projection', {})
                if turnout:
                    item['tables'].append(_table(['Participation measure', 'Value', 'Interpretation'], [
                        ['Reported early participation', turnout.get('current_total'), 'Source date '+str(turnout.get('report_date'))],
                        ['Conditional final participation', turnout.get('projection'), turnout.get('reason')],
                        ['Conditional remaining participation', turnout.get('remaining_participation'), 'Later/unreported participation, not an observed Election Day count'],
                        ['Historical analogue span', [turnout.get('range_low'), turnout.get('range_high')], 'Not a confidence interval; excludes model error']], 'Prior-only turnout analogue and limits'))
                confidence = call.get('confidence', {})
                if confidence:
                    item['paragraphs'].append(confidence.get('reason', ''))
                item['warnings'] = list(dict.fromkeys(call['warnings']+projection['warnings']+[projection['validation']['ev_validation'], projection['validation']['timestamp_limitations']]))
        elif sid == 'summary':
            item['paragraphs'] = [f'{state_info(request.query.state)["name"]}: this packet distinguishes current participation, historical contest returns and resident context. They use separate units and source scopes.']
            if ev:
                total = ev['summary']['total']
                metric = ev['summary']['metric_label']
                item['paragraphs'].append(f'{request.query.cycle} participation: '+(f'{total:,.0f} {metric.lower()} at {ev["summary"]["latest_date"]}, using {request.query.time_basis} chronology and {request.query.mode} voting mode.' if total is not None else f'No compatible {metric.lower()} observations match the selected mode, chronology and cutoff; unavailable is not zero.'))
                item['paragraphs'] += [s['text'] for s in ev['brief'] if s.get('text')]
            if results:
                total = results['summary']['total_votes']
                item['paragraphs'].append(f'Historical results: {request.results.year} {request.results.office}, '+(f'{total:,.0f} candidate/ballot-option votes across {len(results["geographies"]):,} displayed {request.results.geography_level} areas.' if total is not None else 'no safely aggregable contest total is available in this scope.'))
                reconciliation = results['coverage'].get('source_reconciliation')
                if reconciliation and reconciliation['difference_votes']:
                    item['warnings'].append(f'County source sum differs from the dedicated statewide source by {reconciliation["difference_votes"]:,.0f} candidate votes. Preserve this discrepancy when interpreting the map.')
            if context:
                item['paragraphs'].append(f'Resident context: {request.context_metric.replace("_", " ")}, ACS 2020-2024 five-year estimates and 90% margins of error; not characteristics measured among voters.')
        elif sid == 'ev_trajectory':
            figure = _trajectory('Actual participation observations by cycle', _participation_points(ev), ev['summary']['unit'], 'Historical alignment: '+request.query.alignment.replace('_', ' '))
            item['figures'] = [figure] if figure else []
            item['warnings'] = ev['historical'].get('warnings', [])
            item['paragraphs'] = ['Dates and reporting coverage are retained. Historical pace is unavailable whenever calendar, definition or matched-coverage requirements fail.']
            item['tables'] = [_table(['Cycle', 'Report date', 'Value', 'Unit'], [[p['cycle'], p['date'], p['value'], ev['summary']['unit']] for p in ev['series']], 'Actual trajectory observations')]
        elif sid == 'ev_changes':
            points = [p for p in ev['series'] if p['cycle'] == request.query.cycle]
            changes = []
            for i, point in enumerate(points):
                change = point.get('newly_reported')
                if change is None and i:
                    change = point['value']-points[i-1]['value']
                if change is not None:
                    changes.append({'name': point['date'], 'value': change, 'label': ('+' if change > 0 else '')+_fmt(change), 'color': TEAL if change >= 0 else '#cc7134'})
            item['figures'] = [f] if (f := _bars('Recent reporting changes', changes[-16:], ev['summary']['unit'])) else []
            item['paragraphs'] = ['These are changes between actual reports, not the number of people who voted on each day. A negative change is a correction or coverage change. No first-report increment is invented.']
            item['tables'] = [_table(['Reporting date', 'Newly reported change', 'Unit'], [[r['name'], r['value'], ev['summary']['unit']] for r in changes])]
        elif sid in {'ev_map', 'ev_places'}:
            areas = ev['geographies']
            if sid == 'ev_map':
                values = []
                for row in areas:
                    canonical = row.get('canonical_id')
                    if not canonical:
                        canonical = canonicalize_observation({'state': request.query.state, 'geography_id': row['id'], 'geography_name': row['name'], 'geography_type': row['type']}).get('canonical_id')
                    values.append({'id': canonical or row['id'], 'value': row['value']})
                grain = 'county' if any(r['type'] == 'county' for r in areas) else 'state'
                item['figures'] = [f] if (f := _map('Participation - reported volume', request.query.state, grain, values, 'volume', ev['summary']['unit'], boundaries)) else []
                item['paragraphs'] = [f'{ev["summary"]["metric_label"]}; {request.query.mode} mode; source evidence date {ev["summary"]["latest_date"] or "unavailable"}. Counts use symbol area. Native districts or municipalities without verified geometry remain in the lookup.']
            else:
                item['figures'] = [f] if (f := _bars('Largest reporting-area contributions', [{'name': r['name'], 'value': r['value']} for r in sorted(areas, key=lambda r: -r['value'])], ev['summary']['unit'])) else []
                places = ev.get('geographic_research', {}).get('places', [])[:8]
                groups = [(p['name'], [(r.get('x', r.get('days_to_election', i)), r['value']) for i, r in enumerate(p.get('current_series', p.get('series', [])))], list(CYCLE_COLORS.values())[index%5]) for index, p in enumerate(places)]
                if (f := _trajectory('Individually labeled place trajectories', groups, ev['summary']['unit'])):
                    item['figures'].append(f)
            item['tables'] = [_table(['Place', 'Identifier', 'Report date', 'Reported count', 'Baseline', 'Change'], [[r['name'], r.get('canonical_id') or r['id'], r['date'], r['value'], r.get('baseline_value'), r.get('change')] for r in areas])]
        elif sid == 'ev_composition':
            grouped = {}
            for row in ev['composition']:
                grouped.setdefault(row['dimension'], []).append(row)
            for dimension, rows in grouped.items():
                title = dimension.replace('_', ' ')
                values = [{'name': str(r.get('category', 'Unknown')), 'value': r.get('value')} for r in rows]
                if (f := _bars(title, values, ev['summary']['unit'])):
                    item['figures'].append(f)
                item['tables'].append(_table(['Published group', 'Count'], [[r['name'], r['value']] for r in values], title))
            item['paragraphs'] = ['Published marginal groups remain separate. Unknown and unclassified categories are retained. These data do not establish candidate choice or unreported demographic intersections.']
        elif sid == 'results_map':
            values = [{'id': r['id'], 'value': r.get(request.map_metric)} for r in results['geographies']]
            metric = 'volume' if request.map_metric == 'total_votes' else request.map_metric
            unit = 'candidate votes' if metric == 'volume' else 'percentage points'
            map_options = {'features_override': precinct_bundle['features'], 'boundaries_override': precinct_boundaries, 'vintage': precinct_bundle.get('boundary_vintage', str(request.results.year))} if precinct_bundle and precinct_bundle['features'] else {}
            item['figures'] = [f] if (f := _map(f'{request.results.year} {request.results.office} - '+('candidate votes' if metric == 'volume' else 'Democratic margin'), request.query.state, request.results.geography_level, values, metric, unit, boundaries, **map_options)) else []
            if precinct_bundle:
                item['warnings'] += precinct_bundle['warnings']
                item['paragraphs'].append('Only exact identifiers shared by this result page and the archived source boundary bundle receive color. Unmatched administrative returns are retained in the table. The legend and totals describe this report scope, not statewide turnout.')
            if not item['figures']:
                item['warnings'].append('No verified geometry is available to this report renderer for the selected reporting grain. Exact original counts remain in the table; county polygons are not substituted.')
            item['tables'] = [_table(['Place', 'Identifier', 'Votes', 'DEM share %', 'REP share %', 'D minus R pp'], [[r['name'], r['id'], r['total_votes'], r.get('dem_share_pct'), r.get('rep_share_pct'), r.get('dem_margin_pp')] for r in results['geographies']])]
            item['warnings'] += results['warnings']
        elif sid == 'results_distribution':
            total = results['summary']['total_votes']
            options = {}
            if total is not None and not any(r.get('partial_suppression') for r in results['geographies']):
                for row in results['geographies']:
                    for option in row['options']:
                        key = (option['name'], option.get('party'))
                        item_option = options.setdefault(key, {'name': option['name'], 'party': option.get('party'), 'votes': 0})
                        item_option['votes'] += option['votes'] or 0
            ordered = sorted(options.values(), key=lambda r: -r['votes'])
            item['figures'] = [f] if (f := _bars('Complete response distribution - largest named options', [{'name': r['name'], 'value': r['votes'], 'label': f'{r["votes"]:,.0f} / {r["votes"]/total*100:.1f}%', 'color': party_color(r['party'])} for r in ordered] if total else [], 'candidate / ballot-option votes')) else []
            item['tables'] = [_table(['Option / candidate', 'Party as published', 'Votes', 'Share of candidate votes %'], [[r['name'], r['party'] or 'Nonpartisan / not specified', r['votes'], r['votes']/total*100 if total else None] for r in ordered])]
            item['paragraphs'] = ['Write-ins and other named responses remain in the table. Candidate-vote shares are not turnout. Several unrelated contests, suppressed counts, multi-seat votes and unspecified ranked-choice rounds retain their original qualifications.']
        elif sid == 'historical_trend':
            history = results['history']
            groups = [(label, [(r['year'], r[field]) for r in history if r.get(field) is not None], color) for label, field, color in [('Democratic', 'dem_share_pct', '#1559be'), ('Republican', 'rep_share_pct', '#c41439')]]
            item['figures'] = [f] if (f := _trajectory('Statewide presidential published vote shares', groups, 'percent of candidate votes', 'Election year', step=False)) else []
            item['tables'] = [_table(['Election', 'Candidate votes', 'DEM %', 'REP %', 'D minus R pp'], [[r['year'], r['total_votes'], r['dem_share_pct'], r['rep_share_pct'], r['dem_margin_pp']] for r in history])]
            item['paragraphs'] = ['This statewide presidential context retains its original contest scope even when a different office or place is being investigated. It is separate from early participation.']
        elif sid == 'comparison':
            rows = results['geographies']
            item['tables'] = [_table(['Place', f'{request.results.year} D-R pp', f'{request.results.baseline} D-R pp', 'Swing pp', 'Compatibility'], [[r['name'], r.get('dem_margin_pp'), r.get('baseline_dem_margin_pp'), r.get('swing_pp'), r['comparison_status'].replace('_', ' ')] for r in rows])]
            item['paragraphs'] = [f'Comparing {request.results.year} and {request.results.baseline}. Original margins can be read side by side. A numeric difference is published only when boundary and tabulation-round compatibility are established.']
            compatible = [r for r in rows if r.get('swing_pp') is not None]
            item['figures'] = [f] if (f := _bars('Compatible changes in Democratic margin', [{'name': r['name'], 'value': r['swing_pp'], 'label': ('+' if r['swing_pp'] > 0 else '')+_fmt(r['swing_pp'], 2)+' pp', 'color': TEAL if r['swing_pp'] >= 0 else '#cc7134'} for r in sorted(compatible, key=lambda r: -abs(r['swing_pp']))], 'percentage points')) else []
            if not compatible:
                item['warnings'].append('No paired observations in this scope meet the published difference-map criteria. Side-by-side original evidence remains available above.')
        elif sid in {'context_map', 'context_ranking'}:
            estimates = context['estimates']
            county = [r for r in estimates if r['geography_id'].startswith('county:')]
            use = county or estimates
            metric_title = request.context_metric.replace('_', ' ').title()
            unit = use[0]['unit'] if use else 'published units'
            if sid == 'context_map':
                item['figures'] = [f] if (f := _map(metric_title+' - residents / households', request.query.state, 'county' if county else 'state', [{'id': r['geography_id'], 'value': r['estimate']} for r in use], 'context', unit, boundaries)) else []
            else:
                names = {('county:'+str(f['properties']['GEOID'])): f['properties']['NAME'] for f in _map_features(request.query.state, 'county')[0]}
                item['figures'] = [f] if (f := _bars(metric_title, [{'name': names.get(r['geography_id'], r['geography_id']), 'value': r['estimate'], 'label': _fmt(r['estimate'], 1)+' ± '+_fmt(r['moe'], 1)} for r in sorted(use, key=lambda r: -(r['estimate'] or 0))], unit)) else []
            item['tables'] = [_table(['GEOID', 'Estimate', '90% MOE', 'Unit', 'Estimate period'], [[r['geography_id'], r['estimate'], r['moe'], r['unit'], r['period_start']+' to '+r['period_end']] for r in use])]
            item['warnings'] = context['warnings']
            item['paragraphs'] = ['ACS 2020-2024 five-year resident/household estimates; public release January 29, 2026. Release chronology source: '+ACS_RELEASE['source_url']+'. Published 90% margins of error appear in the table. An unavailable estimate is never shown as zero; resident context is not measured voter composition.']
        elif sid == 'polls':
            polls = [p for p in ev['polls'] if p['cycle'] == request.query.cycle]
            item['tables'] = [_table(['Producer', 'Fieldwork', 'Population', 'Sample', 'Question', 'Complete responses', 'Original release'], [[p['producer'], p['field_start']+' to '+p['field_end'], p['population'], p.get('sample_size'), p['question'], _poll_responses(p['estimates']), p.get('document_url') or p['source_url']] for p in polls])]
            item['paragraphs'] = ['Polling is statewide and does not change when a county is selected. Questions, candidates, undecideds and other responses remain intact. No average is manufactured when there are fewer than three eligible independent producers.']
        elif sid == 'evidence':
            item['paragraphs'] = ['This report pins its normalized queries, dataset revision, complete section order, researcher captions, map boundaries and source checksums. The ZIP can be regenerated locally with observatory reproduce PACKAGE --format html or --format pdf.']
            item['tables'] = [_table(['Snapshot', 'Source', 'Retrieved', 'SHA-256'], [[s['id'], s['url'], s['retrieved_at'], s['sha256']] for s in sources], 'Archived source documents')]
            item['warnings'] = list(dict.fromkeys(w for v in (ev, results, context) if v for w in v.get('warnings', [])))
            metric = next((m for m in METRICS if m['id'] == request.query.metric), None)
            if metric:
                item['paragraphs'].append('Participation definition: '+str(metric.get('definition', metric.get('label'))))
        if not item['figures'] and not item['tables'] and sid not in {'summary', 'evidence'}:
            item['warnings'].append('No source-supported evidence is available for this section at the pinned query. Missing does not mean zero.')
        sections.append(item)
    boundary_files = list({r['file']: r for r in boundaries}.values())
    request_data = pinned_request.model_dump(mode='json')
    report = {'schema': SCHEMA, 'title': request.title, 'state': request.query.state, 'revision': revision,
              'query': pinned_query, 'request': request_data, 'sections': sections, 'sources': sources,
              'boundary_files': boundary_files, 'notes': request.notes if request.include_notes else '',
              'private_notes_included': bool(request.include_notes and request.notes),
              'coverage': {k: v.get('coverage', {}) for k, v in evidence.items()},
              'limitations': list(dict.fromkeys(w for v in (ev, results, context) if v for w in v.get('warnings', []))),
              'evidence': evidence}
    report['content_sha256'] = _digest({k: report[k] for k in ('title', 'state', 'revision', 'query', 'request', 'sections', 'sources', 'boundary_files', 'notes')})
    return report


def figure_svg(figure):
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {figure["width"]} {figure["height"]}" role="img" aria-label="{escape(figure["title"], quote=True)}"><title>{escape(figure["title"])}</title>']
    for p in figure['primitives']:
        kind, color = p['type'], p.get('color', NAVY)
        if kind == 'text':
            elements.append(f'<text x="{p["x"]:.2f}" y="{p["y"]:.2f}" fill="{color}" font-size="{p["size"]}" text-anchor="{p["anchor"]}">{escape(p["text"])}</text>')
        elif kind == 'rect':
            elements.append(f'<rect x="{p["x"]:.2f}" y="{p["y"]:.2f}" width="{p["width"]:.2f}" height="{p["height"]:.2f}" fill="{color}"/>')
        elif kind == 'circle':
            elements.append(f'<circle cx="{p["x"]:.2f}" cy="{p["y"]:.2f}" r="{p["r"]:.2f}" fill="{color}" fill-opacity=".75" stroke="white" stroke-width=".5"/>')
        elif kind in {'line', 'polyline'}:
            coords = ' '.join(f'{x:.2f},{y:.2f}' for x, y in p['points'])
            elements.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{p.get("width", 1)}"/>')
        elif kind == 'polygon':
            path = ' '.join('M '+' L '.join(f'{x:.2f},{y:.2f}' for x, y in ring)+' Z' for ring in p['rings'])
            elements.append(f'<path d="{path}" fill="{color}" fill-rule="evenodd" stroke="{p["stroke"]}" stroke-width="{p["width"]}"/>')
    return ''.join(elements)+'</svg>'


def _html(document):
    output = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(document["title"])}</title><style>',
        'body{margin:0;background:#f3f5f7;color:#172e47;font:15px/1.55 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:40px;background:#fff}h1,h2{font-family:Georgia,serif;line-height:1.2}h1{font-size:36px}h2{font-size:25px;margin-top:0}header{border-top:7px solid #087f8c;border-bottom:1px solid #d4e1e8;padding:25px 0}.eyebrow{font:700 11px system-ui;letter-spacing:2px;color:#087f8c}.meta{display:flex;gap:12px;flex-wrap:wrap;color:#52687d;font-size:13px}section{margin:32px 0;padding-bottom:24px;border-bottom:1px solid #d4e1e8}figure{margin:24px 0;padding:18px;background:#f7fafb;border:1px solid #dae4eb;border-radius:10px}figure h3{font-size:17px;margin:0 0 10px}svg{width:100%;height:auto;font-family:system-ui,sans-serif}figcaption{font-size:12px;color:#52687d}table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}td,th{padding:8px;border-bottom:1px solid #dde6ec;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e7f3f0}details{margin:16px 0}summary{cursor:pointer;font-weight:700}.table-wrap{max-height:480px;overflow:auto}.warning{background:#fff3d8;border-left:4px solid #ca8b20;padding:10px 14px;margin:8px 0;font-size:13px}.caption{white-space:pre-wrap;padding:10px;background:#f0eaf9;border-left:3px solid #8552b6}.notes{white-space:pre-wrap}footer{font-size:11px;color:#52687d}@media(max-width:600px){main{padding:18px}h1{font-size:28px}.table-wrap{overflow:auto}figure{padding:6px}}@media print{body{background:#fff}main{padding:0;max-width:none}figure{break-inside:avoid}details>*{display:block}.table-wrap{max-height:none;overflow:visible}thead{display:table-header-group}section{break-before:auto}}',
        f'</style></head><body><main><header><div class="eyebrow">OBSERVATORY · ELECTION RESEARCH ATLAS</div><h1>{escape(document["title"])}</h1><p class="meta"><span>{escape(state_info(document["state"])["name"])}</span><span>Evidence revision {document["revision"]}</span><span>Cutoff {escape(str(document["query"].get("as_of") or "revision pinned"))}</span></p></header>']
    for section in document['sections']:
        output.append(f'<section id="section-{section["id"]}"><h2>{escape(section["title"])}</h2>')
        output += [f'<p>{escape(p)}</p>' for p in section['paragraphs']]
        for figure in section['figures']:
            output.append('<figure><h3>'+escape(figure['title'])+'</h3>'+figure_svg(figure)+'<figcaption><b>What this shows:</b> '+escape(figure['what'])+' Source: archived evidence references in this report; the full table retains original values.</figcaption></figure>')
        for warning in section['warnings']:
            output.append('<p class="warning">'+escape(warning)+'</p>')
        if section['researcher_caption']:
            output.append('<p class="caption"><b>Researcher caption:</b> '+escape(section['researcher_caption'])+'</p>')
        for table in section['tables']:
            output.append(f'<details open><summary>{escape(table["title"])} · {len(table["rows"]):,} rows</summary><div class="table-wrap"><table><thead><tr>'+''.join('<th>'+escape(c)+'</th>' for c in table['columns'])+'</tr></thead><tbody>')
            output += ['<tr>'+''.join('<td>'+escape(_cell(v))+'</td>' for v in row)+'</tr>' for row in table['rows']]
            output.append('</tbody></table></div></details>')
        output.append('</section>')
    if document['notes']:
        output.append('<section class="notes"><h2>Personal research notes</h2><p>Researcher interpretation, explicitly included; separate from reported evidence.</p>'+escape(document['notes'])+'</section>')
    output.append(f'<footer>Local aggregate research · revision {document["revision"]} · content SHA-256 {document["content_sha256"]}. Original evidence, limitations, queries and figure layout accompany the research package.</footer></main></body></html>')
    return ''.join(output).encode()


def _cell(value):
    if value is None:
        return 'Unavailable'
    if isinstance(value, float):
        return _fmt(value, 2 if value % 1 else 0)
    if isinstance(value, int):
        return f'{value:,}'
    return str(value)


def _pdf_figure(figure, width=500):
    from reportlab.graphics.shapes import Circle, Drawing, PolyLine, Rect, String
    from reportlab.graphics.shapes import Path as ShapePath
    from reportlab.lib.colors import HexColor
    scale = width / figure['width']
    drawing = Drawing(width, figure['height']*scale)
    # Use the same map rings, line paths, legend domains and values as SVG.
    for p in figure['primitives']:
        color = HexColor(p.get('color', NAVY))
        kind = p['type']
        def point(x, y):
            return x*scale, (figure['height']-y)*scale
        if kind == 'text':
            x, y = point(p['x'], p['y'])
            drawing.add(String(x, y, p['text'].replace('−', '-').replace('–', '-').replace('·', '/'), fontName='Helvetica', fontSize=p['size']*scale, fillColor=color, textAnchor=p['anchor']))
        elif kind == 'rect':
            x, y = point(p['x'], p['y']+p['height'])
            drawing.add(Rect(x, y, p['width']*scale, p['height']*scale, fillColor=color, strokeColor=None))
        elif kind == 'circle':
            x, y = point(p['x'], p['y'])
            drawing.add(Circle(x, y, p['r']*scale, fillColor=color, strokeColor=HexColor('#ffffff'), strokeWidth=.3))
        elif kind in {'line', 'polyline'}:
            pts = [v for x, y in p['points'] for v in point(x, y)]
            if len(pts) >= 4:
                drawing.add(PolyLine(pts, strokeColor=color, strokeWidth=p.get('width', 1)*scale))
        elif kind == 'polygon':
            shape = ShapePath(fillColor=color, strokeColor=HexColor(p['stroke']), strokeWidth=p['width']*scale)
            for ring in p['rings']:
                x, y = point(*ring[0])
                shape.moveTo(x, y)
                for coords in ring[1:]:
                    shape.lineTo(*point(*coords))
                shape.closePath()
            drawing.add(shape)
    return drawing


def _pdf(document):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('ResearchSmall', parent=styles['Normal'], fontSize=8, leading=11, textColor=colors.HexColor(MUTED)))
    styles.add(ParagraphStyle('ResearchCell', parent=styles['Normal'], fontSize=7, leading=9, wordWrap='CJK'))
    styles['Normal'].spaceAfter = 7
    styles['Normal'].leading = 14
    styles['Title'].textColor = colors.HexColor(NAVY)
    styles['Heading2'].textColor = colors.HexColor(TEAL)
    def para(value, style='Normal'):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), styles[style])
    story = [para('OBSERVATORY / ELECTION RESEARCH ATLAS', 'ResearchSmall'), Spacer(1, 8), para(document['title'], 'Title'),
             para(f'{state_info(document["state"])["name"]} / Evidence revision {document["revision"]} / Cutoff {document["query"].get("as_of") or "revision pinned"}', 'ResearchSmall'), Spacer(1, 20)]
    for section in document['sections']:
        story += [para(section['title'], 'Heading2')]
        story += [para(p) for p in section['paragraphs']]
        for figure in section['figures']:
            story.append(KeepTogether([Spacer(1, 10), para(figure['title'], 'Heading3'), _pdf_figure(figure), para(figure['what'], 'ResearchSmall'), Spacer(1, 10)]))
        story += [para('Evidence limitation: '+w, 'ResearchSmall') for w in section['warnings']]
        if section['researcher_caption']:
            story.append(para('Researcher caption: '+section['researcher_caption']))
        for table in section['tables']:
            story += [Spacer(1, 12), para(f'{table["title"]} / {len(table["rows"]):,} rows', 'Heading3')]
            rows = [[para(v, 'ResearchCell') for v in table['columns']]] + [[para(_cell(v), 'ResearchCell') for v in r] for r in table['rows']]
            if len(rows) > 1:
                widths = [500/len(table['columns'])]*len(table['columns'])
                data_table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
                data_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2f3ed')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LINEBELOW', (0, 0), (-1, -1), .2, colors.HexColor('#d9e3eb'))]))
                story.append(data_table)
            else:
                story.append(para('No matching source-supported rows.', 'ResearchSmall'))
        story.append(Spacer(1, 16))
    if document['notes']:
        story += [para('Personal research notes', 'Heading2'), para('Researcher interpretation, explicitly included; separate from reported evidence.', 'ResearchSmall'), para(document['notes'])]
    story += [Spacer(1, 12), para('Report content SHA-256: '+document['content_sha256'], 'ResearchSmall')]
    output = io.BytesIO()
    def footer(canvas, doc):
        report_footer(canvas, doc, document['revision'])
    SimpleDocTemplate(output, pagesize=A4, rightMargin=44, leftMargin=44, topMargin=42, bottomMargin=48, title=document['title']).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def compose_report(database, request: ReportRequest | dict):
    request = ReportRequest.model_validate(request) if isinstance(request, dict) else request
    document = _document(database, request)
    return {k: v for k, v in document.items() if k != 'evidence'} | {'html': _html(document).decode(), 'templates': TEMPLATES, 'catalog': SECTION_CATALOG}


def _manifest(document):
    build_files = sorted((PROJECT_ROOT/'backend'/'observatory').rglob('*.py'))
    return {'schema': SCHEMA, 'created_at': utc_now(), 'dataset_revision': document['revision'],
            'request': document['request'], 'source_snapshots': document['sources'], 'boundary_files': document['boundary_files'],
            'content_sha256': document['content_sha256'], 'evidence_sha256': _digest(document['evidence']),
            'private_notes_included': document['private_notes_included'], 'model_manifests': [document['evidence']['ev_projection']['selected']['manifest']] if document['evidence'].get('ev_projection', {}).get('selected') else [], 'limitations': document['limitations'],
            'application_build_sha256': hashlib.sha256(b''.join(p.read_bytes() for p in build_files)).hexdigest()}


def _render_export(document, format):
    manifest = _manifest(document)
    if format == 'html':
        return _html(document), 'text/html'
    if format == 'pdf':
        return _pdf(document), 'application/pdf'
    if format == 'json':
        return json.dumps({'report': document, 'manifest': manifest}, indent=2).encode(), 'application/json'
    if format == 'csv':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['section', 'table', 'column', 'row', 'value'])
        for section in document['sections']:
            for table in section['tables']:
                for index, row in enumerate(table['rows']):
                    for column, value in zip(table['columns'], row):
                        cell = _cell(value)
                        writer.writerow([section['id'], table['title'], column, index+1, "'"+cell if cell[:1] in {'=', '+', '-', '@'} else cell])
        return stream.getvalue().encode('utf-8-sig'), 'text/csv'
    if format != 'zip':
        raise ValueError('Choose html, pdf, json, csv or zip')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        archive.writestr('report.json', json.dumps(document, indent=2))
        archive.writestr('evidence.json', json.dumps(document['evidence'], indent=2))
        archive.writestr('saved_view.json', json.dumps({'page': 'reports', 'query': document['query'], 'report_request': document['request']}, indent=2))
        archive.writestr('report.html', _html(document))
        archive.writestr('report.pdf', _pdf(document))
        archive.writestr('tables.csv', _render_export(document, 'csv')[0])
        for section in document['sections']:
            for index, figure in enumerate(section['figures']):
                archive.writestr(f'figures/{section["id"]}-{index+1}.svg', figure_svg(figure))
        archive.writestr('README.txt', 'Aggregate research package. No raw personal voter records. Reproduce with: observatory reproduce THIS.zip --format html (or pdf). Matching SQLite/archive backup and verified boundary files are required. Query, evidence revision, figure order, captions and explicitly selected notes are pinned in manifest.json.\n')
    return output.getvalue(), 'application/zip'


def export_report(database, request: ReportRequest | dict, format='pdf'):
    request = ReportRequest.model_validate(request) if isinstance(request, dict) else request
    return _render_export(_document(database, request), format)


def reproduce_report(database, package_path: Path, format='html', output: Path | None = None):
    with zipfile.ZipFile(package_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        original = json.loads(archive.read('report.json'))
        evidence = json.loads(archive.read('evidence.json'))
    if manifest.get('schema') != SCHEMA:
        raise ValueError('Unsupported composed report package')
    if _digest(evidence) != manifest['evidence_sha256'] or original.get('evidence') != evidence:
        raise ValueError('Research package evidence checksum failed')
    if _digest({k: original[k] for k in ('title', 'state', 'revision', 'query', 'request', 'sections', 'sources', 'boundary_files', 'notes')}) != manifest['content_sha256']:
        raise ValueError('Research package report checksum failed')
    if manifest['request'] != original['request']:
        raise ValueError('Research package report layout checksum failed')
    with database.session() as session:
        for expected in manifest['source_snapshots']:
            snapshot = session.get(Snapshot, expected['id'])
            if not snapshot or snapshot.sha256 != expected['sha256']:
                raise ValueError('Matching source evidence database is required')
            if hashlib.sha256(Path(snapshot.path).read_bytes()).hexdigest() != expected['sha256']:
                raise ValueError('Archived source checksum failed')
    for expected in manifest['boundary_files']:
        path = (database.settings.data_dir if expected.get('storage') == 'data' else PROJECT_ROOT/'frontend'/'public')/expected['file']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected['sha256']:
            raise ValueError('Matching archived map boundary file is required')
    document = _document(database, ReportRequest.model_validate(manifest['request']))
    recomputed = True
    if document['content_sha256'] != manifest['content_sha256']:
        old_model = original.get('evidence', {}).get('ev_projection', {}).get('manifest', {}).get('model_version')
        new_model = document.get('evidence', {}).get('ev_projection', {}).get('manifest', {}).get('model_version')
        if not old_model or not new_model or old_model == new_model:
            raise ValueError('Report analytical output differs; retain the original application version for exact reproduction')
        # Sources, boundaries, evidence and original figure/table content have
        # all been verified above. Preserve that frozen research result across
        # a model upgrade, and explicitly distinguish it from recomputation.
        document, recomputed = original, False
    content, _ = _render_export(document, format)
    output = output or database.settings.data_dir/'exports'/f'composed-{document["state"]}-r{document["revision"]}-{utc_now().replace(":", "-")}.{format}'
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Output already exists; choose another filename')
    output.write_bytes(content)
    return {'output': str(output), 'revision': document['revision'], 'results_agree': recomputed,
        'analytical_recomputed': recomputed,
        'reproduction_mode': 'recomputed_and_verified' if recomputed else 'verified_frozen_model_result',
        'note': 'Pinned evidence and original results agree with the current calculation.' if recomputed else
            'The model version changed. This renders the checksum-verified original model result; it does not substitute a new forecast.',
        'source_hashes_verified': True, 'layout_preserved': True, 'boundary_hashes_verified': True}
