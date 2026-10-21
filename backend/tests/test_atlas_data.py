from __future__ import annotations

import csv

import pytest
from observatory.atlas.catalog import dataset_catalog, state_catalog
from observatory.atlas.ingest import _publish, number, parse_context, parse_results
from observatory.atlas.models import ensure_schema
from observatory.atlas.store import ranked_choice_scope, result_query
from observatory.db import Database
from observatory.domain import FetchedDocument
from observatory.settings import PROJECT_ROOT, Settings


@pytest.fixture
def database(tmp_path):
    value = Database(Settings(tmp_path, project_root=PROJECT_ROOT))
    ensure_schema(value)
    return value


def rows_file(tmp_path, rows):
    path = tmp_path / "fixture.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def native(**changes):
    return {"state_po": "TX", "year": "2024", "office": "US PRESIDENT", "district": "STATEWIDE",
        "candidate": "Candidate A", "party_simplified": "DEMOCRAT", "votes": "100", "mode": "TOTAL",
        "county_fips": "48001", "county_name": "ANDERSON", "jurisdiction_name": "ANDERSON",
        "jurisdiction_fips": "48001", "precinct": "1", "stage": "GEN", "date": "2024-11-05",
        "dataverse": "PRESIDENT", "magnitude": "1", **changes}


def publish(database, source, path, rows):
    doc = FetchedDocument(url="https://example.org/source.csv", sha256="a" * 64, path=str(path),
        content_type="text/csv", retrieved_at="2026-10-21T10:00:00Z", byte_count=path.stat().st_size)
    return _publish(database, source, doc, rows, {})


def test_total_is_not_added_to_method_components(tmp_path):
    source = {"id": "primary", "provider": "precinct", "years": [2024]}
    path = rows_file(tmp_path, [native(), native(mode="MAIL", votes="40"), native(mode="ELECTION DAY", votes="60"),
        native(candidate="Candidate B", party_simplified="REPUBLICAN", votes="80"),
        native(candidate="OVERVOTES", votes="5")])
    # Exercise the identical parser using a ZIP, as public precinct sources do.
    import zipfile
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(path, "tx24.csv")
    parsed, _ = parse_results(source, str(archive))
    county = [r for r in parsed if r["geography_level"] == "county"]
    assert sum(r["votes"] for r in county) == 180
    assert len(county) == 2
    assert next(r for r in county if r["candidate"] == "Candidate A")["source_modes"] == ["ELECTION DAY", "MAIL", "TOTAL"]


def test_suppression_is_not_a_zero(tmp_path):
    source = {"id": "legacy", "provider": "county_legacy", "years": [2024]}
    path = rows_file(tmp_path, [native(votes="*", candidatevotes="NA")])
    parsed, metadata = parse_results(source, str(path))
    assert parsed[0]["votes"] is None
    assert parsed[0]["partial_suppression"] is True
    assert metadata["suppressed_rows"] == 1


@pytest.mark.parametrize("value", ["NaN", "nan", "inf", "-inf", "-555555555", "*", "NA", None])
def test_invalid_numeric_values_are_not_evidence(value):
    assert number(value) is None


def test_acs_preserves_period_moe_and_sentinel(tmp_path):
    path = tmp_path / "context.dat"
    path.write_text("GEO_ID|B01003_E001|B01003_M001\n0400000US48|30000000|-555555555\n0500000US48001|60000|120\n1400000US48001000100|1000|50\n")
    rows = parse_context({"table": "B01003", "metric": "population", "unit": "people"}, str(path))
    assert len(rows) == 2
    assert rows[0]["moe"] is None
    assert rows[0]["payload"]["moe_raw"] == "-555555555"
    assert rows[1]["moe"] == 120
    assert rows[1]["period_start"] == "2020-01-01"
    assert rows[1]["payload"]["is_voter_characteristic"] is False


def test_revision_and_source_priority(database, tmp_path):
    source = {"id": "original", "provider": "county_legacy", "years": [2024], "title": "Original", "tier": 3}
    path = rows_file(tmp_path, [native(candidatevotes="100"), native(candidate="Candidate B", party_simplified="REPUBLICAN", votes="80", candidatevotes="80")])
    rows, _ = parse_results(source, str(path))
    first = publish(database, source, path, rows)
    rows[0]["votes"] = 120
    second = publish(database, source, path, rows)
    old = result_query(database, "TX", revision=first["revision"])
    new = result_query(database, "TX", revision=second["revision"])
    assert old["summary"]["total_votes"] == 180
    assert new["summary"]["total_votes"] == 200
    assert new["geographies"][0]["dem_margin_pp"] == 20
    assert new["geographies"][0]["winner_margin_pp"] == 20
    assert new["geographies"][0]["rep_margin_pp"] == -20
    # A lower-authority bridge may not replace original-producer evidence.
    rows[0]["votes"] = 1000
    publish(database, {**source, "id": "bridge", "tier": 4}, path, rows)
    assert result_query(database, "TX")["summary"]["total_votes"] == 200


