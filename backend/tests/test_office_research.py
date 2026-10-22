"""Synthetic office fixtures exercise the real parser, store, API and reports."""
import hashlib
import io
import json

import pytest
from observatory.atlas.ingest import _publish, parse_results
from observatory.atlas.store import _rows, house_district_identity, result_query
from observatory.domain import FetchedDocument
from observatory.office_registry import HOUSE_SEATS, election_system, race_catalog
from observatory.office_research import district_number, office_research
from observatory.report_composer import compose_report, export_report
from pypdf import PdfReader
from test_evidence_workflows import harness as harness
from test_evidence_workflows import survey


def install(database, root, *, office='GOVERNOR'):
    path = root/f'{office}.csv'
    path.write_text('state_po,year,office,district,candidate,party,candidatevotes,stage\n'+''.join(
        f'OH,{year},{office},{district},{party} fixture candidate,{party},{votes},GEN\n'
        for year in (2018, 2022, 2024, 2026)
        for district in (['STATEWIDE'] if office == 'GOVERNOR' else ['1', '2'])
        for party, votes in [('DEM', 40 if district != '2' else 70), ('REP', 60 if district != '2' else 30)]))
    source = {'id': 'explicit-synthetic-'+office, 'title': 'Synthetic office integration fixture',
        'provider': 'state_federal', 'years': [2018, 2022, 2024, 2026], 'tier': 1, 'url': 'https://fixture.invalid/results.csv'}
    rows, metadata = parse_results(source, str(path))
    document = FetchedDocument(url=source['url'], path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        content_type='text/csv', retrieved_at='2026-10-21T12:00:00Z', byte_count=path.stat().st_size)
    return _publish(database, source, document, rows, metadata)['revision']


def test_universes_are_complete_and_legacy_senate_registry_stays_compatible():
    assert len(race_catalog()) == 35
    assert len(race_catalog('US HOUSE')) == sum(HOUSE_SEATS.values()) == 435
    assert len(race_catalog('GOVERNOR')) == 36
    assert len({r['state'] for r in race_catalog('US HOUSE')}) == 50
    assert len({r['id'] for r in race_catalog('US HOUSE')}) == 435
    assert not any(r['state'] == 'NC' for r in race_catalog('GOVERNOR'))
    assert election_system('ME', 'GOVERNOR') == 'plurality'
    assert election_system('ME', 'US HOUSE') == 'ranked_choice'
    assert election_system('AK', 'GOVERNOR') == 'ranked_choice'
    assert election_system('GA', 'GOVERNOR') == 'majority_runoff'
    assert next(r for r in race_catalog('US HOUSE') if r['state'] == 'LA')['possible_runoff_date'] == '2026-12-12'


def test_at_large_and_district_numbers_do_not_create_crosswalks():
    assert district_number('001') == 1
    assert district_number('STATEWIDE') is None
    assert district_number('STATEWIDE', at_large=True) == 1
    assert district_number('0', at_large=True) == 1
    assert district_number('not a district') is None
    assert house_district_identity('OH', 2024, '001') == '1'
    assert house_district_identity('MT', 2020, '1') == 'AL'
    assert house_district_identity('MT', 2024, '1') == '1'


def test_governor_adapter_keeps_final_runoffs_and_offices_distinct(tmp_path):
    path = tmp_path/'academic.tab'
    path.write_text('year\tstate\toffice\ttype\tname_snyder\tparty\tparty_formal\tcandidatevotes\trunoff\n'
        '2019.0\tLA\tG\tG\tGovernor fixture\tD\tD\t100.0\t1.0\n'
        '2022.0\tOH\tH\tG\tHouse fixture\tR\tR\t500.0\t\n')
    rows, _ = parse_results({'provider': 'snyder_governor', 'years': [2019]}, str(path))
    assert len(rows) == 1
    assert rows[0]['office'] == 'GOVERNOR'
    assert rows[0]['stage'] == 'GEN RUNOFF' and rows[0]['date'] == ''
    assert rows[0]['party'] == 'DEM'


def test_academic_bridge_keeps_house_offices_at_large_and_unknown_special_dates_separate(tmp_path):
    path = tmp_path/'academic.tab'
    path.write_text('year\tstate\toffice\tdist\ttype\tname_snyder\tparty\tparty_formal\tcandidatevotes\trunoff\n'
        '2020.0\tMT\tH\t1.0\tG\tAt large fixture\tR\tR\t100.0\t\n'
        '2024.0\tMT\tH\t1.0\tG\tDistrict fixture\tD\tD\t100.0\t\n'
        '2011.0\tWV\tG\t\tS\tSpecial fixture\tD\tD\t100.0\t\n')
    house, _ = parse_results({'provider': 'snyder_house', 'years': [2024]}, str(path))
    assert len(house) == 2
    assert house[0]['district'] == 'STATEWIDE' and house[1]['district'] == '1'
    gov, metadata = parse_results({'provider': 'snyder_governor', 'years': [2011]}, str(path))
    assert gov[0]['special'] and gov[0]['stage'] == 'GEN SPECIAL' and gov[0]['date'] == ''
    assert len(metadata['invalidated_contest_ids']) == 3


