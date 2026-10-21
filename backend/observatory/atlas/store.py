"""One calculation path for historical maps, tables, dossiers, and exports."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select

from observatory.db import Snapshot, record_dict
from observatory.geography import county_index
from observatory.registry import all_states

from .models import BallotOption, Contest, ContextEstimate, ElectionResult, ensure_schema


def ranked_choice_scope(state: str,year: int,office: str) -> bool:
    """General-election rules, scoped to the actual office and implementation year."""
    if state=='ME':
        return (year>=2018 and office in {'US SENATE','US HOUSE'}) or (year>=2020 and office=='PRESIDENT')
    return state=='AK' and year>=2022 and office in {'PRESIDENT','US SENATE','US HOUSE','GOVERNOR',
        'GOVERNOR / LIEUTENANT GOVERNOR','GOVERNOR/LIEUTENANT GOVERNOR','STATE SENATE','STATE HOUSE'}


def _result_statement(*, state, years, office, level, revision, contest_id=None,
                      contest_ids=None, geography_ids=None):
    statement = select(ElectionResult).where(ElectionResult.revision <= revision,
        ElectionResult.year.in_(years), ElectionResult.geography_level == level)
    if state:
        statement = statement.where(ElectionResult.state == state.upper())
    if office:
        statement = statement.where(ElectionResult.office == office.upper())
    if contest_id:
        statement = statement.where(ElectionResult.contest_id == contest_id)
    if contest_ids is not None:
        statement = statement.where(ElectionResult.contest_id.in_(contest_ids))
    if geography_ids:
        statement = statement.where(ElectionResult.geography_id.in_(geography_ids))
    return statement


def _rows(database, *, state, years, office, level, revision, contest_id=None,
          contest_ids=None, geography_ids=None):
    statement=_result_statement(state=state,years=years,office=office,level=level,revision=revision,
        contest_id=contest_id,contest_ids=contest_ids,geography_ids=geography_ids)
    with database.session() as session:
        rows = [record_dict(r) for r in session.scalars(statement.order_by(ElectionResult.revision, ElectionResult.id))]
        contest_ids={r['contest_id'] for r in rows}
        identities={r.id:(r.state,r.year,r.office,r.district.upper(),r.payload.get('special',False),
            r.election_id.split(':')[-1],r.name.upper().replace('STATEWIDE',''))
            for r in session.scalars(select(Contest).where(Contest.id.in_(contest_ids)))}
    latest = {r['logical_key']:r for r in rows}
    from .result_validation import apply_result_validations
    validated_rows = apply_result_validations(database, list(latest.values()), revision)
    # Entire geography/contest uses one producer, rather than mixing candidate rows.
    grouped = defaultdict(list)
    for row in validated_rows:
        grouped[(row['year'],identities.get(row['contest_id'],row['contest_id']),row['geography_id'])].append(row)
    output=[]
    for members in grouped.values():
        scores = {}
        for row in members:
            tier=row['payload'].get('source_tier',9)
            # At state grain prefer dedicated certified statewide compilation.
            specificity = 0 if row['dataset_id'].startswith('medsl_state_') else 1
            scores[row['dataset_id']] = (tier,specificity)
        chosen=min(scores,key=lambda key:scores[key])
        output.extend(r for r in members if r['dataset_id']==chosen)
    return output


def _contest_identity(contest: dict) -> tuple:
    return (contest.get('office'),str(contest.get('district','')).upper(),contest.get('payload',{}).get('special',False),
        str(contest.get('name','')).upper(),contest.get('election_id','').split(':')[-1])


def _selected_contest_ids(database,contest_id: str | None,baseline: int | None) -> list[str] | None:
    """Restrict the evidence read before materializing candidate records.

    A selected current contest may include its semantically matching historical
    contest, while another district, office, stage, or special election cannot
    enter the same comparison.
    """
    if not contest_id:
        return None
    with database.session() as session:
        selected=session.get(Contest,contest_id)
        if selected is None:
            return []
        ids=[contest_id]
        if baseline is not None:
            identity=_contest_identity(record_dict(selected))
            statement=select(Contest).where(Contest.state==selected.state,Contest.office==selected.office,
                Contest.year==baseline,func.upper(Contest.district)==selected.district.upper())
            ids.extend(contest.id for contest in session.scalars(statement)
                if contest.id!=contest_id and _contest_identity(record_dict(contest))==identity)
    return ids


def _precinct_page(database, *, state,year,office,revision,contest_ids,geography_ids,limit,offset) -> tuple[list[str],dict]:
    # Page complete places, never candidate rows: every candidate in each chosen
    # precinct reaches the denominator and the published response distribution.
    statement=_result_statement(state=state,years=[year],office=office,level='precinct',revision=revision,
        contest_ids=contest_ids,geography_ids=geography_ids)
    distinct=statement.with_only_columns(ElectionResult.geography_id).distinct().subquery()
    with database.session() as session:
        total=session.scalar(select(func.count()).select_from(distinct)) or 0
        page=list(session.scalars(select(distinct.c.geography_id).order_by(distinct.c.geography_id).offset(offset).limit(limit)))
    return page,{'offset':offset,'limit':limit,'total_geographies':total,'has_more':offset+len(page)<total}


def _geographies(rows, option_lookup, contest_lookup=None):
    grouped=defaultdict(list)
    for row in rows:
        grouped[(row['contest_id'],row['geography_id'])].append(row)
    output=[]
    for (contest_id,geo_id),members in grouped.items():
        total=sum(r['votes'] or 0 for r in members)
        options=[]
        for row in members:
            option=option_lookup.get(row['option_id'],{})
            options.append({'id':row['option_id'],'name':option.get('name','Unclassified'),
                'party':option.get('party'),'kind':option.get('kind','candidate'),'votes':row['votes'],
                'share_pct':100*row['votes']/total if total and row['votes'] is not None else None,
                'source_refs':[{'snapshot_id':row['snapshot_id'],'source_id':row['source_id'],'result_id':row['id'],'revision':row['revision']}],
                'partial_suppression':row['payload'].get('partial_suppression',False),
                'ballot_parties':option.get('payload',{}).get('ballot_parties',[])})
        options.sort(key=lambda o:-(o['votes'] or 0))
        dem=sum(o['votes'] or 0 for o in options if o['party']=='DEM')
        rep=sum(o['votes'] or 0 for o in options if o['party']=='REP')
        dem_present=any(o['party']=='DEM' for o in options)
        rep_present=any(o['party']=='REP' for o in options)
        margin=100*((options[0]['votes'] or 0)-(options[1]['votes'] or 0))/total if total and len(options)>1 else None
        contest=(contest_lookup or {}).get(contest_id,{})
        uses_ranked_choice=ranked_choice_scope(members[0]['state'],members[0]['year'],members[0]['office'])
        # Election law establishes the counting system, not a file's tabulation
        # round. These compilation schemas do not supply reliable round IDs.
        displayed_round='reported_round_unspecified' if uses_ranked_choice else 'reported'
        tied=len(options)>1 and options[0]['votes']==options[1]['votes']
        suppression=any(o['partial_suppression'] for o in options)
        if suppression:
            for option in options:
                option['share_pct']=None
        winner_supported=bool(options and total and not tied and not suppression and
            (contest.get('magnitude') or 1)==1 and not uses_ranked_choice)
        if suppression:
            margin=None
        item={'id':geo_id,'name':members[0]['geography_name'],'state':members[0]['state'],'year':members[0]['year'],
            'level':members[0]['geography_level'],'contest_id':contest_id,'total_votes':total,'options':options,
            'winner':options[0] if winner_supported else None,
            'leading_option':options[0] if options and total and not suppression and not tied else None,
            'winner_status':'supported' if winner_supported else ('tie' if tied else 'leading_option_only'),
            'margin_pp':margin,'winner_margin_pp':margin if winner_supported else None,
            'dem_share_pct':100*dem/total if total and dem_present and not suppression else None,
            'rep_share_pct':100*rep/total if total and rep_present and not suppression else None,
            'dem_margin_pp':100*(dem-rep)/total if total and dem_present and rep_present and not suppression else None,
            'rep_margin_pp':100*(rep-dem)/total if total and dem_present and rep_present and not suppression else None,
            'source_refs':[ref for option in options for ref in option['source_refs']],
            'partial_suppression':any(o['partial_suppression'] for o in options),
            'boundary_vintage':str(members[0]['year']),'source_id':members[0]['source_id'],
            'round':displayed_round,'election_system':'ranked_choice' if uses_ranked_choice else 'source_reported',
            'unit':'candidate votes'}
        output.append(item)
    return output


def result_query(database, state: str | None = None, year: int = 2024, office: str = 'PRESIDENT',
                 contest_id: str | None = None, baseline: int | None = 2020,
                 geography_level: str = 'county', revision: int | None = None,
                 geography_ids: list[str] | None = None, limit: int | None = None,offset: int = 0) -> dict:
    ensure_schema(database)
    if state and state.upper() not in {s['code'] for s in all_states()}:
        raise ValueError('Unknown state')
    if geography_level not in {'state','county','district','municipality','precinct'}:
        raise ValueError('Unsupported geography level')
    latest=database.latest_revision()
    bound=latest if revision is None else revision
    if bound<0 or bound>latest:
        raise ValueError('Dataset revision is outside the available evidence range')
    years=[int(year)]+([int(baseline)] if baseline is not None and baseline != year else [])
    selected_contest_ids=_selected_contest_ids(database,contest_id,baseline)
    pagination=None
    evidence_geography_ids=geography_ids
    effective_limit=None
    if geography_level=='precinct':
        effective_limit=200 if limit is None else limit
        if isinstance(effective_limit,bool) or not isinstance(effective_limit,int) or not 1<=effective_limit<=200:
            raise ValueError('Precinct page size must be an integer between 1 and 200')
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:
            raise ValueError('Precinct page offset must be a nonnegative integer')
        if geography_ids and len(geography_ids)>200:
            raise ValueError('Select no more than 200 precincts in one investigation')
        evidence_geography_ids,pagination=_precinct_page(database,state=state,year=year,office=office,
            revision=bound,contest_ids=selected_contest_ids,geography_ids=geography_ids,
            limit=effective_limit,offset=offset)
    rows=[] if pagination is not None and not evidence_geography_ids else _rows(
        database,state=state,years=years,office=office,level=geography_level,revision=bound,
        contest_ids=selected_contest_ids,geography_ids=evidence_geography_ids)
    option_ids={r['option_id'] for r in rows}
    contest_ids={r['contest_id'] for r in rows}
    with database.session() as session:
        option_lookup={r.id:record_dict(r) for r in session.scalars(select(BallotOption).where(BallotOption.id.in_(option_ids)))}
        contests=[record_dict(r) for r in session.scalars(select(Contest).where(Contest.id.in_(contest_ids)))]
        snapshot_ids={r['snapshot_id'] for r in rows}
        sources=[record_dict(r) for r in session.scalars(select(Snapshot).where(Snapshot.id.in_(snapshot_ids)))]
    lookup={r['id']:r for r in contests}
    identity=_contest_identity
    selected=lookup.get(contest_id) if contest_id else None
    if contest_id:
        rows=[r for r in rows if r['contest_id']==contest_id or (r['year']==baseline and selected and identity(lookup.get(r['contest_id'],{}))==identity(selected))]
        contests=[r for r in contests if any(row['contest_id']==r['id'] for row in rows)]
    current=_geographies([r for r in rows if r['year']==year],option_lookup,lookup)
    earlier=_geographies([r for r in rows if r['year']==baseline],option_lookup,lookup)
    from ..historical_comparisons import _review, boundary_eligibility
    boundary_review = _review(database, bound) if geography_level == 'county' and baseline is not None else None
    reviewed_county_comparisons = 0
    prior={(r['id'],identity(lookup.get(r['contest_id'],{}))):r for r in earlier}
    for item in current:
        old=prior.get((item['id'],identity(lookup.get(item['contest_id'],{}))))
        item['baseline_margin_pp']=old['dem_margin_pp'] if old else None
        item['baseline_dem_margin_pp']=old['dem_margin_pp'] if old else None
        round_compatible=bool(old and old['round']==item['round'] and item['round']!='reported_round_unspecified')
        boundary_decision = boundary_eligibility(item['state'], item['id'], geography_level, year, baseline or year,
            review_available=boundary_review is not None)
        # A stable county does not make its intersection with a changed
        # legislative/congressional/local district the same reporting unit.
        district = str(lookup.get(item['contest_id'], {}).get('district', 'STATEWIDE')).upper()
        if district != 'STATEWIDE' and baseline is not None and year != baseline:
            boundary_decision = {'eligible': False, 'reason': 'contest_district_crosswalk_required',
                'standard': 'numbered contest districts need their own reviewed boundary continuity'}
        boundary_compatible=bool(boundary_decision['eligible'] and round_compatible)
        item['swing_pp']=item['dem_margin_pp']-old['dem_margin_pp'] if old and boundary_compatible and item['dem_margin_pp'] is not None and old['dem_margin_pp'] is not None else None
        item['matched_baseline']=old is not None
        item['comparison_status']=boundary_decision['reason'] if old and boundary_compatible else (
            'round_provenance_required' if old and not round_compatible else ('boundary_crosswalk_required' if old else 'missing_baseline'))
        item['boundary_comparison'] = boundary_decision
        if old and boundary_compatible and geography_level == 'county':
            reviewed_county_comparisons += 1
        if geography_level=='county':
            match=county_index(item['state'])['by_geoid'].get(item['id'].removeprefix('county:'))
            item['geography_join']={'status':'matched' if match else 'unmatched','boundary_vintage':'2024',
                'method':'census_geoid' if match else 'no_current_boundary_for_source_identifier',
                'canonical_id':match['canonical_id'] if match else None}
    current.sort(key=lambda row:-(row['total_votes'] or 0))
    current_contests={r['contest_id'] for r in current}
    # Multiple states' presidential contests are compatible for a national sum;
    # unrelated offices/contests are never added to an election participation total.
    compatible=office.upper()=='PRESIDENT' or len(current_contests)<=1
    total=sum(r['total_votes'] for r in current) if compatible and current else None
    for row in current:
        row['share_of_selected_votes_pct']=100*row['total_votes']/total if total else None
    warnings=['Historical published candidate returns are election context, not early votes or contemporaneous reporting snapshots.',
        'Margin is winner lead in percentage points; Democratic margin is D minus R; swing is change in D minus R.',
        'Matching geographic identifiers do not establish identical boundaries across vintages.']
    from .result_validation import result_validation_warnings
    warnings.extend(result_validation_warnings(database, rows, bound))
    if reviewed_county_comparisons and boundary_review:
        warnings.append('County differences use matched reported county identifiers with no Census-listed substantial boundary change in the reviewed 2018–2024 window. Minor adjustments are not certified identical; no votes are redistributed.')
        snapshot_ids.update(ref['snapshot_id'] for ref in boundary_review['sources'] if ref.get('snapshot_id'))
    if pagination is not None:
        warnings.append('Candidate-vote totals and geographic contribution shares describe this precinct page only; they are not statewide totals. Each displayed precinct retains all its candidate records.')
    if geography_level=='county' and state=='AK':
        warnings.append('Alaska statewide and native reporting-district evidence are available; borough totals are not manufactured from election districts.')
    if not compatible:
        warnings.append('Several contests are present; their candidate vote totals are not added together.')
    if any(r['partial_suppression'] for r in current):
        warnings.append('Some source counts are suppressed; displayed sums are incomplete lower bounds, not exact totals.')
    if any('bridge' in r['source_id'] for r in current):
        warnings.append('A labeled secondary county compilation fills this view; loading the original-producer state precinct dataset replaces it where supported.')
    if any(r['election_system']=='ranked_choice' for r in current):
        warnings.append('This office uses ranked-choice voting. The compilation does not establish its tabulation round; published counts remain inspectable and an eventual-winner label is withheld.')
    summary={'total_votes':total,'geography_count':len(current),'contest_count':len(current_contests),
        'matched_baseline_count':sum(r['matched_baseline'] for r in current),'unit':'candidate votes'}
    if pagination is not None:
        summary['total_votes_scope']='precinct_page'
    if len(current)==1:
        summary.update({k:current[0][k] for k in ('options','winner','leading_option','winner_status','margin_pp','winner_margin_pp','dem_share_pct','rep_share_pct','dem_margin_pp','rep_margin_pp','swing_pp')})
    reconciliation=None
    if state and office.upper()=='PRESIDENT' and geography_level=='county' and not geography_ids and current:
        reference_rows=_rows(database,state=state,years=[year],office=office,level='state',revision=bound)
        snapshot_ids.update(r['snapshot_id'] for r in reference_rows)
        reference_total=sum(r['votes'] or 0 for r in reference_rows)
        if reference_rows:
            difference=(total or 0)-reference_total
            reconciliation={'state_reference_votes':reference_total,'displayed_geographic_votes':total,
                'difference_votes':difference,'difference_pct':100*difference/reference_total if reference_total else None,
                'status':'agrees' if difference==0 else 'source_vintage_or_coverage_difference',
                'source_ids':sorted({r['source_id'] for r in reference_rows})}
            if difference:
                warnings.append(f"County source sums differ from the dedicated statewide source by {difference:,.0f} candidate votes. Source vintages, write-in treatment, or coverage differ; this view has not been reconciled to statewide certification.")
    if any(r['comparison_status']=='boundary_crosswalk_required' for r in current):
        warnings.append('Geographic swing is withheld until a defensible boundary crosswalk is available; both elections\' original margins remain inspectable.')
    if any(r['comparison_status']=='round_provenance_required' for r in current):
        warnings.append('Cross-cycle swing is withheld because comparable tabulation rounds are not established.')
    unmatched=[{'id':r['id'],'name':r['name'],'state':r['state']} for r in current if r.get('geography_join',{}).get('status')=='unmatched']
    if unmatched:
        warnings.append(f"{len(unmatched)} source reporting identifiers do not match the 2024 Census county boundaries; they remain in the table and are not assigned to a different place.")
    history=[]
    if state and office.upper()=='PRESIDENT':
        history_rows=_rows(database,state=state,years=list(range(1976,2025,4)),office=office,level='state',revision=bound)
        snapshot_ids.update(r['snapshot_id'] for r in history_rows)
        with database.session() as session:
            ids={r['option_id'] for r in history_rows}
            history_options={r.id:record_dict(r) for r in session.scalars(select(BallotOption).where(BallotOption.id.in_(ids)))}
        for item in _geographies(history_rows,history_options):
            history.append({k:item[k] for k in ('year','total_votes','dem_share_pct','rep_share_pct','dem_margin_pp','rep_margin_pp','margin_pp','winner','leading_option','source_refs')})
        history.sort(key=lambda r:r['year'])
    missing_snapshots = snapshot_ids - {r['id'] for r in sources}
    if missing_snapshots:
        with database.session() as session:
            sources.extend(record_dict(r) for r in session.scalars(select(Snapshot).where(Snapshot.id.in_(missing_snapshots))))
    sources.sort(key=lambda r: r['id'])
    return {'revision':bound,'query':{'state':state,'year':year,'office':office,'contest_id':contest_id,'baseline':baseline,
            'geography_level':geography_level,'geography_ids':geography_ids or [],
            'limit':effective_limit,'offset':offset if pagination is not None else 0},'contests':contests,'summary':summary,
        'pagination':pagination,
        'geographies':current,'baseline_geographies':earlier,'history':history,
        'margin_definition':{'margin_pp':'positive winner lead','dem_margin_pp':'DEM minus REP','rep_margin_pp':'REP minus DEM','swing_pp':'current DEM-minus-REP minus baseline DEM-minus-REP'},
        'coverage':{'status':'loaded' if current else 'unavailable','current_geographies':len(current),'baseline_geographies':len(earlier),
            'matched_geographies':sum(r['matched_baseline'] for r in current),
            'boundary_harmonization':'state_boundaries_stable' if geography_level=='state' else ('reviewed_material_county_continuity' if reviewed_county_comparisons else 'crosswalk_required'),
            'source_reconciliation':reconciliation,
            'geography_join':{'boundary_vintage':'2024','matched':len(current)-len(unmatched),
                'unmatched':len(unmatched),'unmatched_records':unmatched} if geography_level=='county' else None},
        'sources':sources,'warnings':warnings}


def context_query(database, state: str | None = None, geography_id: str | None = None,
                  metric: str | None = None, revision: int | None = None) -> dict:
    ensure_schema(database)
    latest=database.latest_revision()
    bound=latest if revision is None else revision
    if bound<0 or bound>latest:
        raise ValueError('Dataset revision is outside the available evidence range')
    statement=select(ContextEstimate).where(ContextEstimate.revision<=bound)
    if state:
        statement=statement.where(ContextEstimate.state==state.upper())
    if geography_id:
        statement=statement.where(ContextEstimate.geography_id==geography_id)
    if metric:
        statement=statement.where(ContextEstimate.metric==metric)
    with database.session() as session:
        rows={r.logical_key:record_dict(r) for r in session.scalars(statement.order_by(ContextEstimate.revision,ContextEstimate.id))}
        ids={r['snapshot_id'] for r in rows.values()}
        sources=[record_dict(r) for r in session.scalars(select(Snapshot).where(Snapshot.id.in_(ids)))]
    return {'revision':bound,'query':{'state':state,'geography_id':geography_id,'metric':metric},'estimates':list(rows.values()),
        'sources':sources,'warnings':['Resident population and household estimates are geographic context, not measured characteristics of voters.',
            'ACS estimates cover 2020–2024 and include the published 90% margins of error. Negative Census sentinel values are annotations, not numbers.']}