def test_all_states_and_verified_on_demand_inventory(database):
    states = state_catalog(database)["states"]
    assert len(states) == 50
    assert all(s["result_count"] == 0 for s in states)
    datasets = dataset_catalog(database, "TX")["datasets"]
    deep = next(d for d in datasets if d["id"] == "medsl_2024_TX")
    assert deep["on_demand"] is True
    assert deep["status"] == "available"
    assert "JUDICIAL" in deep["offices"]
    assert not any(d.get("state") and d["state"] != "TX" for d in datasets)


@pytest.mark.parametrize('changes', [{"magnitude":"2"}, {"state_po":"ME"}, {"votes":"*"}])
def test_unsupported_winner_labels_withheld(database,tmp_path,changes):
    source={"id":"original","provider":"county_legacy","years":[2024],"title":"Original","tier":3}
    path=rows_file(tmp_path,[native(**changes),native(candidate="Candidate B",party_simplified="REPUBLICAN",votes="80",**{k:v for k,v in changes.items() if k!='votes'})])
    rows,_=parse_results(source,str(path))
    publish(database,source,path,rows)
    result=result_query(database,changes.get('state_po','TX'))
    assert result['geographies'][0]['winner'] is None
    assert result['geographies'][0]['winner_margin_pp'] is None


def test_empty_scope_is_missing_not_zero(database):
    result=result_query(database,'AK')
    assert result['summary']['total_votes'] is None
    assert result['coverage']['status']=='unavailable'


def test_swing_requires_boundary_compatibility(database,tmp_path):
    source={"id":"original","provider":"county_legacy","years":[2024],"title":"Original","tier":3}
    path=rows_file(tmp_path,[native(),native(candidate="Candidate B",party_simplified="REPUBLICAN",votes="80"),
        native(year="2020",votes="80"),native(year="2020",candidate="Candidate B",party_simplified="REPUBLICAN",votes="100")])
    rows,_=parse_results(source,str(path))
    publish(database,source,path,rows)
    place=result_query(database,'TX')['geographies'][0]
    assert place['matched_baseline'] is True
    assert place['baseline_dem_margin_pp'] is not None
    assert place['swing_pp'] is None
    assert place['comparison_status']=='boundary_crosswalk_required'


def test_special_and_regular_contests_are_not_baselines(database,tmp_path):
    source={"id":"original","provider":"county_legacy","years":[2024],"title":"Original","tier":3}
    path=rows_file(tmp_path,[native(office='US SENATE',special='FALSE'),
        native(office='US SENATE',year='2020',special='TRUE')])
    rows,_=parse_results(source,str(path))
    publish(database,source,path,rows)
    place=result_query(database,'TX',office='US SENATE')['geographies'][0]
    assert place['matched_baseline'] is False


def test_no_invented_general_election_date_for_runoff(tmp_path):
    source={"id":"original","provider":"state_federal","years":[2024]}
    path=rows_file(tmp_path,[native(office='US SENATE',stage='RUNOFF',date='')])
    rows,_=parse_results(source,str(path))
    assert rows[0]['date']==''


@pytest.mark.parametrize('state,year,office,expected', [('AK',2018,'US HOUSE',False),('AK',2020,'PRESIDENT',False),
    ('AK',2022,'US HOUSE',True),('AK',2024,'RETENTION SUPREME COURT',False),('ME',2018,'US HOUSE',True),
    ('ME',2018,'PRESIDENT',False),('ME',2020,'PRESIDENT',True),('ME',2024,'GOVERNOR',False),
    ('ME',2024,'STATE HOUSE',False)])
def test_ranked_choice_scope_is_office_and_year_specific(state,year,office,expected):
    assert ranked_choice_scope(state,year,office) is expected


def precinct_fixture(database,tmp_path,count=205):
    import zipfile
    source={"id":"primary_precincts","provider":"precinct","years":[2024],"title":"Primary precinct records","tier":3}
    path=rows_file(tmp_path,[native(precinct=str(index),candidate=name,party_simplified=party,votes=str(votes))
        for index in range(count) for name,party,votes in [('Candidate A','DEMOCRAT',100),('Candidate B','REPUBLICAN',80)]])
    archive=tmp_path/'precincts.zip'
    with zipfile.ZipFile(archive,'w') as zipped:
        zipped.write(path,'tx24.csv')
    parsed,_=parse_results(source,str(archive))
    revision=publish(database,source,path,parsed)['revision']
    return source,parsed,path,revision


