"""Research packages must reproduce pinned evidence and detect tampering."""
import hashlib
import json
import zipfile

import pytest
from observatory.atlas.ingest import _publish, parse_bridge
from observatory.atlas.models import ensure_schema
from observatory.atlas.store import result_query
from observatory.atlas_api import _result_export
from observatory.atlas_reproduce import reproduce_atlas
from observatory.db import Database
from observatory.domain import FetchedDocument, Observation, ResearchQuery
from observatory.settings import PROJECT_ROOT, Settings


def test_atlas_package_roundtrip_and_tamper_detection(tmp_path):
    database = Database(Settings(tmp_path / 'data', project_root=PROJECT_ROOT))
    ensure_schema(database)
    path = tmp_path / 'source.csv'
    # Explicit synthetic fixture; no sample values enter the installed live store.
    path.write_text('state_name,county_fips,county_name,votes_dem,votes_gop,total_votes\nTexas,48001,Anderson,40,55,100\n')
    source = {'id': 'test_bridge', 'title': 'Explicit test fixture', 'provider': 'county_bridge',
              'url': 'https://example.org/test.csv', 'producer': 'Test fixture', 'license': 'Fixture',
              'years': [2024], 'tier': 4}
    rows, metadata = parse_bridge(source, str(path))
    document = FetchedDocument(url='https://example.org/test.csv', path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        content_type='text/csv', retrieved_at='2026-10-21T00:00:00Z', byte_count=path.stat().st_size)
    _publish(database, source, document, rows, metadata)
    view = result_query(database, state='TX', year=2024, baseline=None)
    content, media = _result_export(view, 'zip')
    assert media == 'application/zip'
    package = tmp_path / 'research.zip'
    package.write_bytes(content)
    proof = reproduce_atlas(database, package, 'html', tmp_path / 'reproduced.html')
    assert proof['results_agree'] is True
    assert proof['source_hashes_verified'] is True
    assert '100.0' in (tmp_path / 'reproduced.html').read_text()
    with zipfile.ZipFile(package) as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    result = json.loads(members['results.json'])
    result['summary']['total_votes'] = 999
    members['results.json'] = json.dumps(result).encode()
    with zipfile.ZipFile(tmp_path / 'tampered.zip', 'w') as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    with pytest.raises(ValueError, match='checksum'):
        reproduce_atlas(database, tmp_path / 'tampered.zip', 'html', tmp_path / 'tampered.html')


def test_quantitative_input_guards():
    for invalid in (float('nan'), float('inf'), -1):
        with pytest.raises(ValueError):
            Observation(state='TX', cycle=2026, election_date='2026-11-03', date='2026-10-20', metric='ballots_cast',
                        value=invalid, geography_id='state:TX', geography_name='Texas')
    with pytest.raises(ValueError):
        ResearchQuery(date_window=('2026-10-20', '2026-10-10'))


def test_context_package_keeps_missing_estimates_and_visual_state(tmp_path):
    from observatory.atlas_reporting import context_export
    view = {'revision': 1, 'query': {'state': 'NM', 'metric': 'median_household_income'},
        'sources': [], 'warnings': ['Resident context, not voter demographics'],
        'estimates': [{'state': 'NM', 'geography_id': 'county:35011', 'metric': 'median_household_income',
            'estimate': None, 'moe': None, 'unit': '2024 dollars', 'period_start': '2020-01-01',
            'period_end': '2024-12-31', 'snapshot_id': 1, 'revision': 1}]}
    content, _ = context_export(view, 'zip', {'layer': 'population', 'selected_geographies': ['county:35011']})
    import io
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        report = package.read('report.html').decode()
        assert 'Unavailable' in report
        assert json.loads(package.read('context.json'))['estimates'][0]['estimate'] is None
        assert json.loads(package.read('manifest.json'))['presentation']['selected_geographies'] == ['county:35011']


def test_vector_report_figures_preserve_actual_option_shares():
    from observatory.atlas_reporting import result_figures_svg, result_pdf_figures
    view = {'summary': {'total_votes': 100}, 'geographies': [{'total_votes': 100, 'partial_suppression': False,
        'options': [{'id': 'yes', 'name': 'YES', 'party': None, 'votes': 60}, {'id': 'no', 'name': 'NO', 'party': None, 'votes': 40}]}], 'history': []}
    assert '60.0%' in result_figures_svg(view)
    assert result_pdf_figures(view)
    view['geographies'][0]['partial_suppression'] = True
    assert '60.0%' not in result_figures_svg(view)
