"""The report layout and every exported representation belong to the evidence."""
import hashlib
import io
import json
import zipfile

import pytest
from observatory.atlas.ingest import _publish, parse_bridge
from observatory.atlas.models import ensure_schema
from observatory.db import Database
from observatory.domain import FetchedDocument
from observatory.report_composer import ReportRequest, compose_report, export_report, reproduce_report
from observatory.settings import PROJECT_ROOT, Settings
from test_evidence_workflows import aggregate
from test_evidence_workflows import harness as harness


@pytest.fixture
def report_db(tmp_path):
    database = Database(Settings(tmp_path/'data', project_root=PROJECT_ROOT))
    ensure_schema(database)
    source = {'id': 'explicit_report_fixture', 'title': 'Synthetic report test fixture', 'provider': 'county_bridge',
              'url': 'https://example.org/explicit-fixture.csv', 'producer': 'Test fixture', 'license': 'Fixture', 'years': [2024], 'tier': 4}
    path = tmp_path/'fixture.csv'
    path.write_text('state_name,county_fips,county_name,votes_dem,votes_gop,total_votes\nTexas,48001,Anderson,40,55,100\nTexas,48003,Andrews,180,200,400\n')
    rows, metadata = parse_bridge(source, str(path))
    document = FetchedDocument(url=source['url'], path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        content_type='text/csv', retrieved_at='2026-10-21T00:00:00Z', byte_count=path.stat().st_size)
    _publish(database, source, document, rows, metadata)
    return database


def request(**changes):
    return {'title': 'Explicit test report', 'query': {'state': 'TX'}, 'template': 'history',
            'sections': [{'id': 'results_distribution', 'caption': 'Researcher explanation <script>unsafe()</script>'},
                         {'id': 'results_map'}, {'id': 'evidence'}], **changes}


def test_report_preview_and_pdf_preserve_layout_values_and_source_hashes(report_db):
    preview = compose_report(report_db, request(notes='Private note excluded by default'))
    assert [s['id'] for s in preview['sections']] == ['results_distribution', 'results_map', 'evidence']
    assert preview['request']['query']['revision'] == 1
    assert preview['request']['notes'] == ''
    assert 'Private note excluded' not in json.dumps(preview)
    assert '&lt;script&gt;unsafe()&lt;/script&gt;' in preview['html']
    assert '<script>unsafe()</script>' not in preview['html']
    assert len(preview['sources'][0]['sha256']) == 64
    assert preview['boundary_files'][0]['vintage'] == '2024'
    mapped = preview['sections'][1]['figures'][0]
    assert mapped['join']['populated'] == 2
    assert any(p.get('geography_id') == 'county:48001' and p.get('value') == -15 for p in mapped['primitives'])
    content, media = export_report(report_db, request(), 'pdf')
    assert media == 'application/pdf'
    from pypdf import PdfReader
    text = ''.join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)
    assert 'Explicit test report' in text and 'Anderson' in text
    assert '2024' in text and 'Evidence revision 1' in text


def test_symbol_area_not_radius_encodes_volume(report_db):
    value = compose_report(report_db, request(map_metric='total_votes'))
    figure = value['sections'][1]['figures'][0]
    circles = {p['geography_id']: p for p in figure['primitives'] if p['type'] == 'circle' and 'geography_id' in p}
    assert circles['county:48003']['r']/circles['county:48001']['r'] == pytest.approx(2)
    assert figure['unit'] == 'candidate votes'


