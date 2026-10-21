"""Original-authority turnout endpoints, distinct from contest candidate votes.

EAVS F1a is total voters. Native method totals are retained separately and are
not assumed to be disjoint: provisional/UOCAVA treatment can overlap methods.
Missing/negative EAVS survey codes never become zero. An incomplete aggregation
is withheld rather than advertised as a statewide turnout endpoint.
"""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict

from observatory.domain import ParsedBatch
from observatory.registry import ELECTION_DATES, all_states

from .common import number, observation, soup

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
FIELDS = {'F1a': 'all', 'F1b': 'election_day', 'F1c': 'uocava', 'F1d': 'mail',
          'F1e': 'provisional', 'F1f': 'early_in_person', 'F1g': 'mail_vbm_jurisdiction', 'F1h': 'other'}
YEARS = {2016, 2018, 2020, 2022, 2024}


def _nonnegative(value):
    raw = str(value if value is not None else '').strip().replace(',', '')
    if not re.fullmatch(r'\d+(?:\.0+)?', raw):
        return None
    return int(float(raw))


def _xlsx_records(path):
    """Read only first-sheet scalar data, streaming the large public workbook."""
    with zipfile.ZipFile(path) as archive:
        shared = [''.join(item.itertext()) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in archive.namelist() else []
        headers = None
        with archive.open('xl/worksheets/sheet1.xml') as handle:
            for _event, element in ET.iterparse(handle, events=('end',)):
                if not element.tag.endswith('}row'):
                    continue
                cells = {}
                for cell in element:
                    column = re.sub(r'\d+', '', cell.get('r', ''))
                    scalar = cell.find('s:v', NS)
                    value = scalar.text if scalar is not None else ''.join(cell.itertext())
                    if cell.get('t') == 's':
                        value = shared[int(value)]
                    cells[column] = value
                if headers is None:
                    headers = cells
                else:
                    yield {headers[column]: value for column, value in cells.items() if column in headers}
                element.clear()


def _csv_records(path):
    with zipfile.ZipFile(path) as archive:
        files = [name for name in archive.namelist() if name.lower().endswith('.csv') and not name.startswith('__MACOSX/')]
        if len(files) != 1:
            raise ValueError('EAVS archive must contain one source CSV')
        with archive.open(files[0]) as handle:
            yield from csv.DictReader(io.TextIOWrapper(handle, encoding='utf-8-sig', newline=''))


def parse_eac(source, document):
    records = _xlsx_records(document.path) if source.get('format') == 'xlsx' else _csv_records(document.path)
    states = {row['code']: row['name'] for row in all_states()}
    groups = defaultdict(list)
    seen = set()
    for row in records:
        state = str(row.get('State_Abbr', '')).strip().upper()
        year = int(row.get('year') or source.get('cycle', 0))
        if state not in states or year not in YEARS:
            continue
        key = (state, year, row.get('FIPSCode'), row.get('Jurisdiction_Name'))
        if key in seen:
            raise ValueError('Duplicate EAVS jurisdiction within state/year; aggregation withheld')
        seen.add(key)
        groups[state, year].append(row)
    if not groups:
        raise ValueError('No verified 2016–2024 EAVS state/jurisdiction records located')
    observations, findings = [], []
    for (state, year), rows in sorted(groups.items()):
        statewide = [row for row in rows if str(row.get('Jurisdiction_Name', '')).strip().upper() in {'STATEWIDE', 'STATE TOTAL', 'STATE TOTALS'}]
        if len(statewide) > 1:
            raise ValueError('Multiple EAVS statewide records; original scope requires review')
        selected = statewide or rows
        for field, mode in FIELDS.items():
            values = [_nonnegative(row.get(field)) for row in selected]
            missing = sum(value is None for value in values)
            if missing:
                findings.append({'state': state, 'year': year, 'field': field, 'missing_jurisdictions': missing,
                                 'reported_jurisdictions': len(values)-missing, 'status': 'withheld_incomplete'})
                continue
            total = sum(values)
            if field == 'F1a' and total <= 0:
                findings.append({'state': state, 'year': year, 'field': field, 'status': 'withheld_nonpositive_total'})
                continue
            observations.append(observation({**source, 'state': state}, document, name=states[state], kind='state',
                value=total, metric='final_turnout', mode=mode, date_=ELECTION_DATES[year], cycle=year, basis='final',
                metadata={'parser_version': 'eac-turnout-1.0', 'source_tier': 1, 'metric_definition': 'eavs_total_participation' if mode == 'all' else f'eavs_{field}',
                    'native_definition': 'EAVS F1a total voters' if mode == 'all' else f'EAVS {field} native final participation category ({mode}); categories are not presumed disjoint.',
                    'original_field': field, 'endpoint_is_candidate_votes': False, 'administrative_survey': True,
                    'statewide_aggregation': 'Native statewide row' if statewide else 'Sum of every surveyed jurisdiction in this state/year; no missing field values',
                    'jurisdictions': len(selected), 'missing_jurisdictions': 0, 'source_vintage': source.get('version'),
                    'native_f1_comments_count': sum(bool(str(row.get('F1Comments') or '').strip()) for row in selected),
                    'native_highest_office_proxy_jurisdictions': sum(str(row.get('F2_4') or '').strip() in {'1', '1.0'} for row in selected),
                    'participation_measurement_caveat': 'EAVS permits poll books, ballots counted, vote history, or highest-office vote totals as administrative measurement sources. Raw F2 fields and jurisdiction comments remain in the archive.',
                    'publication_date_verified': False, 'contemporary_final_publication_unknown': True,
                    'definition_note': 'EAVS total voters is an administrative participation measure, not a contest vote sum. Native survey revisions can differ from other official turnout series.',
                    'method_categories_disjoint': False, 'denominator_use': 'Prior final reference only; never a current registration denominator.'}))
    return ParsedBatch(observations=observations, data_as_of=max(ELECTION_DATES[year] for _, year in groups),
        metadata={'primary_document_url': document.url, 'coverage_findings': findings, 'reference_data': True,
                  'state_coverage': {state: sorted({obs.cycle for obs in observations if obs.state == state and obs.mode == 'all'}) for state in states}},
        warnings=['Original EAC administrative survey endpoints; source vintages and state authority turnout series can differ.',
                  'Incomplete state/category aggregations and negative EAVS missing-data codes are withheld, never changed to zero.',
                  'Native method categories are not assumed disjoint and must not be automatically summed.'])


def parse_nc(source, document):
    page = soup(document)
    tables = [table for table in page.find_all('table') if 'Ballots Cast' in table.get_text() and 'General' in table.get_text()]
    observations = []
    years = set()
    for table in tables:
        for tr in table.find_all('tr'):
            cells = [cell.get_text(' ', strip=True) for cell in tr.find_all(['th', 'td'])]
            if len(cells) != 4 or not re.fullmatch(r'\d{4} General', cells[0]):
                continue
            year = int(cells[0][:4])
            if year < 1976 or year > 2024:
                continue
            if year in years:
                raise ValueError('Duplicate NC general turnout year')
            years.add(year)
            total, eligibility = number(cells[2]), number(cells[1])
            if total <= 0 or total > eligibility:
                raise ValueError('NC turnout endpoint does not reconcile with the published eligibility reference')
            observations.append(observation(source, document, name='North Carolina', kind='state', value=total,
                metric='final_turnout', date_=ELECTION_DATES[year], cycle=year, basis='final',
                metadata={'parser_version': 'nc-turnout-1.0', 'source_tier': 1, 'source_priority': 0,
                    'native_definition': 'NCSBE Voter Turnout main summary: Ballots Cast, general election',
                    'metric_definition': 'ncsbe_summary_final_participation', 'source_table': 'Presidential/non-presidential general election turnout summary',
                    'original_cell': cells[2], 'endpoint_is_candidate_votes': False,
                    'published_eligible_voters': eligibility, 'eligibility_reference_date': ELECTION_DATES[year],
                    'eligibility_definition': 'Eligible Voters (original summary label); do not relabel as active registration',
                    'publication_date_verified': False, 'contemporary_final_publication_unknown': True,
                    'source_vintage': document.retrieved_at,
                    'version_note': 'Main summary vintage. The separate 2024 detail page has a different total; no silent averaging or replacement.',
                    'denominator_use': 'Prior final participation reference only. Eligibility is historical context and never enters a pre-election target-year predictor.'}))
    if not all(year in years for year in (2016, 2018, 2020, 2022, 2024)):
        raise ValueError('NC turnout source lacks the required recent general elections')
    return ParsedBatch(observations=observations, data_as_of=ELECTION_DATES[max(years)], metadata={'reference_data': True},
        warnings=['Main summary turnout vintages can differ from election-detail and EAVS series; definitions/source versions remain separate.',
                  'Historical eligibility figures are final-election context and are never inserted into pre-election registration denominators.'])


def collect(source, fetcher):
    document = fetcher.fetch(source['url'])
    return parse_nc(source, document) if source.get('dataset') == 'nc_summary' else parse_eac(source, document)