def test_office_api_preserves_cutoff_revision_and_district_scope(harness):
    before = harness.database.latest_revision()
    revision = install(harness.database, harness.root, office='US HOUSE')
    response = harness.client.get('/api/v2/forecasts/offices', params={'office': 'US HOUSE', 'revision': revision, 'as_of': '2026-10-21'})
    assert response.status_code == 200
    value = response.json()
    one, two = [next(r for r in value['calls'] if r['id'] == f'2026-OH-HOUSE-0{n}') for n in (1, 2)]
    assert one['latest_result']['margin_pp'] == 20
    assert two['latest_result']['margin_pp'] == -40
    assert all(r['year'] < 2026 for r in one['history'])
    assert one['call']['margin_pp'] is None and one['call']['ev_adjustment_pp'] is None
    assert one['historical_reference']['scope'] == 'same_number_historical_district'
    assert value['validation'] is None  # Never reuse Senate or cross-boundary scores.
    assert all(r['call']['eventual_winner_probability'] is None for r in value['calls'])
    assert all('path' not in s and len(s['sha256']) == 64 for s in value['sources'])
    assert not any(r['latest_result'] for r in office_research(harness.database, 'US HOUSE', before, '2026-10-21')['calls'])
    assert not any(r['year'] >= 2022 for r in office_research(harness.database, 'US HOUSE', revision, '2022-10-21')['calls'][0]['history'])


def test_governor_reference_uses_governor_history_and_report_preserves_exact_race(harness):
    revision = install(harness.database, harness.root)
    value = office_research(harness.database, 'GOVERNOR', revision, '2026-10-21')
    ohio = next(r for r in value['calls'] if r['state'] == 'OH')
    assert {r['year'] for r in ohio['historical_reference']['cycles']} == {2018, 2022}
    assert ohio['call']['margin_pp'] == pytest.approx(20)
    assert ohio['call']['status'] == 'reference_only'
    assert value['validation']['office'] == 'GOVERNOR'
    assert 'governor' in value['validation']['methodology']
    request = {'title': 'Office test report', 'template': 'office', 'race_id': ohio['id'],
        'query': {'state': 'OH', 'revision': revision, 'as_of': '2026-10-21'},
        'results': {'office': 'GOVERNOR'}, 'sections': [{'id': 'office_call'}, {'id': 'evidence'}]}
    report = compose_report(harness.database, request)
    assert report['request']['race_id'] == ohio['id']
    assert report['sections'][0]['tables'][0]['rows'][0][0] == 2018
    assert report['sources'] and 'SHA-256' in report['html']
    assert 'EV direction not established' in report['html']
    pdf, _ = export_report(harness.database, request, 'pdf')
    text = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert 'Governor' in text and 'DEM fixture candidate' in text
    with pytest.raises(ValueError, match='No different race'):
        compose_report(harness.database, {**request, 'race_id': '2026-TX-GOV'})
    assert 'private' not in json.dumps(value['sources']).lower()


def test_house_leading_zero_aliases_choose_one_producer_without_combining_votes(harness):
    install(harness.database, harness.root, office='US HOUSE')
    path=harness.root/'bridge.csv'
    path.write_text('state_po,year,office,district,candidate,party,candidatevotes,stage\n'
        'OH,2024,US HOUSE,001,Bridge A,DEM,75,GEN\nOH,2024,US HOUSE,001,Bridge B,REP,25,GEN\n')
    source={'id':'snyder_test_bridge','title':'Synthetic academic bridge','provider':'state_federal','years':[2024],'tier':3,'url':'https://fixture.invalid/bridge.csv'}
    rows,metadata=parse_results(source,str(path))
    doc=FetchedDocument(url=source['url'],path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),content_type='text/csv',retrieved_at='2026-10-21T12:00:00Z',byte_count=path.stat().st_size)
    revision=_publish(harness.database,source,doc,rows,metadata)['revision']
    raw=_rows(harness.database,state='OH',years=[2024],office='US HOUSE',level='district',revision=revision)
    assert len(raw)==4 and all(r['source_id']=='explicit-synthetic-US HOUSE' for r in raw)
    view=result_query(harness.database,state='OH',year=2024,office='US HOUSE',geography_level='district',baseline=None,revision=revision)
    assert len(view['geographies'])==2
    desk=office_research(harness.database,'US HOUSE',revision,'2026-10-21')
    one=next(r for r in desk['calls'] if r['id']=='2026-OH-HOUSE-01')
    assert len([r for r in one['history'] if r['year']==2024])==1
    assert one['latest_result']['margin_pp']==20


def test_office_report_excludes_senate_polling_from_brief_inventory_and_evidence(harness):
    polls=[]
    for index in range(3):
        poll=survey()
        poll.update(study_id=f'senate-only-{index}',producer=f'Independent Senate fixture {index}',
            question='Synthetic Senate vote choice?')
        polls.append(poll)
    harness.state.payload['polls']=polls
    harness.collect()
    revision=install(harness.database,harness.root)
    request={'title':'Office-scoped report','race_id':'2026-OH-GOV','template':'office',
        'query':{'state':'NC','revision':revision,'as_of':'2026-10-21'},
        'results':{'office':'GOVERNOR'},'sections':[{'id':'office_call'},{'id':'summary'},{'id':'ev_trajectory'},{'id':'polls'}]}
    # North Carolina has no scheduled 2026 governor race: the participation
    # packet remains useful, without borrowing the state's Senate surveys.
    request['race_id']=None
    report=compose_report(harness.database,request)
    assert 'Independent Senate fixture' not in report['html']
    summary=next(s for s in report['sections'] if s['id']=='summary')
    assert not any('descriptive average' in text for text in summary['paragraphs'])
    poll_section=next(s for s in report['sections'] if s['id']=='polls')
    assert all(not table['rows'] for table in poll_section['tables'])