def test_report_package_regeneration_checks_data_layout_notes_and_boundaries(report_db, tmp_path):
    payload = request(notes='Explicit interpretation', include_notes=True)
    content, _ = export_report(report_db, payload, 'zip')
    package = tmp_path/'report.zip'
    package.write_bytes(content)
    with zipfile.ZipFile(package) as archive:
        assert {'report.pdf', 'report.html', 'tables.csv', 'report.json', 'evidence.json', 'saved_view.json'} <= set(archive.namelist())
        members = {n: archive.read(n) for n in archive.namelist()}
        manifest = json.loads(members['manifest.json'])
        assert manifest['private_notes_included'] is True
        assert manifest['request']['sections'][0]['id'] == 'results_distribution'
        assert 'Explicit interpretation' in members['report.html'].decode()
        assert any(n.startswith('figures/') and n.endswith('.svg') for n in members)
    result = reproduce_report(report_db, package, 'html', tmp_path/'regenerated.html')
    assert result['results_agree'] and result['layout_preserved'] and result['boundary_hashes_verified']
    assert (tmp_path/'regenerated.html').read_bytes() == members['report.html']
    report = json.loads(members['report.json'])
    report['sections'].reverse()
    members['report.json'] = json.dumps(report).encode()
    with zipfile.ZipFile(tmp_path/'tampered.zip', 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with pytest.raises(ValueError, match='report checksum'):
        reproduce_report(report_db, tmp_path/'tampered.zip', 'html', tmp_path/'bad.html')


def test_scope_and_duplicate_section_validation():
    with pytest.raises(ValueError, match='only once'):
        ReportRequest.model_validate(request(sections=[{'id': 'evidence'}, {'id': 'evidence'}]))
    with pytest.raises(ValueError, match='at least one'):
        ReportRequest.model_validate(request(sections=[{'id': 'evidence', 'enabled': False}]))
    with pytest.raises(ValueError):
        ReportRequest.model_validate(request(results={'geography_level': 'precinct', 'limit': 1000}))


def test_model_upgrade_renders_verified_frozen_report_instead_of_new_calls(report_db, tmp_path, monkeypatch):
    from observatory import report_composer
    from observatory.ev_forecast import _run
    _run.cache_clear()
    payload = request(sections=[{'id': 'ev_call'}, {'id': 'evidence'}], template='ev_senate')
    content, _ = export_report(report_db, payload, 'zip')
    package = tmp_path / 'pinned-model.zip'
    package.write_bytes(content)
    with zipfile.ZipFile(package) as archive:
        old_html = archive.read('report.html')
    real_document = report_composer._document

    def newer_model(database, body):
        result = real_document(database, body)
        result['evidence']['ev_projection']['manifest']['model_version'] = 'explicit-synthetic-later-model'
        result['content_sha256'] = 'explicitly-different-new-model-output'
        return result

    monkeypatch.setattr(report_composer, '_document', newer_model)
    result = reproduce_report(report_db, package, 'html', tmp_path/'frozen.html')
    assert result['reproduction_mode'] == 'verified_frozen_model_result'
    assert not result['analytical_recomputed'] and not result['results_agree']
    assert (tmp_path/'frozen.html').read_bytes() == old_html
    _run.cache_clear()


def test_nonpartisan_missing_parties_are_not_fake_zeroes(report_db):
    # A valid response distribution and volume map do not require party margins.
    payload = request(results={'year': 2024, 'baseline': None, 'office': 'NONEXISTENT'})
    preview = compose_report(report_db, payload)
    assert preview['sections'][0]['tables'][0]['rows'] == []
    assert 'Unavailable' not in preview['title']
    figure = preview['sections'][1]['figures'][0]
    assert figure['join']['populated'] == 0


def test_participation_report_remains_pinned_after_new_source_revision(harness):
    harness.state.payload['observations'] = [aggregate(100, date='2026-10-19'), aggregate(90, date='2026-10-20')]
    first = harness.collect()
    payload = {'title': 'Pinned participation report', 'query': {'state': 'NC', 'as_of': '2026-10-20', 'revision': first['revision']},
        'sections': [{'id': 'summary'}, {'id': 'ev_trajectory'}, {'id': 'ev_changes'}, {'id': 'evidence'}]}
    before = compose_report(harness.database, payload)
    changes = next(s for s in before['sections'] if s['id'] == 'ev_changes')['tables'][0]['rows']
    assert changes == [['2026-10-20', -10.0, 'ballots']]
    assert any('90 ballots' in p for p in before['sections'][0]['paragraphs'])
    harness.state.payload['observations'][-1]['value'] = 110
    harness.collect(now='2026-10-21T16:00:00Z')
    after = compose_report(harness.database, payload)
    assert after['content_sha256'] == before['content_sha256']
    assert after['html'] == before['html']


def test_missing_calendar_alignment_is_not_an_invented_ordinal_timeline(harness):
    harness.state.payload['observations'] = [{**aggregate(100), 'mode': 'early_in_person'}]
    harness.collect()
    view = compose_report(harness.database, {'title': 'Unsupported calendar',
        'query': {'state': 'NC', 'as_of': '2026-10-20', 'mode': 'early_in_person', 'alignment': 'voting_opportunities'},
        'sections': [{'id': 'ev_trajectory'}]})
    assert view['sections'][0]['figures'] == []


def test_earlier_saved_cutoff_does_not_acquire_later_final_election_returns(report_db):
    report = compose_report(report_db, request(query={'state': 'TX', 'as_of': '2022-10-20'}, sections=[{'id': 'results_map'}, {'id': 'historical_trend'}]))
    mapping = report['sections'][0]
    assert mapping['tables'][0]['rows'] == []
    assert mapping['figures'][0]['join']['populated'] == 0
    assert any('withheld' in w for w in mapping['warnings'])
    assert report['sections'][1]['tables'][0]['rows'] == []


def test_ev_report_pins_model_cutoff_and_regenerates_after_today_changes(report_db, tmp_path, monkeypatch):
    from observatory import ev_forecast
    ev_forecast._run.cache_clear()
    monkeypatch.setattr(ev_forecast, 'local_today', lambda: '2026-10-21')
    payload = request(sections=[{'id': 'ev_call'}, {'id': 'evidence'}], template='ev_senate')
    preview = compose_report(report_db, payload)
    assert preview['request']['query']['as_of'] == '2026-10-21'
    assert preview['sections'][0]['id'] == 'ev_call'
    content, _ = export_report(report_db, payload, 'zip')
    path = tmp_path/'ev-report.zip'
    path.write_bytes(content)
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['model_manifests'][0]['model_version'] == ev_forecast.MODEL_VERSION
        assert manifest['request']['query']['as_of'] == '2026-10-21'
        assert 'No winner probability' in archive.read('report.html').decode()
    monkeypatch.setattr(ev_forecast, 'local_today', lambda: '2026-10-22')
    result = reproduce_report(report_db, path, 'html', tmp_path/'ev-report-reproduced.html')
    assert result['layout_preserved']
    ev_forecast._run.cache_clear()


def test_report_poll_options_preserve_published_shares_and_missingness():
    from observatory.report_composer import _poll_responses

    text = _poll_responses([
        {'name': 'Candidate A', 'party': 'DEM', 'value': 48.0, 'reported': '48%'},
        {'name': 'Undecided', 'value': 4.0, 'reported': '4%'},
        {'name': 'Other', 'value': 0.4, 'reported': '<1%'},
        {'name': 'Suppressed group', 'value': None, 'suppressed': True},
        {'name': 'No published value', 'value': None},
    ])
    assert text == 'Candidate A (DEM): 48%; Undecided: 4%; Other: <1%; Suppressed group: Suppressed; No published value: Not reported'
