"""A historical report cutoff applies to derived values and context evidence."""
import hashlib
import json

from observatory.atlas.ingest import _publish, parse_bridge
from observatory.atlas.models import ContextEstimate
from observatory.domain import FetchedDocument
from observatory.report_composer import export_report
from test_report_composer import report_db as report_db


def report_document(database, payload):
    content, _ = export_report(database, payload, 'json')
    return json.loads(content)['report']


def test_future_baseline_cannot_survive_in_current_result_derived_fields(report_db, tmp_path):
    source = {'id': 'explicit_prior_report_fixture', 'title': 'Explicit 2020 test results',
        'provider': 'county_bridge', 'years': [2020], 'tier': 4, 'state': 'TX'}
    path = tmp_path/'prior.csv'
    path.write_text('state_name,county_fips,county_name,votes_dem,votes_gop,total_votes\nTexas,48001,Anderson,45,50,100\nTexas,48003,Andrews,150,240,400\n')
    rows, metadata = parse_bridge(source, str(path))
    document = FetchedDocument(url='https://example.org/explicit-prior-fixture.csv', path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), content_type='text/csv',
        retrieved_at='2026-10-21T00:00:00Z', byte_count=path.stat().st_size)
    _publish(report_db, source, document, rows, metadata)
    report = report_document(report_db, {'query': {'state': 'TX', 'as_of': '2022-10-20'},
        'results': {'year': 2020, 'baseline': 2024}, 'sections': [{'id': 'comparison'}, {'id': 'evidence'}]})
    evidence = report['evidence']['results']
    assert evidence['geographies']
    assert not evidence['baseline_geographies']
    assert all(row['baseline_dem_margin_pp'] is None and row['baseline_margin_pp'] is None and row['swing_pp'] is None
        for row in evidence['geographies'])
    assert evidence['summary']['matched_baseline_count'] == 0
    table = report['sections'][0]['tables'][0]
    assert all(row[2] is None and row[3] is None for row in table['rows'])
    assert report['request']['results']['baseline'] == 2024  # Preserve the user's requested layout, with an explained gap.


def test_context_period_after_cutoff_is_withheld_from_historical_report(report_db):
    with report_db.session() as session, session.begin():
        session.add(ContextEstimate(logical_key='explicit_future_context', revision=1, snapshot_id=1,
            dataset_id='explicit_context_fixture', state='TX', geography_id='county:48001',
            metric='population', estimate=12345, moe=15, unit='people',
            period_start='2020-01-01', period_end='2024-12-31', payload={'is_voter_characteristic': False}))
    report = report_document(report_db, {'query': {'state': 'TX', 'as_of': '2022-10-20'},
        'sections': [{'id': 'context_ranking'}, {'id': 'evidence'}]})
    assert report['evidence']['context']['estimates'] == []
    assert report['sections'][0]['tables'][0]['rows'] == []
    assert any('cutoff' in warning.lower() for warning in report['evidence']['context']['warnings'])


def test_future_precinct_bundle_is_not_opened_after_final_returns_are_withheld(report_db, monkeypatch):
    import observatory.precincts
    def unexpected_later_bundle(*args, **kwargs):
        raise AssertionError('A 2024 precinct bundle cannot enter a 2022-cutoff report')
    monkeypatch.setattr(observatory.precincts, 'precinct_map', unexpected_later_bundle)
    report = report_document(report_db, {'query': {'state': 'TX', 'as_of': '2022-10-20'},
        'results': {'year': 2024, 'baseline': None, 'geography_level': 'precinct'},
        'sections': [{'id': 'results_map'}, {'id': 'evidence'}]})
    assert report['evidence']['results']['coverage']['status'] == 'withheld_future_final_returns'
    assert 'precinct_map' not in report['evidence']