def test_precinct_pages_complete_geographies_before_candidate_reads(database,tmp_path):
    from sqlalchemy import event
    precinct_fixture(database,tmp_path)
    candidate_reads=[]
    def capture(_connection,_cursor,statement,parameters,_context,_many):
        if statement.startswith('SELECT atlas_results.id,') and 'precinct' in parameters:
            candidate_reads.append(statement)
    event.listen(database.engine,'before_cursor_execute',capture)
    try:
        first=result_query(database,'TX',geography_level='precinct')
        second=result_query(database,'TX',geography_level='precinct',offset=200)
        outside=result_query(database,'TX',geography_level='precinct',offset=205)
    finally:
        event.remove(database.engine,'before_cursor_execute',capture)
    assert first['pagination']=={'offset':0,'limit':200,'total_geographies':205,'has_more':True}
    assert second['pagination']=={'offset':200,'limit':200,'total_geographies':205,'has_more':False}
    assert len(first['geographies'])==200
    assert len(second['geographies'])==5
    assert not ({r['id'] for r in first['geographies']} & {r['id'] for r in second['geographies']})
    assert all(len(r['options'])==2 and r['total_votes']==180 for r in first['geographies']+second['geographies'])
    assert first['summary']['total_votes']==36000
    assert second['summary']['total_votes']==900
    assert first['summary']['total_votes_scope']=='precinct_page'
    assert first['query']['limit']==200
    assert second['query']['offset']==200
    assert outside['geographies']==[] and outside['summary']['total_votes'] is None
    assert candidate_reads and all('atlas_results.geography_id IN (' in statement for statement in candidate_reads)
    assert any('page only' in warning for warning in first['warnings'])


def test_precinct_pagination_respects_revision_and_explicit_selection(database,tmp_path):
    source,rows,path,revision=precinct_fixture(database,tmp_path,count=3)
    selected_ids=sorted({r['geography_id'] for r in rows if r['geography_level']=='precinct'})
    selected=result_query(database,None,geography_level='precinct',geography_ids=selected_ids[:2],limit=1)
    assert selected['pagination']['total_geographies']==2
    assert len(selected['geographies'])==1
    assert len(selected['geographies'][0]['options'])==2
    # Later evidence must not increase an old revision's page count.
    addition=[{**r,'geography_id':'precinct:TX:2024:new','geography_name':'New precinct'}
        for r in rows if r['geography_level']=='precinct' and r['geography_id']==selected_ids[0]]
    publish(database,source,path,addition)
    assert result_query(database,'TX',geography_level='precinct',revision=revision)['pagination']['total_geographies']==3
    assert result_query(database,'TX',geography_level='precinct')['pagination']['total_geographies']==4


@pytest.mark.parametrize('arguments',[{'limit':0},{'limit':201},{'offset':-1},{'geography_ids':[str(i) for i in range(201)]}])
def test_precinct_reads_are_bounded_even_for_national_queries(database,arguments):
    with pytest.raises(ValueError):
        result_query(database,None,geography_level='precinct',**arguments)


def test_precinct_page_count_applies_selected_contest_in_sql(database,tmp_path):
    source,rows,path,_=precinct_fixture(database,tmp_path,count=3)
    chosen=next(r['contest_id'] for r in rows if r['geography_level']=='precinct')
    other=[{**r,'contest_id':'contest:other','contest_name':'Another contest','district':'002',
        'option_id':'other:'+r['option_id'],'geography_id':r['geography_id']+':other'}
        for r in rows if r['geography_level']=='precinct']
    publish(database,source,path,other)
    selected=result_query(database,'TX',geography_level='precinct',contest_id=chosen,limit=1)
    assert selected['pagination']['total_geographies']==3
    assert len(selected['geographies'])==1
    assert selected['geographies'][0]['contest_id']==chosen
    assert selected['summary']['contest_count']==1


def test_nonpartisan_options_do_not_acquire_zero_party_shares():
    from observatory.atlas.store import _geographies
    records = [{'contest_id': 'synthetic-measure', 'option_id': option, 'geography_id': 'county:48001',
        'geography_name': 'Synthetic', 'state': 'TX', 'year': 2024, 'geography_level': 'county',
        'office': 'BALLOT MEASURE', 'votes': votes, 'snapshot_id': 1, 'source_id': 'fixture',
        'id': index, 'revision': 1, 'round': 'reported', 'payload': {}}
        for index, (option, votes) in enumerate([('yes', 60), ('no', 40)])]
    options = {option: {'name': option, 'party': None, 'kind': 'response'} for option in ('yes', 'no')}
    place = _geographies(records, options)[0]
    assert place['dem_share_pct'] is None and place['rep_share_pct'] is None
    assert place['dem_margin_pp'] is None and place['rep_margin_pp'] is None
    assert place['total_votes'] == 100
    assert place['options'][0]['share_pct'] == 60
